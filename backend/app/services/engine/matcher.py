"""Camada 2: dá uma nota a cada elemento da página comparando-o com a impressão digital gravada."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.models.enums import StepAction
from app.services.engine.snapshot import PageElement

WEIGHT_TEXT = 0.5
WEIGHT_ROLE = 0.15
WEIGHT_NEIGHBORS = 0.2
WEIGHT_ATTRIBUTES = 0.15

_CLICKABLE_ROLES = {"button", "link", "menuitem", "tab", "option", "generic"}
_TEXT_INPUT_ROLES = {"textbox", "combobox"}


@dataclass
class Candidate:
    element: PageElement
    score: float


def similarity(first: str, second: str) -> float:
    a, b = first.strip().casefold(), second.strip().casefold()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _best_text_similarity(target: dict[str, Any], element: PageElement) -> float:
    recorded = [target.get(key) for key in ("text", "label", "placeholder")]
    current = [element.text, element.label, element.placeholder]
    return max(
        (similarity(a, b) for a in recorded if a for b in current if b),
        default=0.0,
    )


def _neighbor_similarity(recorded: list[str], current: list[str]) -> float:
    if not current:
        return 0.0
    return sum(max(similarity(item, other) for other in current) for item in recorded) / len(
        recorded
    )


def _role_similarity(recorded: str, current: str) -> float:
    if recorded == current:
        return 1.0
    return 0.7 if recorded in _CLICKABLE_ROLES and current in _CLICKABLE_ROLES else 0.0


def score(target: dict[str, Any], element: PageElement) -> float:
    """Só entra na conta o que foi gravado; a nota vai de 0 a 1."""
    parts: list[tuple[float, float]] = []

    if target.get("text") or target.get("label") or target.get("placeholder"):
        parts.append((WEIGHT_TEXT, _best_text_similarity(target, element)))
    if target.get("role"):
        parts.append((WEIGHT_ROLE, _role_similarity(target["role"], element.role)))
    if target.get("neighbors"):
        parts.append(
            (WEIGHT_NEIGHBORS, _neighbor_similarity(target["neighbors"], element.neighbors))
        )

    attributes = [
        target.get(key) == getattr(element, key) for key in ("name", "test_id") if target.get(key)
    ]
    if attributes:
        parts.append((WEIGHT_ATTRIBUTES, sum(attributes) / len(attributes)))

    total_weight = sum(weight for weight, _ in parts)
    if total_weight == 0:
        return 0.0
    return sum(weight * value for weight, value in parts) / total_weight


def is_compatible(action: StepAction, element: PageElement) -> bool:
    """Evita, por exemplo, digitar em um link ou clicar em um campo de texto como se fosse botão."""
    if action == StepAction.FILL:
        return element.role == "textbox"
    if action == StepAction.SELECT:
        return element.role == "combobox"
    if action == StepAction.CHECK:
        return element.role in {"checkbox", "radio"}
    if action == StepAction.PRESS:
        return element.role in _TEXT_INPUT_ROLES
    return element.role not in _TEXT_INPUT_ROLES


def rank(
    target: dict[str, Any], action: StepAction, elements: list[PageElement]
) -> list[Candidate]:
    candidates = [
        Candidate(element, score(target, element))
        for element in elements
        if is_compatible(action, element)
    ]
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


def is_confident(candidates: list[Candidate], threshold: float, margin: float) -> bool:
    """Precisa de nota alta e de folga sobre o segundo colocado: empate é dúvida, e dúvida vai para a pessoa."""
    if not candidates or candidates[0].score < threshold:
        return False
    return len(candidates) == 1 or candidates[0].score - candidates[1].score >= margin
