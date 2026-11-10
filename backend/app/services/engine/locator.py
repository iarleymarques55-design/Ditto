"""Camada 1: procura o elemento pelos seletores gravados, do mais estável para o menos estável."""

import json
from collections.abc import Iterator
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Frame, Locator, Page

from app.services.engine.matcher import similarity

# Um seletor frágil (CSS, name) pode apontar para outro botão depois que a página muda.
_MIN_TEXT_MATCH_FOR_WEAK_SELECTORS = 0.6


def _strong_selectors(page: Page | Frame, target: dict[str, Any]) -> Iterator[Locator]:
    if target.get("test_id"):
        yield page.get_by_test_id(target["test_id"])
    name = target.get("text") or target.get("label")
    if target.get("role") and name:
        yield page.get_by_role(target["role"], name=name, exact=True)
    if target.get("label"):
        yield page.get_by_label(target["label"], exact=True)
    if target.get("placeholder"):
        yield page.get_by_placeholder(target["placeholder"], exact=True)
    if target.get("text"):
        yield page.get_by_text(target["text"], exact=True)


def _weak_selectors(page: Page | Frame, target: dict[str, Any]) -> Iterator[Locator]:
    if target.get("name"):
        yield page.locator(f"{target.get('tag', '')}[name={json.dumps(target['name'])}]")
    if target.get("css"):
        yield page.locator(target["css"])


def _single_visible(locator: Locator) -> bool:
    try:
        return locator.count() == 1 and locator.is_visible()
    except PlaywrightError:
        # Seletor CSS inválido ou página navegando: não é um elemento encontrado
        return False


def _still_looks_the_same(locator: Locator, target: dict[str, Any]) -> bool:
    recorded = target.get("text")
    if not recorded:
        return True
    try:
        return similarity(recorded, locator.inner_text()) >= _MIN_TEXT_MATCH_FOR_WEAK_SELECTORS
    except PlaywrightError:
        return False


def _only_match(locators: list[Locator], target: dict[str, Any] | None) -> Locator | None:
    """Exatamente um elemento visível, somando todos os iframes. Ambíguo é não encontrado."""
    found = [locator for locator in locators if _single_visible(locator)]
    if len(found) != 1:
        return None
    if target is not None and not _still_looks_the_same(found[0], target):
        return None
    return found[0]


def locate(page: Page, target: dict[str, Any]) -> Locator | None:
    """Procura na página e nos iframes, tentando os seletores do mais estável para o menos estável."""
    frames = page.frames
    by_frame = [list(_strong_selectors(frame, target)) for frame in frames]
    for options in zip(*by_frame, strict=True):
        element = _only_match(list(options), None)
        if element is not None:
            return element

    by_frame = [list(_weak_selectors(frame, target)) for frame in frames]
    for options in zip(*by_frame, strict=True):
        element = _only_match(list(options), target)
        if element is not None:
            return element
    return None
