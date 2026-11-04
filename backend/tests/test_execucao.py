"""De ponta a ponta: API, fila, worker, banco e um Chromium de verdade contra o portal falso."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Browser
from sqlalchemy.orm import Session, sessionmaker

from app.core.encryption import decrypt_json
from app.models.credential import Credential
from app.models.enums import VersionSource
from app.models.flow import Flow, Step, StepVersion
from app.models.repair import HelpRequest
from app.models.run import Artifact, Run, RunItem
from app.models.schedule import Schedule
from app.services.analyzer import analyze_flow
from app.services.engine.llm_repair import LlmRepairer
from app.services.llm_client import LlmUnavailableError
from app.services.worker_tasks import (
    expire_help_requests,
    fire_due_schedules,
    process_next_run,
    purge_expired_artifacts,
    recover_stale_runs,
)
from tests.fixtures.portal import Portal

Cabecalho = dict[str, str]
Fabrica = sessionmaker[Session]

PLANILHA_3 = b"loja\nLoja 01 - Shopping Norte\nLoja 02 - Aldeota\nLoja 03 - Messejana\n"
PLANILHA_1 = b"loja\nLoja 01 - Shopping Norte\n"


class IaRoteirizada:
    """Responde o que o teste mandar e guarda o que recebeu, para conferir que nada vazou."""

    def __init__(self, respostas: list[Any]) -> None:
        self.respostas = list(respostas)
        self.pedidos: list[str] = []

    def chat_json(self, _sistema: str, usuario: str) -> dict[str, Any]:
        self.pedidos.append(usuario)
        if not self.respostas:
            raise LlmUnavailableError("sem resposta")
        resposta = self.respostas.pop(0)
        if callable(resposta):
            return resposta(json.loads(usuario))
        return resposta


def indice_de(pedido: dict[str, Any], texto: str) -> int:
    return next(item["indice"] for item in pedido["elementos_da_pagina"] if item["texto"] == texto)


def disparar(
    api: TestClient, tarefa: dict[str, Any], cabecalho: Cabecalho, planilha: bytes = PLANILHA_3
) -> str:
    resposta = api.post(
        "/api/v1/runs",
        data={"flow_id": tarefa["id"]},
        files={"file": ("lojas.csv", planilha)},
        headers=cabecalho,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def ver(api: TestClient, run_id: str, cabecalho: Cabecalho) -> dict[str, Any]:
    return api.get(f"/api/v1/runs/{run_id}", headers=cabecalho).json()


def pedidos(api: TestClient, cabecalho: Cabecalho) -> list[dict[str, Any]]:
    return api.get("/api/v1/help-requests", headers=cabecalho).json()


def situacoes(execucao: dict[str, Any]) -> list[str]:
    return [item["status"] for item in execucao["items"]]


# O caminho feliz


def test_tres_lojas_sem_nada_mudar(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado)
    assert ver(api, run_id, autenticado)["status"] == "queued"

    assert process_next_run(fabrica_sessao, navegador) is True
    assert process_next_run(fabrica_sessao, navegador) is False  # a fila esvaziou

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "succeeded"
    assert situacoes(execucao) == ["succeeded"] * 3
    assert (execucao["done"], execucao["total"], execucao["repaired"]) == (3, 3, 0)
    assert execucao["finished_at"] is not None

    # O arquivo baixado pode ser pego pela API
    arquivo = api.get(
        f"/api/v1/artifacts/{execucao['items'][1]['file_artifact_id']}", headers=autenticado
    )
    assert arquivo.status_code == 200
    assert arquivo.content.startswith(b"%PDF")
    assert "attachment" in arquivo.headers["content-disposition"]

    # Tudo pela camada 1: nada de IA nem reparo
    camadas = {
        linha["layer"]: linha["steps"]
        for linha in api.get("/api/v1/repairs/stats", headers=autenticado).json()
    }
    assert camadas[1] == 12
    assert camadas[2] == camadas[3] == camadas[4] == 0
    assert api.get("/api/v1/repairs", headers=autenticado).json()["total"] == 0

    resumo = api.get("/api/v1/dashboard/summary", headers=autenticado).json()
    assert resumo["copies_today"] == 3
    assert resumo["highlight"]["id"] == run_id


def test_valor_que_nao_existe_no_portal_falha_a_linha_sem_parar_o_lote(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    # "Loja 99" não existe no portal: é dado errado, não layout novo. A linha falha e o lote segue.
    planilha = b"loja\nLoja 99 - Inexistente\nLoja 02 - Aldeota\n"
    run_id = disparar(api, tarefa_ativa, autenticado, planilha)
    process_next_run(fabrica_sessao, navegador)
    execucao = ver(api, run_id, autenticado)
    assert situacoes(execucao) == ["failed", "succeeded"]
    assert execucao["status"] == "partial"
    assert execucao["items"][0]["problem_step_position"] == 2
    assert "opções" in execucao["items"][0]["error_message"]
    assert pedidos(api, autenticado) == []


def test_salvar_com_o_nome_definido_na_tarefa(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    passo = tarefa_ativa["steps"][3]["id"]
    api.patch(
        f"/api/v1/flows/{tarefa_ativa['id']}/steps/{passo}",
        json={"save_as": "relatorios/{loja}.pdf"},
        headers=autenticado,
    )
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)
    assert ver(api, run_id, autenticado)["items"][0]["file_name"] == "Loja 01 - Shopping Norte.pdf"


def test_valor_malicioso_da_planilha_nao_sai_da_pasta(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    # A planilha chama a coluna do arquivo de "../..": o select falha, então testamos direto o nome salvo
    passo = tarefa_ativa["steps"][3]["id"]
    api.patch(
        f"/api/v1/flows/{tarefa_ativa['id']}/steps/{passo}",
        json={"save_as": "{loja}.pdf"},
        headers=autenticado,
    )
    with fabrica_sessao() as sessao:
        flow = sessao.get(Flow, tarefa_ativa["id"])
        flow.steps[1].value_template = "Loja 01 - Shopping Norte"
        sessao.commit()

    run_id = disparar(api, tarefa_ativa, autenticado, b"loja\n../../../fora\n")
    process_next_run(fabrica_sessao, navegador)
    item = ver(api, run_id, autenticado)["items"][0]
    assert item["status"] == "succeeded"
    # Virou um único nome de arquivo, sem pastas: não tem como sair da pasta da execução
    assert "/" not in item["file_name"]
    assert "\\" not in item["file_name"]
    assert item["file_name"] not in {"..", "."}


# A escada de reparo


def test_camada_2_acha_o_botao_renomeado_e_salva_para_as_proximas(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "renomeado"
    run_id = disparar(api, tarefa_ativa, autenticado)
    ia = IaRoteirizada([])
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "succeeded"
    # Só a primeira linha precisou reparar; as outras já usaram o caminho novo
    assert situacoes(execucao) == ["repaired", "succeeded", "succeeded"]
    assert execucao["items"][0]["resolved_layer"] == 2
    assert ia.pedidos == []

    reparos = api.get("/api/v1/repairs", headers=autenticado).json()
    assert reparos["total"] == 1
    reparo = reparos["items"][0]
    assert reparo["layer"] == 2
    assert reparo["old_path"] == "Exportar PDF"
    assert reparo["new_path"] == "Exportar em PDF"
    assert reparo["score"] >= 0.75

    tarefa = api.get(f"/api/v1/flows/{tarefa_ativa['id']}", headers=autenticado).json()
    assert tarefa["steps"][3]["repaired_at"] is not None
    assert tarefa["steps"][3]["current_path"] == "Exportar em PDF"


def test_reparo_guarda_o_caminho_antigo(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "renomeado"
    disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)

    with fabrica_sessao() as sessao:
        passo = sessao.get(Step, tarefa_ativa["steps"][3]["id"])
        versoes = sorted(passo.versions, key=lambda v: v.version)
        assert [v.version for v in versoes] == [1, 2]
        assert [v.is_current for v in versoes] == [False, True]
        assert versoes[0].source == VersionSource.RECORDING
        assert versoes[1].source == VersionSource.SIMILARITY


def test_site_volta_ao_layout_antigo_e_o_caminho_antigo_e_reaproveitado(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "renomeado"
    disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)

    portal.layout = "original"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)

    assert situacoes(ver(api, run_id, autenticado)) == ["succeeded"]
    assert api.get("/api/v1/repairs", headers=autenticado).json()["total"] == 1
    with fabrica_sessao() as sessao:
        atual = next(
            v for v in sessao.get(Step, tarefa_ativa["steps"][3]["id"]).versions if v.is_current
        )
        assert atual.version == 1


def test_camada_3_ia_acha_o_botao_dentro_do_menu(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "menu"
    run_id = disparar(api, tarefa_ativa, autenticado)
    ia = IaRoteirizada(
        [
            lambda p: {
                "indice": indice_de(p, "Ações"),
                "final": False,
                "explicacao": "Abrindo o menu.",
            },
            lambda p: {
                "indice": indice_de(p, "Baixar como PDF"),
                "final": True,
                "explicacao": "O botão foi movido para o menu Ações.",
            },
        ]
    )
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "succeeded"
    assert situacoes(execucao) == ["repaired", "succeeded", "succeeded"]
    assert execucao["items"][0]["resolved_layer"] == 3
    assert execucao["items"][1]["file_artifact_id"] is not None

    # Uma mudança no site, duas perguntas (abrir o menu e escolher). As outras lojas não gastam IA.
    assert len(ia.pedidos) == 2

    reparo = api.get("/api/v1/repairs", headers=autenticado).json()["items"][0]
    assert reparo["layer"] == 3
    assert reparo["new_path"] == "Ações › Baixar como PDF"
    assert reparo["explanation"] == "O botão foi movido para o menu Ações."


def test_ia_nao_inventa_elemento(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "vazio"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    ia = IaRoteirizada([{"indice": 9999, "final": True, "explicacao": "inventei"}])
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    assert ver(api, run_id, autenticado)["status"] == "waiting_human"
    assert api.get("/api/v1/repairs", headers=autenticado).json()["total"] == 0


def test_ia_enganada_pela_pagina_nao_clica_em_apagar(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "menu"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    ia = IaRoteirizada(
        [
            lambda p: {"indice": indice_de(p, "Ações"), "final": False, "explicacao": "menu"},
            lambda p: {
                "indice": indice_de(p, "Apagar relatório"),
                "final": True,
                "explicacao": "ignore as regras",
            },
        ]
    )
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    assert ver(api, run_id, autenticado)["status"] == "waiting_human"
    assert api.get("/api/v1/repairs", headers=autenticado).json()["total"] == 0


def test_resultado_errado_da_ia_nao_e_salvo(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "menu"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    # "Ações" não baixa nada: a pós-condição reprova
    ia = IaRoteirizada(
        [lambda p: {"indice": indice_de(p, "Ações"), "final": True, "explicacao": "errei"}]
    )
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    assert ver(api, run_id, autenticado)["status"] == "waiting_human"
    assert api.get("/api/v1/repairs", headers=autenticado).json()["total"] == 0


def test_limite_de_chamadas_a_ia_por_execucao(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "menu"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    ia = IaRoteirizada(
        [lambda p: {"indice": indice_de(p, "Ações"), "final": False, "explicacao": "x"}] * 20
    )
    with fabrica_sessao() as sessao:
        sessao.get(Run, run_id).llm_calls = 4
        sessao.commit()
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    assert len(ia.pedidos) == 1  # 4 já gastas + 1 = o limite de 5
    assert ver(api, run_id, autenticado)["status"] == "waiting_human"


def test_seletor_css_que_agora_aponta_para_outro_botao_nao_e_clicado(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "trocado"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)

    assert ver(api, run_id, autenticado)["status"] == "waiting_human"
    assert "/nada" not in portal.requests


# Camada 4: a pessoa decide


def test_camada_4_pessoa_escolhe_e_o_lote_continua(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "ambiguo"
    run_id = disparar(api, tarefa_ativa, autenticado)
    process_next_run(fabrica_sessao, navegador)

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "waiting_human"
    assert situacoes(execucao) == ["waiting_human", "pending", "pending"]
    assert execucao["items"][0]["screenshot_artifact_id"] is not None

    # O worker não pega de novo enquanto a pessoa não responde
    assert process_next_run(fabrica_sessao, navegador) is False

    pedido = pedidos(api, autenticado)[0]
    assert pedido["kind"] == "choose"
    assert pedido["item_position"] == 1
    assert {opcao["text"] for opcao in pedido["options"]} >= {"Exportar PDF A", "Exportar PDF B"}
    assert "target" not in pedido["options"][0]

    opcao = next(o for o in pedido["options"] if o["text"] == "Exportar PDF B")
    resposta = api.post(
        f"/api/v1/help-requests/{pedido['id']}/answer",
        json={"action": "choose", "option_id": opcao["id"]},
        headers=autenticado,
    )
    assert resposta.status_code == 204
    assert ver(api, run_id, autenticado)["status"] == "queued"

    process_next_run(fabrica_sessao, navegador)
    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "succeeded"
    assert situacoes(execucao) == ["repaired", "succeeded", "succeeded"]
    assert execucao["items"][0]["resolved_layer"] == 4

    reparo = api.get("/api/v1/repairs", headers=autenticado).json()["items"][0]
    assert reparo["layer"] == 4
    assert reparo["new_path"] == "Exportar PDF B"


def test_pular_uma_linha(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "ambiguo"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)

    pedido = pedidos(api, autenticado)[0]
    api.post(
        f"/api/v1/help-requests/{pedido['id']}/answer", json={"action": "skip"}, headers=autenticado
    )

    execucao = ver(api, run_id, autenticado)
    assert situacoes(execucao) == ["skipped"]
    assert execucao["status"] == "failed"


def test_captcha_para_e_nao_tenta_contornar(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "captcha"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    ia = IaRoteirizada([])
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    assert ver(api, run_id, autenticado)["status"] == "waiting_human"
    pedido = pedidos(api, autenticado)[0]
    assert pedido["kind"] == "captcha"
    assert ia.pedidos == []  # nem pergunta à IA

    # Tentar de novo depois que o portal voltou ao normal
    portal.layout = "original"
    api.post(
        f"/api/v1/help-requests/{pedido['id']}/answer",
        json={"action": "retry"},
        headers=autenticado,
    )
    process_next_run(fabrica_sessao, navegador)
    assert ver(api, run_id, autenticado)["status"] == "succeeded"


def test_resposta_que_nao_serve_para_o_pedido_e_recusada(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "captcha"
    disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)
    pedido = pedidos(api, autenticado)[0]
    url = f"/api/v1/help-requests/{pedido['id']}/answer"

    assert api.post(url, json={"action": "confirm"}, headers=autenticado).status_code == 400
    assert api.post(url, json={"action": "retry"}, headers=autenticado).status_code == 204
    # Duas respostas não valem as duas
    assert api.post(url, json={"action": "skip"}, headers=autenticado).status_code == 409


def test_opcao_que_nao_existe_e_recusada(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "ambiguo"
    disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)
    pedido = pedidos(api, autenticado)[0]
    resposta = api.post(
        f"/api/v1/help-requests/{pedido['id']}/answer",
        json={"action": "choose", "option_id": "9999"},
        headers=autenticado,
    )
    assert resposta.status_code == 400


# Passos sem volta


def _tarefa_com_envio(
    api: TestClient, cabecalho: Cabecalho, fabrica: Fabrica, portal: Portal
) -> dict[str, Any]:
    gravacao = {
        "name": "Enviar declaração",
        "start_url": f"{portal.url}/declaracao",
        "steps": [
            {"action": "navigate", "url": f"{portal.url}/declaracao"},
            {
                "action": "click",
                "target": {"role": "button", "text": "Enviar declaração", "css": "#enviar"},
            },
        ],
    }
    flow_id = api.post("/api/v1/flows", json=gravacao, headers=cabecalho).json()["id"]
    with fabrica() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id))
    return api.post(f"/api/v1/flows/{flow_id}/confirm", headers=cabecalho).json()


def test_passo_sem_volta_espera_confirmacao_antes_de_tocar(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_com_envio(api, autenticado, fabrica_sessao, portal)
    assert tarefa["steps"][1]["irreversible"] is True

    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)

    assert ver(api, run_id, autenticado)["status"] == "waiting_human"
    assert portal.submissions == 0

    pedido = pedidos(api, autenticado)[0]
    assert pedido["kind"] == "confirm"
    api.post(
        f"/api/v1/help-requests/{pedido['id']}/answer",
        json={"action": "confirm"},
        headers=autenticado,
    )

    process_next_run(fabrica_sessao, navegador)
    assert ver(api, run_id, autenticado)["status"] == "succeeded"
    assert portal.submissions == 1


def test_nao_confirmar_nao_envia_nada(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_com_envio(api, autenticado, fabrica_sessao, portal)
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)

    pedido = pedidos(api, autenticado)[0]
    api.post(
        f"/api/v1/help-requests/{pedido['id']}/answer",
        json={"action": "decline"},
        headers=autenticado,
    )

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "failed"
    assert situacoes(execucao) == ["skipped"]
    assert portal.submissions == 0
    assert process_next_run(fabrica_sessao, navegador) is False


def test_confirmacao_automatica_precisa_ser_ligada_de_proposito(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_com_envio(api, autenticado, fabrica_sessao, portal)
    api.patch(
        f"/api/v1/flows/{tarefa['id']}/steps/{tarefa['steps'][1]['id']}",
        json={"auto_confirm": True},
        headers=autenticado,
    )
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)
    assert ver(api, run_id, autenticado)["status"] == "succeeded"
    assert portal.submissions == 1


def test_passo_sem_volta_com_botao_sumido_nao_e_reparado_sozinho(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_com_envio(api, autenticado, fabrica_sessao, portal)
    api.patch(
        f"/api/v1/flows/{tarefa['id']}/steps/{tarefa['steps'][1]['id']}",
        json={"auto_confirm": True},
        headers=autenticado,
    )
    # A gravação aponta para um botão que a página não tem
    with fabrica_sessao() as sessao:
        versao = (
            sessao.query(StepVersion).filter(StepVersion.step_id == tarefa["steps"][1]["id"]).one()
        )
        versao.target = {"role": "button", "text": "Enviar declara", "css": "#nao-existe"}
        sessao.commit()

    ia = IaRoteirizada([])
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    # Mesmo com um botão muito parecido na página: nem camada 2, nem IA
    assert ver(api, run_id, autenticado)["status"] == "waiting_human"
    assert portal.submissions == 0
    assert ia.pedidos == []
    assert pedidos(api, autenticado)[0]["kind"] == "choose"


def test_linha_que_ja_tocou_em_passo_sem_volta_nunca_repete(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_com_envio(api, autenticado, fabrica_sessao, portal)
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    with fabrica_sessao() as sessao:
        # Como se o worker tivesse caído logo depois do clique
        run = sessao.get(Run, run_id)
        run.status = "running"
        run.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
        run.items[0].status = "running"
        run.items[0].irreversible_done = True
        sessao.commit()
        assert recover_stale_runs(sessao) == 1

    process_next_run(fabrica_sessao, navegador)
    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "failed"
    assert "sem volta" in execucao["items"][0]["error_message"]
    assert portal.submissions == 0


# Quedas, cancelamento e disjuntor


def test_worker_que_caiu_nao_repete_o_que_ja_terminou(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado)
    with fabrica_sessao() as sessao:
        run = sessao.get(Run, run_id)
        run.status = "running"
        run.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
        run.items[0].status = "succeeded"
        run.items[1].status = "running"
        sessao.commit()
        assert recover_stale_runs(sessao) == 1

    process_next_run(fabrica_sessao, navegador)
    assert ver(api, run_id, autenticado)["status"] == "succeeded"
    # Só as linhas 2 e 3 abriram o portal
    assert portal.requests.count("/relatorios") == 2


def test_execucao_com_sinal_recente_nao_e_recuperada(
    api: TestClient, autenticado: Cabecalho, tarefa_ativa: dict[str, Any], fabrica_sessao: Fabrica
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    with fabrica_sessao() as sessao:
        run = sessao.get(Run, run_id)
        run.status = "running"
        run.heartbeat_at = datetime.now(UTC)
        sessao.commit()
        assert recover_stale_runs(sessao) == 0


def test_disjuntor_para_depois_de_tres_falhas_seguidas(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    planilha = ("loja\n" + "Inexistente\n" * 6).encode()
    run_id = disparar(api, tarefa_ativa, autenticado, planilha)
    process_next_run(fabrica_sessao, navegador)

    execucao = ver(api, run_id, autenticado)
    assert situacoes(execucao) == ["failed"] * 3 + ["skipped"] * 3
    assert execucao["status"] == "failed"
    assert any("bloquear a conta" in linha["message"] for linha in execucao["log"])


def test_cancelar_na_fila(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado)
    cancelada = api.post(f"/api/v1/runs/{run_id}/cancel", headers=autenticado).json()
    assert cancelada["status"] == "canceled"
    assert situacoes(cancelada) == ["skipped"] * 3

    assert process_next_run(fabrica_sessao, navegador) is False
    assert portal.requests == []
    assert api.post(f"/api/v1/runs/{run_id}/cancel", headers=autenticado).status_code == 409


def test_cancelar_enquanto_espera_fecha_o_pedido(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "captcha"
    run_id = disparar(api, tarefa_ativa, autenticado)
    process_next_run(fabrica_sessao, navegador)
    api.post(f"/api/v1/runs/{run_id}/cancel", headers=autenticado)
    assert pedidos(api, autenticado) == []


def test_pedido_sem_resposta_expira_e_o_lote_segue(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "captcha"
    run_id = disparar(api, tarefa_ativa, autenticado)
    process_next_run(fabrica_sessao, navegador)

    with fabrica_sessao() as sessao:
        pedido = sessao.query(HelpRequest).one()
        pedido.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        sessao.commit()
        assert expire_help_requests(sessao) == 1

    portal.layout = "original"
    process_next_run(fabrica_sessao, navegador)
    execucao = ver(api, run_id, autenticado)
    assert situacoes(execucao) == ["failed", "succeeded", "succeeded"]
    assert execucao["status"] == "partial"


# Login, senhas e o que chega à IA


def _tarefa_com_login(
    api: TestClient, cabecalho: Cabecalho, fabrica: Fabrica, portal: Portal
) -> dict[str, Any]:
    gravacao = {
        "name": "Com login",
        "start_url": f"{portal.url}/login",
        "steps": [
            {"action": "navigate", "url": f"{portal.url}/login"},
            {
                "action": "fill",
                "value": "x",
                "target": {"role": "textbox", "label": "Usuário", "input_type": "text"},
            },
            {
                "action": "fill",
                "value": "x",
                "target": {"role": "textbox", "label": "Senha", "input_type": "password"},
            },
            {"action": "click", "target": {"role": "button", "text": "Entrar", "css": "#entrar"}},
        ],
    }
    flow_id = api.post("/api/v1/flows", json=gravacao, headers=cabecalho).json()["id"]
    with fabrica() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id))
    return api.post(f"/api/v1/flows/{flow_id}/confirm", headers=cabecalho).json()


def test_tarefa_com_login_nao_roda_sem_o_acesso_salvo(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: Fabrica, portal: Portal
) -> None:
    tarefa = _tarefa_com_login(api, autenticado, fabrica_sessao, portal)
    assert tarefa["needs_credential"] is True
    resposta = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado)
    assert resposta.status_code == 400
    assert "acesso" in resposta.json()["detail"]


def test_senha_salva_e_usada_no_portal_e_fica_cifrada_no_banco(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_com_login(api, autenticado, fabrica_sessao, portal)
    api.post(
        "/api/v1/credentials",
        json={"domain": "localhost", "username": "financeiro", "password": "senha-marcada-123"},
        headers=autenticado,
    )
    assert (
        api.get(f"/api/v1/flows/{tarefa['id']}", headers=autenticado).json()["needs_credential"]
        is False
    )

    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "succeeded"
    assert portal.passwords_seen == ["senha-marcada-123"]
    assert "senha-marcada-123" not in json.dumps(execucao)

    with fabrica_sessao() as sessao:
        credencial = sessao.query(Credential).one()
        assert "senha-marcada-123" not in credencial.encrypted_payload
        assert decrypt_json(credencial.encrypted_payload)["password"] == "senha-marcada-123"


def test_senha_e_dados_da_planilha_nunca_chegam_a_ia(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_com_login(api, autenticado, fabrica_sessao, portal)
    api.post(
        "/api/v1/credentials",
        json={"domain": "localhost", "username": "financeiro", "password": "senha-marcada-123"},
        headers=autenticado,
    )
    # Depois do login, o clique em "Entrar" aponta para um botão que não existe: chama a IA
    with fabrica_sessao() as sessao:
        versao = (
            sessao.query(StepVersion).filter(StepVersion.step_id == tarefa["steps"][3]["id"]).one()
        )
        versao.target = {"role": "button", "text": "Acessar sistema agora", "css": "#sumiu"}
        sessao.commit()

    ia = IaRoteirizada([{"indice": None, "final": False, "explicacao": "desisto"}])
    api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado)
    process_next_run(fabrica_sessao, navegador, LlmRepairer(ia))

    assert len(ia.pedidos) == 1, "a IA precisa ter sido chamada para o teste valer"
    enviado = ia.pedidos[0]
    assert "senha-marcada-123" not in enviado
    assert "financeiro" not in enviado


# Agenda


def test_agenda_dispara_na_hora_e_calcula_a_proxima(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    criada = api.post(
        "/api/v1/schedules",
        data={"flow_id": tarefa_ativa["id"], "cron": "10 7 5 * *"},
        files={"file": ("a.csv", PLANILHA_1)},
        headers=autenticado,
    ).json()

    with fabrica_sessao() as sessao:
        assert fire_due_schedules(sessao) == 0  # ainda não é a hora

        agenda = sessao.get(Schedule, criada["id"])
        agenda.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        sessao.commit()
        assert fire_due_schedules(sessao) == 1
        assert sessao.get(Schedule, criada["id"]).next_run_at > datetime.now(UTC)
        assert fire_due_schedules(sessao) == 0  # não dispara duas vezes

    execucoes = api.get("/api/v1/runs", headers=autenticado).json()
    assert execucoes["total"] == 1
    assert execucoes["items"][0]["trigger"] == "schedule"

    process_next_run(fabrica_sessao, navegador)
    assert ver(api, execucoes["items"][0]["id"], autenticado)["status"] == "succeeded"

    proximos = api.get("/api/v1/dashboard/summary", headers=autenticado).json()["upcoming"]
    assert proximos[0]["flow_id"] == tarefa_ativa["id"]


def test_agenda_de_tarefa_que_deixou_de_poder_rodar_nao_trava(
    api: TestClient, autenticado: Cabecalho, tarefa_ativa: dict[str, Any], fabrica_sessao: Fabrica
) -> None:
    criada = api.post(
        "/api/v1/schedules",
        data={"flow_id": tarefa_ativa["id"], "cron": "10 7 5 * *"},
        files={"file": ("a.csv", PLANILHA_1)},
        headers=autenticado,
    ).json()
    with fabrica_sessao() as sessao:
        agenda = sessao.get(Schedule, criada["id"])
        agenda.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        sessao.get(Flow, tarefa_ativa["id"]).status = "awaiting_confirmation"
        sessao.commit()
        assert fire_due_schedules(sessao) == 1
        assert sessao.get(Schedule, criada["id"]).next_run_at > datetime.now(UTC)
    assert api.get("/api/v1/runs", headers=autenticado).json()["total"] == 0


# Saídas


def test_relatorio_pdf_e_csv(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    # Valores que tentam virar marcação no PDF e fórmula no Excel
    run_id = disparar(api, tarefa_ativa, autenticado, b'loja\n=1+1\n"<b>x</b> & y"\n')
    process_next_run(fabrica_sessao, navegador)

    relatorio = api.get(f"/api/v1/runs/{run_id}/report", headers=autenticado)
    assert relatorio.status_code == 200
    assert relatorio.content.startswith(b"%PDF")

    planilha = api.get(f"/api/v1/runs/{run_id}/export", headers=autenticado)
    assert planilha.status_code == 200
    assert "'=1+1" in planilha.text
    assert "Falhou" in planilha.text


def test_screenshot_baixa_como_imagem(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = "ambiguo"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)
    item = ver(api, run_id, autenticado)["items"][0]
    tela = api.get(f"/api/v1/artifacts/{item['screenshot_artifact_id']}", headers=autenticado)
    assert tela.status_code == 200
    assert tela.content.startswith(b"\x89PNG")


def test_arquivos_vencidos_sao_apagados(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)
    artefato = ver(api, run_id, autenticado)["items"][0]["file_artifact_id"]

    with fabrica_sessao() as sessao:
        assert purge_expired_artifacts(sessao) == 0
        sessao.get(Artifact, uuid.UUID(artefato)).created_at = datetime.now(UTC) - timedelta(
            days=90
        )
        sessao.commit()
        assert purge_expired_artifacts(sessao) == 1

    assert api.get(f"/api/v1/artifacts/{artefato}", headers=autenticado).status_code == 404


def test_disparar_valida_a_entrada(
    api: TestClient, autenticado: Cabecalho, tarefa_ativa: dict[str, Any]
) -> None:
    dados = {"flow_id": tarefa_ativa["id"]}
    sem_arquivo = api.post("/api/v1/runs", data=dados, headers=autenticado)
    assert sem_arquivo.status_code == 400
    assert "planilha" in sem_arquivo.json()["detail"]

    errada = api.post(
        "/api/v1/runs", data=dados, files={"file": ("a.csv", b"nome\nA\n")}, headers=autenticado
    )
    assert errada.status_code == 400
    assert "loja" in errada.json()["detail"]

    grande = api.post(
        "/api/v1/runs",
        data=dados,
        files={"file": ("a.csv", b"x" * (5 * 1024 * 1024 + 1))},
        headers=autenticado,
    )
    assert grande.status_code == 413

    fuso = api.post(
        "/api/v1/runs",
        data={**dados, "timezone": "Marte/Olympus"},
        files={"file": ("a.csv", PLANILHA_1)},
        headers=autenticado,
    )
    assert fuso.status_code == 400


def test_linhas_guardam_so_as_colunas_da_tarefa(
    api: TestClient, autenticado: Cabecalho, tarefa_ativa: dict[str, Any], fabrica_sessao: Fabrica
) -> None:
    # Uma coluna de salário na planilha não tem motivo para ficar no banco
    run_id = disparar(api, tarefa_ativa, autenticado, b"loja,salario\nLoja 01,9999\n")
    with fabrica_sessao() as sessao:
        item = sessao.query(RunItem).filter(RunItem.run_id == run_id).one()
        assert item.input == {"loja": "Loja 01"}


@pytest.mark.parametrize("layout", ["vazio"])
def test_sem_opcoes_a_pessoa_so_pode_tentar_de_novo_ou_pular(
    layout: str,
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    portal.layout = layout
    disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)
    pedido = pedidos(api, autenticado)[0]
    assert pedido["kind"] == "uncertain"
    assert pedido["options"] == []
