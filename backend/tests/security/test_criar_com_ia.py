"""Bateria da skill backend-python para "criar tarefa com IA"."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.services.engine.llm_explorer import ExplorerDecision
from app.services.engine.snapshot import PageElement
from app.services.sanitizer import SecretLeakError, build_explorer_payload

Cabecalho = dict[str, str]
PEDIDO = {"prompt": "Consulte o CNPJ 111 e guarde a situação.", "start_url": "https://portal.exemplo/busca"}


@pytest.fixture(autouse=True)
def _ia_ligada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("chave-de-teste"))
    monkeypatch.setattr(settings, "llm_model", "modelo-de-teste")
    monkeypatch.setattr(settings, "extension_runner_port", 8765)


def test_outra_conta_nao_ve_nem_mexe_no_pedido(
    api: TestClient, autenticado: Cabecalho, criar_conta: Callable[..., Cabecalho]
) -> None:
    pedido_id = api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado).json()["id"]
    intrusa = criar_conta()
    caminho = f"/api/v1/ai-drafts/{pedido_id}"

    assert api.get(caminho, headers=intrusa).status_code == 404
    assert api.post(f"{caminho}/answer", json={"answer": "sim"}, headers=intrusa).status_code == 404
    assert api.post(f"{caminho}/cancel", headers=intrusa).status_code == 404
    assert api.get("/api/v1/ai-drafts", headers=intrusa).json() == []
    assert api.get(caminho, headers=autenticado).json()["status"] == "queued"


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "done"},
        {"owner_id": "00000000-0000-4000-8000-000000000000"},
        {"flow_id": "00000000-0000-4000-8000-000000000000"},
        {"steps": [{"action": "click"}]},
        {"allowed_hosts": ["intranet.local"]},
    ],
)
def test_campos_internos_sao_recusados(
    extra: dict[str, Any], api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = api.post("/api/v1/ai-drafts", json={**PEDIDO, **extra}, headers=autenticado)
    assert resposta.status_code == 422


@pytest.mark.parametrize(
    "corpo",
    [
        {"prompt": "curto", "start_url": "https://portal.exemplo"},
        {"prompt": "x" * 2001, "start_url": "https://portal.exemplo"},
        {"prompt": "Consulte o CNPJ 111.", "start_url": "javascript:alert(1)"},
        {"prompt": "Consulte o CNPJ 111.", "start_url": "file:///etc/passwd"},
        {"prompt": "Consulte o CNPJ 111."},
        {"prompt": 123, "start_url": "https://portal.exemplo"},
    ],
)
def test_pedido_invalido_responde_422(
    corpo: dict[str, Any], api: TestClient, autenticado: Cabecalho
) -> None:
    assert api.post("/api/v1/ai-drafts", json=corpo, headers=autenticado).status_code == 422


def test_resposta_gigante_e_recusada(api: TestClient, autenticado: Cabecalho) -> None:
    pedido_id = api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado).json()["id"]
    resposta = api.post(
        f"/api/v1/ai-drafts/{pedido_id}/answer", json={"answer": "x" * 301}, headers=autenticado
    )
    assert resposta.status_code == 422


@pytest.mark.parametrize("texto", ["' OR 1=1 --", "'; DROP TABLE ai_drafts; --", "<script>alert(1)</script>"])
def test_injecao_no_pedido_fica_so_como_texto(
    texto: str, api: TestClient, autenticado: Cabecalho
) -> None:
    corpo = {**PEDIDO, "prompt": f"Consulte o CNPJ {texto}"}
    criado = api.post("/api/v1/ai-drafts", json=corpo, headers=autenticado)
    assert criado.status_code == 201
    assert criado.json()["prompt"] == corpo["prompt"]
    api.post(f"/api/v1/ai-drafts/{criado.json()['id']}/cancel", headers=autenticado)


def test_id_invalido_responde_422(api: TestClient, autenticado: Cabecalho) -> None:
    assert api.get("/api/v1/ai-drafts/1 OR 1=1", headers=autenticado).status_code == 422


def test_token_da_extensao_nao_cria_pedido(api: TestClient, autenticado: Cabecalho) -> None:
    token = api.post("/api/v1/auth/recording-token", headers=autenticado).json()["token"]
    resposta = api.post(
        "/api/v1/ai-drafts", json=PEDIDO, headers={"Authorization": f"Bearer {token}"}
    )
    assert resposta.status_code == 401


def test_resposta_nao_traz_campos_internos(api: TestClient, autenticado: Cabecalho) -> None:
    corpo = api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado).json()
    assert {"owner_id", "answer", "heartbeat_at", "steps", "allowed_hosts"}.isdisjoint(corpo)


def test_pacote_da_ia_nunca_leva_valor_de_campo_nem_consulta_da_url() -> None:
    campo = PageElement(index=0, role="textbox", tag="input", label="CNPJ", input_type="text")
    pacote = build_explorer_payload(
        prompt="Consulte o CNPJ 111",
        url="https://portal.exemplo/consulta?token=sessao-secreta#topo",
        title="Consulta",
        done=[],
        last_result="",
        answers=[],
        captured=[],
        steps_left=10,
        elements=[campo],
        options={},
        screen_data=[],
    )
    dados = json.loads(pacote)
    assert dados["endereco_atual"] == "https://portal.exemplo/consulta"
    assert "sessao-secreta" not in pacote
    assert "valor" not in dados["elementos_da_pagina"][0]


def test_pacote_da_ia_some_com_segredos_conhecidos() -> None:
    pacote = build_explorer_payload(
        prompt="Use a senha-do-portal-111",
        url="https://portal.exemplo",
        title="",
        done=[],
        last_result="",
        answers=[],
        captured=[],
        steps_left=1,
        elements=[],
        options={},
        screen_data=[],
        secrets=["senha-do-portal-111"],
    )
    assert "senha-do-portal-111" not in pacote


def test_resposta_da_ia_comprida_e_cortada_em_vez_de_quebrar() -> None:
    decisao = ExplorerDecision.model_validate(
        {"acao": "perguntar", "pergunta": "x" * 5000, "opcoes": ["a" * 500] * 20, "descricao": "y" * 900}
    )
    assert len(decisao.pergunta) == 400
    assert len(decisao.opcoes) == 6
    assert len(decisao.descricao) == 300


def test_resposta_da_ia_com_acao_desconhecida_e_descartada() -> None:
    with pytest.raises(ValueError):
        ExplorerDecision.model_validate({"acao": "executar_javascript", "valor": "fetch('x')"})


def test_segredo_que_escapa_do_filtro_cancela_o_envio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.sanitizer.scrub", lambda texto, _: texto)
    with pytest.raises(SecretLeakError):
        build_explorer_payload(
            prompt="senha-do-portal-111",
            url="https://portal.exemplo",
            title="",
            done=[],
            last_result="",
            answers=[],
            captured=[],
            steps_left=1,
            elements=[],
            options={},
            screen_data=[],
            secrets=["senha-do-portal-111"],
        )


def test_resposta_da_ia_com_campos_nulos_vale_o_padrao() -> None:
    """O gpt-oss do Groq manda null em tudo o que não usa, inclusive em listas."""
    decisao = ExplorerDecision.model_validate(
        {
            "acao": "digitar",
            "indice": 7,
            "valor": "Boston Bruins",
            "endereco": None,
            "dado": None,
            "opcoes": None,
            "descricao": None,
        }
    )
    assert decisao.opcoes == []
    assert decisao.descricao == ""
    assert decisao.indice == 7


def test_nomes_da_ia_ficam_legiveis() -> None:
    decisao = ExplorerDecision.model_validate(
        {
            "acao": "capturar_tabela",
            "dado": 0,
            "nome_do_dado": "tabela_boston_bruins",
            "descricao": "captura a tabela",
        }
    )
    assert decisao.nome_do_dado == "Tabela boston bruins"
    assert decisao.descricao == "Captura a tabela"


def test_celulas_com_endereco_invalido_sao_descartadas() -> None:
    decisao = ExplorerDecision.model_validate(
        {
            "acao": "escrever_celulas",
            "celulas": [
                {"celula": "a1", "valor": "ok"},
                {"celula": "A0", "valor": "x"},
                {"celula": "=HYPERLINK()", "valor": "x"},
                {"celula": "B2", "valor": None},
                "lixo",
            ]
            + [{"celula": f"C{n}", "valor": "v"} for n in range(1, 100)],
        }
    )
    assert decisao.celulas[0].celula == "A1"
    assert decisao.celulas[1].celula == "B2" and decisao.celulas[1].valor == ""
    assert len(decisao.celulas) == 60
