"""O cliente da IA diante de limites e respostas ruins, sem chamar o serviço real."""

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.services import llm_client
from app.services.llm_client import LlmClient, LlmUnavailableError

URL = "https://ia.exemplo/chat/completions"


def resposta(
    status: int, corpo: Any = None, cabecalhos: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(
        status, json=corpo or {}, headers=cabecalhos, request=httpx.Request("POST", URL)
    )


def conteudo(texto: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": texto}}]}


@pytest.fixture
def esperas(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    registro: list[float] = []
    monkeypatch.setattr(llm_client.settings, "llm_api_key", SecretStr("chave-de-teste"))
    monkeypatch.setattr(llm_client.settings, "llm_model", "modelo-de-teste")
    monkeypatch.setattr(llm_client.time, "sleep", registro.append)
    return registro


def responder_com(
    monkeypatch: pytest.MonkeyPatch, respostas: list[httpx.Response]
) -> list[dict[str, Any]]:
    pedidos: list[dict[str, Any]] = []

    def falso_post(_url: str, **kwargs: Any) -> httpx.Response:
        pedidos.append(kwargs)
        return respostas.pop(0)

    monkeypatch.setattr(llm_client.httpx, "post", falso_post)
    return pedidos


def test_limite_passageiro_espera_e_tenta_de_novo(
    esperas: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    pedidos = responder_com(
        monkeypatch,
        [
            resposta(429, cabecalhos={"retry-after": "3"}),
            resposta(200, conteudo(json.dumps({"ok": True}))),
        ],
    )
    assert LlmClient().chat_json("s", "u") == {"ok": True}
    assert esperas == [3.0]
    assert len(pedidos) == 2


def test_limite_que_continua_vira_indisponivel_sem_insistir(
    esperas: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    pedidos = responder_com(monkeypatch, [resposta(429), resposta(429)])
    with pytest.raises(LlmUnavailableError):
        LlmClient().chat_json("s", "u")
    assert len(pedidos) == 2


def test_espera_longa_tem_teto(esperas: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    responder_com(
        monkeypatch,
        [resposta(429, cabecalhos={"retry-after": "3600"}), resposta(200, conteudo("{}"))],
    )
    LlmClient().chat_json("s", "u")
    assert esperas == [20.0]


def test_retry_after_invalido_usa_o_padrao(
    esperas: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    responder_com(
        monkeypatch,
        [resposta(429, cabecalhos={"retry-after": "amanha"}), resposta(200, conteudo("{}"))],
    )
    LlmClient().chat_json("s", "u")
    assert esperas == [2.0]


def test_outros_erros_nao_repetem(esperas: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos = responder_com(monkeypatch, [resposta(401)])
    with pytest.raises(LlmUnavailableError):
        LlmClient().chat_json("s", "u")
    assert len(pedidos) == 1
    assert esperas == []


@pytest.mark.parametrize("texto", ["isto nao e json", "[1, 2]"])
def test_resposta_fora_do_formato(
    texto: str, esperas: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    responder_com(monkeypatch, [resposta(200, conteudo(texto))])
    with pytest.raises(LlmUnavailableError):
        LlmClient().chat_json("s", "u")


def test_log_de_erro_nao_traz_o_conteudo_enviado(
    esperas: list[float], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    responder_com(monkeypatch, [resposta(400, {"error": {"failed_generation": "dado-sigiloso"}})])
    with pytest.raises(LlmUnavailableError):
        LlmClient().chat_json("s", "dado-sigiloso")
    assert "dado-sigiloso" not in caplog.text
    assert "chave-de-teste" not in caplog.text
    assert "400" in caplog.text
