"""Único caminho de saída de dados para a IA. Nada chega ao LLM sem passar por aqui."""

import json
import re
from collections.abc import Iterable
from typing import Any

from app.services.engine.snapshot import PageElement

MAX_ELEMENTS = 150
MAX_TEXT = 120
_MIN_SECRET_LENGTH = 3


class SecretLeakError(Exception):
    """O conteúdo montado ainda contém um segredo: a chamada à IA é cancelada."""


def _usable(secrets: Iterable[str]) -> list[str]:
    # Valores curtos demais ("1", "sim") apagariam partes comuns do texto sem proteger nada.
    # Do maior para o menor: um segredo pode conter outro.
    return sorted(
        {secret for secret in secrets if secret and len(secret) >= _MIN_SECRET_LENGTH},
        key=len,
        reverse=True,
    )


def scrub(text: str, secrets: Iterable[str]) -> str:
    cleaned = text
    for secret in _usable(secrets):
        cleaned = re.sub(re.escape(secret), "[oculto]", cleaned, flags=re.IGNORECASE)
    return cleaned


def _short(text: str | None, secrets: list[str]) -> str:
    return scrub(text or "", secrets)[:MAX_TEXT]


def value_shape(value: str | None) -> str:
    """Só o formato do valor: "Loja 07" vira "aaaa 99". O conteúdo nunca sai daqui."""
    if not value:
        return ""
    return re.sub(r"[^\W\d]", "a", re.sub(r"\d", "9", value))[:40]


def _assert_clean(payload: str, secrets: list[str]) -> str:
    lowered = payload.lower()
    if any(secret.lower() in lowered for secret in secrets):
        raise SecretLeakError("O conteúdo para a IA ainda contém um valor protegido.")
    return payload


def build_repair_payload(
    intent: str,
    action: str,
    recorded_target: dict[str, Any],
    elements: list[PageElement],
    secrets: Iterable[str],
    already_clicked: Iterable[str] = (),
) -> str:
    """Monta o pedido de reparo. O valor dos campos nunca é coletado (ver snapshot.py)."""
    protected = _usable(secrets)
    data = {
        "objetivo_do_passo": _short(intent, protected),
        "acao": action,
        "elemento_gravado": {
            "papel": recorded_target.get("role"),
            "texto": _short(recorded_target.get("text"), protected),
            "rotulo": _short(recorded_target.get("label"), protected),
            "vizinhos": [_short(item, protected) for item in recorded_target.get("neighbors", [])][
                :5
            ],
        },
        "ja_clicados": [_short(item, protected) for item in already_clicked],
        "elementos_da_pagina": [
            {
                "indice": element.index,
                "papel": element.role,
                "tag": element.tag,
                "texto": _short(element.text, protected),
                "rotulo": _short(element.label, protected),
                "dica": _short(element.placeholder, protected),
            }
            for element in elements[:MAX_ELEMENTS]
        ],
    }
    return _assert_clean(json.dumps(data, ensure_ascii=False), protected)


def build_analysis_payload(steps: list[dict[str, Any]], secrets: Iterable[str]) -> str:
    """Monta o pedido de análise da gravação, com o formato dos valores em vez dos valores."""
    protected = _usable(secrets)
    data = [
        {
            "posicao": step["position"],
            "acao": step["action"],
            "texto": _short(step.get("text"), protected),
            "rotulo": _short(step.get("label"), protected),
            "formato_do_valor": value_shape(step.get("value")),
        }
        for step in steps
    ]
    return _assert_clean(json.dumps(data, ensure_ascii=False), protected)
