"""Dados guardados sozinhos da tela final: opcionais na repetição e removíveis na revisão."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Browser
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.schemas.flow import RecordingCreate
from app.services.worker_tasks import process_next_run
from tests.fixtures.portal import Portal
from tests.test_captura import preparar

Cabecalho = dict[str, str]
Fabrica = sessionmaker[Session]


def gravacao_tela_final(url: str, *, opcional: bool = True) -> dict[str, Any]:
    """Como a extensão envia: a página aberta e os dados que ela achou sozinha ao salvar."""
    return {
        "name": "Tela final",
        "start_url": f"{url}/tela-final",
        "steps": [
            {"action": "navigate", "url": f"{url}/tela-final"},
            {
                "action": "capture",
                "capture_name": "Protocolo",
                "optional": opcional,
                "target": {"tag": "span", "anchor": "Protocolo:", "anchor_kind": "adjacent"},
            },
            {
                "action": "capture",
                "capture_name": "Situação",
                "optional": opcional,
                "target": {"tag": "p", "anchor": "Situação", "anchor_kind": "inline"},
            },
            {
                "action": "capture",
                "capture_name": "Notas emitidas",
                "capture_kind": "table",
                "optional": opcional,
                "target": {"tag": "table", "neighbors": ["Número", "Valor"], "css": "#notas"},
            },
        ],
    }


def executar(
    api: TestClient, cabecalho: Cabecalho, fabrica: Fabrica, navegador: Browser, flow_id: str
) -> dict:
    resposta = api.post("/api/v1/runs", data={"flow_id": flow_id}, headers=cabecalho)
    assert resposta.status_code == 201, resposta.text
    assert process_next_run(fabrica, navegador) is True
    return api.get(f"/api/v1/runs/{resposta.json()['id']}", headers=cabecalho).json()


def test_dados_da_tela_final_sao_lidos_na_repeticao(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_tela_final(portal.url))
    assert tarefa["steps"][1]["postcondition"] == {"type": "none", "optional": True}

    execucao = executar(api, autenticado, fabrica_sessao, navegador, tarefa["id"])
    assert execucao["status"] == "succeeded", execucao["items"]
    saida = execucao["items"][0]["output"]
    assert saida["protocolo"] == "PROT-9"
    assert saida["situacao"] == "ATIVA"
    assert execucao["items"][0]["table_rows"]["notas_emitidas"] == 2


def test_dado_da_tela_final_que_some_fica_vazio_e_a_tarefa_segue(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_tela_final(portal.url))
    portal.tela_final_sem_protocolo = True

    execucao = executar(api, autenticado, fabrica_sessao, navegador, tarefa["id"])
    assert execucao["status"] == "succeeded", execucao["items"]
    saida = execucao["items"][0]["output"]
    assert saida["protocolo"] == ""
    assert saida["situacao"] == "ATIVA"


def test_dado_capturado_a_mao_que_some_continua_pedindo_ajuda(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = preparar(
        api, autenticado, fabrica_sessao, gravacao_tela_final(portal.url, opcional=False)
    )
    portal.tela_final_sem_protocolo = True

    execucao = executar(api, autenticado, fabrica_sessao, navegador, tarefa["id"])
    assert execucao["status"] != "succeeded"


def test_opcional_so_vale_em_captura() -> None:
    with pytest.raises(ValidationError, match="optional"):
        RecordingCreate.model_validate(
            {
                "name": "x",
                "start_url": "https://portal.exemplo.gov.br",
                "steps": [
                    {"action": "navigate", "url": "https://portal.exemplo.gov.br"},
                    {"action": "click", "optional": True, "target": {"css": "#a"}},
                ],
            }
        )


def test_remove_dado_e_os_passos_seguintes_sobem(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: Fabrica, portal: Portal
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_tela_final(portal.url))
    protocolo = tarefa["steps"][1]

    resposta = api.delete(
        f"/api/v1/flows/{tarefa['id']}/steps/{protocolo['id']}", headers=autenticado
    )
    assert resposta.status_code == 204, resposta.text

    depois = api.get(f"/api/v1/flows/{tarefa['id']}", headers=autenticado).json()
    assert [(passo["position"], passo["capture_key"]) for passo in depois["steps"]] == [
        (1, None),
        (2, "situacao"),
        (3, "notas_emitidas"),
    ]


def test_so_remove_captura_que_nenhum_passo_usa(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: Fabrica, portal: Portal
) -> None:
    gravacao = gravacao_tela_final(portal.url, opcional=False)
    # Um passo depois digita o dado: sem a captura, ele não teria o que digitar
    gravacao["steps"].append(
        {
            "action": "fill",
            "value_from_capture": "Situação",
            "target": {"tag": "input", "label": "Observação", "css": "#obs"},
        }
    )
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao)
    url = f"/api/v1/flows/{tarefa['id']}/steps"

    abrir_pagina = api.delete(f"{url}/{tarefa['steps'][0]['id']}", headers=autenticado)
    assert abrir_pagina.status_code == 400
    usada = api.delete(f"{url}/{tarefa['steps'][2]['id']}", headers=autenticado)
    assert usada.status_code == 400
    assert "Outro passo digita" in usada.json()["detail"]

    depois = api.get(f"/api/v1/flows/{tarefa['id']}", headers=autenticado).json()
    assert len(depois["steps"]) == 5


def test_nao_remove_dado_de_tarefa_de_outra_conta(
    api: TestClient,
    autenticado: Cabecalho,
    criar_conta: Callable[..., Cabecalho],
    fabrica_sessao: Fabrica,
    portal: Portal,
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_tela_final(portal.url))
    resposta = api.delete(
        f"/api/v1/flows/{tarefa['id']}/steps/{tarefa['steps'][1]['id']}", headers=criar_conta()
    )
    assert resposta.status_code == 404
