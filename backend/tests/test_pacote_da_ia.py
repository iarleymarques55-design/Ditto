"""O pacote que descreve a tela para a IA cabe no limite do plano, mesmo em páginas enormes."""

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services import llm_client
from app.services.engine.snapshot import PageElement
from app.services.llm_client import LlmClient
from app.services.sanitizer import build_explorer_payload


def _pagina_enorme() -> tuple[list[PageElement], dict[int, list[str]]]:
    """Como o Google Agenda: centenas de botões de dia e horário, menus e alguns campos."""
    elementos: list[PageElement] = []
    for indice in range(400):
        if indice % 50 == 0:
            elementos.append(
                PageElement(index=indice, role="textbox", tag="input", label=f"Título {indice}")
            )
        elif indice % 3 == 0:
            elementos.append(
                PageElement(
                    index=indice,
                    role="link",
                    tag="a",
                    text=f"Agenda compartilhada número {indice} " * 4,
                    in_menu=True,
                )
            )
        else:
            elementos.append(
                PageElement(
                    index=indice,
                    role="button",
                    tag="div",
                    text=f"{indice % 31 + 1} de dezembro, 09:00, sem eventos " * 3,
                )
            )
    opcoes = {e.index: [f"Opção {n}" for n in range(30)] for e in elementos[:20]}
    return elementos, opcoes


def _pacote(elementos: list[PageElement], opcoes: dict[int, list[str]]) -> str:
    return build_explorer_payload(
        prompt="Crie o evento aniversário em 7 de dezembro às 9h",
        url="https://calendar.google.com/calendar/u/0/r",
        title="Google Agenda",
        done=[],
        last_result="A página abriu.",
        answers=[],
        captured=[],
        steps_left=40,
        elements=elementos,
        options=opcoes,
        screen_data=[],
        screen_text="Dezembro de 2026 " * 200,
    )


def test_pagina_enorme_cabe_no_teto() -> None:
    elementos, opcoes = _pagina_enorme()

    pacote = _pacote(elementos, opcoes)

    assert len(pacote) <= settings.llm_max_payload_chars
    json.loads(pacote)


def test_campos_ficam_e_menus_saem_primeiro() -> None:
    elementos, opcoes = _pagina_enorme()

    enviados = json.loads(_pacote(elementos, opcoes))["elementos_da_pagina"]

    campos = [e for e in elementos if e.role == "textbox"]
    indices = {e["indice"] for e in enviados}
    # Os campos (onde a IA digita o nome do evento) nunca ficam de fora
    assert all(campo.index in indices for campo in campos)
    assert not any(e.get("no_menu") for e in enviados)


def test_pagina_pequena_vai_inteira(monkeypatch: pytest.MonkeyPatch) -> None:
    elementos = [
        PageElement(index=n, role="button", tag="button", text=f"Botão {n}") for n in range(30)
    ]

    enviados = json.loads(_pacote(elementos, {}))["elementos_da_pagina"]

    assert len(enviados) == 30


def test_ia_recebe_teto_para_a_resposta(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sem "max_tokens", o Groq conta o máximo do modelo no limite do plano e devolve 413
    monkeypatch.setattr(llm_client.settings, "llm_api_key", SecretStr("chave-de-teste"))
    monkeypatch.setattr(llm_client.settings, "llm_model", "modelo-de-teste")
    pedidos: list[dict[str, Any]] = []

    def falso_post(_url: str, **kwargs: Any) -> httpx.Response:
        pedidos.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}]},
            request=httpx.Request("POST", _url),
        )

    monkeypatch.setattr(llm_client.httpx, "post", falso_post)

    LlmClient().chat_json("sistema", "usuario")

    assert pedidos[0]["max_tokens"] == settings.llm_max_output_tokens
