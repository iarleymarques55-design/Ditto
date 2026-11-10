"""Captura de dados da tela: lê, guarda por linha, exporta e reaproveita em passos seguintes."""

import io
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from playwright.sync_api import Browser
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import HelpKind, StepAction
from app.models.flow import Flow
from app.schemas.flow import RecordingCreate
from app.services.analyzer import analyze_flow
from app.services.engine.browser import new_guarded_context
from app.services.engine.capture import read_table, read_value
from app.services.engine.executor import StepPlan, StepRunner
from app.services.worker_tasks import process_next_run
from tests.fixtures.portal import Portal

Cabecalho = dict[str, str]
Fabrica = sessionmaker[Session]


def gravacao_consulta(url: str) -> dict[str, Any]:
    """Consulta um CNPJ e captura o que o portal responde."""
    return {
        "name": "Situação de CNPJs",
        "start_url": f"{url}/busca",
        "steps": [
            {"action": "navigate", "url": f"{url}/busca"},
            {
                "action": "fill",
                "value": "111",
                "target": {
                    "role": "textbox",
                    "tag": "input",
                    "label": "CNPJ",
                    "name": "cnpj",
                    "css": "#cnpj",
                },
            },
            {
                "action": "click",
                "target": {
                    "role": "button",
                    "tag": "button",
                    "text": "Consultar",
                    "css": "#consultar",
                },
            },
            {
                "action": "capture",
                "capture_name": "Situação",
                "target": {
                    "tag": "dd",
                    "anchor": "Situação",
                    "anchor_kind": "definition",
                    "css": "dl > dd:nth-of-type(1)",
                },
            },
            {
                "action": "capture",
                "capture_name": "Razão social",
                "target": {"tag": "span", "anchor": "Razão social", "anchor_kind": "inline"},
            },
            {
                "action": "capture",
                "capture_name": "Notas",
                "capture_kind": "table",
                "target": {"tag": "table", "neighbors": ["Número", "Valor"], "css": "#notas"},
            },
        ],
    }


def preparar(
    api: TestClient, cabecalho: Cabecalho, fabrica: Fabrica, gravacao: dict[str, Any]
) -> dict[str, Any]:
    resposta = api.post("/api/v1/flows", json=gravacao, headers=cabecalho)
    assert resposta.status_code == 201, resposta.text
    flow_id = resposta.json()["id"]
    with fabrica() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id))
    tarefa = api.get(f"/api/v1/flows/{flow_id}", headers=cabecalho).json()
    for variavel in tarefa["variables"]:
        api.post(
            f"/api/v1/flows/{flow_id}/variables/{variavel['id']}/answer",
            json={"is_variable": True, "source": "column"},
            headers=cabecalho,
        )
    return api.post(f"/api/v1/flows/{flow_id}/confirm", headers=cabecalho).json()


def disparar(api: TestClient, tarefa: dict[str, Any], cabecalho: Cabecalho, planilha: bytes) -> str:
    resposta = api.post(
        "/api/v1/runs",
        data={"flow_id": tarefa["id"]},
        files={"file": ("a.csv", planilha)},
        headers=cabecalho,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def test_captura_um_valor_para_cada_linha(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_consulta(portal.url))
    assert [v["name"] for v in tarefa["variables"]] == ["cnpj"]
    assert tarefa["steps"][3]["capture_key"] == "situacao"
    assert tarefa["steps"][3]["intent"] == 'Capturar "Situação"'

    run_id = disparar(api, tarefa, autenticado, b"cnpj\n111\n222\n")
    process_next_run(fabrica_sessao, navegador)

    execucao = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()
    assert execucao["status"] == "succeeded", execucao["items"]
    # O valor muda a cada linha: se o motor procurasse pelo texto gravado, a segunda linha falharia
    assert execucao["items"][0]["output"]["situacao"] == "ATIVA"
    assert execucao["items"][1]["output"]["situacao"] == "BAIXADA"
    assert execucao["items"][0]["output"]["razao_social"] == "Empresa 111 Ltda"
    assert {c["key"] for c in execucao["captures"]} == {"situacao", "razao_social", "notas"}

    # Tabela: o resumo traz só a contagem; o conteúdo vem na rota da linha
    assert execucao["items"][0]["table_rows"]["notas"] == 2
    assert "notas" not in execucao["items"][0]["output"]
    linha = api.get(
        f"/api/v1/runs/{run_id}/items/{execucao['items'][0]['id']}/output", headers=autenticado
    ).json()
    assert linha["notas"][1] == {"Número": "NF-2", "Valor": "R$ 20,00"}


def test_exporta_em_excel_e_csv(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_consulta(portal.url))
    run_id = disparar(api, tarefa, autenticado, b"cnpj\n111\n222\n")
    process_next_run(fabrica_sessao, navegador)

    excel = api.get(f"/api/v1/runs/{run_id}/export?format=xlsx", headers=autenticado)
    assert excel.status_code == 200
    assert "attachment" in excel.headers["content-disposition"]
    arquivo = load_workbook(io.BytesIO(excel.content))
    resultado = list(arquivo["Resultado"].values)
    assert resultado[0][:3] == ("Linha", "Nome", "Situação da linha")
    assert "Situação" in resultado[0]
    coluna = resultado[0].index("Situação")
    assert resultado[1][coluna] == "ATIVA"
    assert resultado[2][coluna] == "BAIXADA"

    notas = list(arquivo["Notas"].values)
    assert notas[0] == ("Linha", "Nome", "Número", "Valor")
    assert len(notas) == 1 + 4  # duas notas por CNPJ

    planilha = api.get(f"/api/v1/runs/{run_id}/export", headers=autenticado)
    assert "BAIXADA" in planilha.text


def test_dado_capturado_que_viraria_formula_e_neutralizado(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    # Um portal malicioso pode exibir uma fórmula para executar ao abrir no Excel
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_consulta(portal.url))
    run_id = disparar(api, tarefa, autenticado, b"cnpj\nformula\n")
    process_next_run(fabrica_sessao, navegador)

    excel = api.get(f"/api/v1/runs/{run_id}/export?format=xlsx", headers=autenticado)
    linhas = list(load_workbook(io.BytesIO(excel.content))["Resultado"].values)
    coluna = linhas[0].index("Situação")
    assert linhas[1][coluna].startswith("'=")

    planilha = api.get(f"/api/v1/runs/{run_id}/export", headers=autenticado)
    assert "'=HYPERLINK" in planilha.text


def test_valor_capturado_alimenta_passo_seguinte(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    """Passar dados entre sistemas: lê em um lugar e digita em outro."""
    gravacao = gravacao_consulta(portal.url)
    gravacao["steps"] = gravacao["steps"][:4] + [
        {"action": "navigate", "url": f"{portal.url}/erp"},
        {
            "action": "fill",
            "value_from_capture": "Situação",
            "target": {
                "role": "textbox",
                "tag": "input",
                "label": "Situação no ERP",
                "css": "#situacao",
            },
        },
        {
            "action": "click",
            "target": {"role": "button", "tag": "button", "text": "Salvar", "css": "#salvar"},
        },
    ]
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao)
    # O campo alimentado pela captura não vira pergunta para a pessoa
    assert [v["name"] for v in tarefa["variables"]] == ["cnpj"]

    run_id = disparar(api, tarefa, autenticado, b"cnpj\n222\n")
    process_next_run(fabrica_sessao, navegador)

    assert api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()["status"] == "succeeded"
    assert portal.saved_values == ["BAIXADA"]


def test_ancora_que_sumiu_para_e_pergunta_em_vez_de_salvar_dado_errado(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_consulta(portal.url))
    # No layout novo, o CSS antigo agora aponta para outro dado, mas o rótulo "Situação" sumiu
    portal.consulta_layout = "sem_rotulo"
    run_id = disparar(api, tarefa, autenticado, b"cnpj\n111\n")
    process_next_run(fabrica_sessao, navegador)

    execucao = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()
    assert execucao["status"] == "waiting_human"
    assert "situacao" not in execucao["items"][0]["output"]
    pedido = api.get("/api/v1/help-requests", headers=autenticado).json()[0]
    assert pedido["kind"] == "uncertain"


def test_nao_le_campo_de_senha_nem_dados_de_cartao(navegador: Browser, portal: Portal) -> None:
    contexto = new_guarded_context(navegador, ["localhost"])
    pagina = contexto.new_page()
    try:
        pagina.goto(f"{portal.url}/campos-sigilosos")
        assert read_value(pagina, {"anchor": "Senha", "anchor_kind": "label"}) is None
        assert read_value(pagina, {"anchor": "Cartão", "anchor_kind": "label"}) is None
        assert read_value(pagina, {"css": "#senha"}) is None
        assert read_value(pagina, {"anchor": "Protocolo", "anchor_kind": "label"}) == "ABC-1"
    finally:
        contexto.close()


@pytest.mark.parametrize(
    ("alvo", "esperado"),
    [
        ({"anchor": "Valor", "anchor_kind": "table_header", "row_index": 1}, "R$ 20,00"),
        ({"anchor": "Situação", "anchor_kind": "definition"}, "ATIVA"),
        ({"anchor": "Razão social", "anchor_kind": "inline"}, "Empresa 111 Ltda"),
        ({"anchor": "Vencimento", "anchor_kind": "adjacent"}, "10/12/2026"),
        ({"test_id": "protocolo"}, "PROT-111"),
        ({"anchor": "Nada disso existe", "anchor_kind": "definition"}, None),
    ],
)
def test_jeitos_de_achar_o_dado(
    alvo: dict, esperado: str | None, navegador: Browser, portal: Portal
) -> None:
    contexto = new_guarded_context(navegador, ["localhost"])
    pagina = contexto.new_page()
    try:
        pagina.goto(f"{portal.url}/consulta?cnpj=111")
        assert read_value(pagina, alvo) == esperado
    finally:
        contexto.close()


def test_le_dentro_de_iframe(navegador: Browser, portal: Portal) -> None:
    contexto = new_guarded_context(navegador, ["localhost"])
    pagina = contexto.new_page()
    try:
        pagina.goto(f"{portal.url}/com-iframe")
        pagina.wait_for_selector("iframe")
        pagina.wait_for_timeout(300)
        assert read_value(pagina, {"anchor": "Situação", "anchor_kind": "definition"}) == "ATIVA"
    finally:
        contexto.close()


def test_tabela_errada_da_pagina_nao_serve(navegador: Browser, portal: Portal) -> None:
    contexto = new_guarded_context(navegador, ["localhost"])
    pagina = contexto.new_page()
    try:
        pagina.goto(f"{portal.url}/consulta?cnpj=111")
        assert read_table(pagina, {"neighbors": ["Outra", "Coisa"]}) is None
        linhas = read_table(pagina, {"neighbors": ["Número", "Valor"]})
        assert [linha["Número"] for linha in linhas] == ["NF-1", "NF-2"]
    finally:
        contexto.close()


def test_senha_salva_nao_aparece_nos_dados_capturados(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    """Se o portal exibir a senha na tela, ela não vai parar na planilha."""
    gravacao = gravacao_consulta(portal.url)
    gravacao["steps"][3]["target"] = {"tag": "span", "anchor": "Acesso", "anchor_kind": "inline"}
    gravacao["steps"][3]["capture_name"] = "Acesso"
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao)
    # Credencial do domínio, embora esta tarefa não faça login: o valor protegido é o que importa
    api.post(
        "/api/v1/credentials",
        json={"domain": "localhost", "username": "u", "password": "senha-do-portal-111"},
        headers=autenticado,
    )
    run_id = disparar(api, tarefa, autenticado, b"cnpj\n111\n")
    process_next_run(fabrica_sessao, navegador)

    execucao = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()
    assert "senha-do-portal-111" not in json.dumps(execucao)
    assert "[oculto]" in execucao["items"][0]["output"]["acesso"]


@pytest.mark.parametrize(
    "passos",
    [
        # Captura sem nome
        [{"action": "capture", "target": {"anchor": "x", "anchor_kind": "label"}}],
        # Nome em passo que não é captura
        [{"action": "click", "capture_name": "x", "target": {"text": "a"}}],
        # Dois dados com o mesmo nome
        [
            {
                "action": "capture",
                "capture_name": "x",
                "target": {"anchor": "a", "anchor_kind": "label"},
            },
            {
                "action": "capture",
                "capture_name": "X",
                "target": {"anchor": "b", "anchor_kind": "label"},
            },
        ],
        # Usa um dado antes de capturar
        [
            {"action": "fill", "value_from_capture": "x", "target": {"label": "a"}},
            {
                "action": "capture",
                "capture_name": "x",
                "target": {"anchor": "b", "anchor_kind": "label"},
            },
        ],
        # Tabela inteira não cabe em um campo
        [
            {
                "action": "capture",
                "capture_name": "x",
                "capture_kind": "table",
                "target": {"neighbors": ["a"]},
            },
            {"action": "fill", "value_from_capture": "x", "target": {"label": "a"}},
        ],
        # Âncora de tipo desconhecido
        [
            {
                "action": "capture",
                "capture_name": "x",
                "target": {"anchor": "a", "anchor_kind": "inventado"},
            }
        ],
    ],
)
def test_gravacao_de_captura_invalida(passos: list[dict]) -> None:
    with pytest.raises(ValidationError):
        RecordingCreate(name="x", start_url="https://a.exemplo", steps=passos)


def test_token_da_gravacao_so_serve_para_enviar_gravacao(
    api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = api.post("/api/v1/auth/recording-token", headers=autenticado)
    assert resposta.status_code == 201
    token = {"Authorization": f"Bearer {resposta.json()['token']}"}

    gravacao = gravacao_consulta("https://portal.exemplo")
    assert api.post("/api/v1/flows", json=gravacao, headers=token).status_code == 201

    for metodo, rota in [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/flows"),
        ("GET", "/api/v1/credentials"),
        ("GET", "/api/v1/account/avatar"),
        ("POST", "/api/v1/auth/recording-token"),
    ]:
        assert api.request(metodo, rota, headers=token).status_code == 401, rota


def test_dominios_visitados_entram_na_lista_da_tarefa(
    api: TestClient, autenticado: Cabecalho
) -> None:
    gravacao = {
        **gravacao_consulta("https://portal.exemplo"),
        "allowed_hosts": ["LOGIN.Exemplo.com"],
    }
    resposta = api.post("/api/v1/flows", json=gravacao, headers=autenticado)
    assert resposta.status_code == 201
    assert resposta.json()["allowed_domains"] == ["login.exemplo.com", "portal.exemplo"]


@pytest.mark.parametrize(
    "dominios", [["não é domínio"], ["http://a.exemplo/x"], ["a.exemplo"] * 21]
)
def test_dominios_invalidos_sao_recusados(
    dominios: list[str], api: TestClient, autenticado: Cabecalho
) -> None:
    gravacao = {**gravacao_consulta("https://portal.exemplo"), "allowed_hosts": dominios}
    assert api.post("/api/v1/flows", json=gravacao, headers=autenticado).status_code == 422


def test_rota_de_dados_da_linha_e_da_propria_conta(
    api: TestClient,
    autenticado: Cabecalho,
    criar_conta,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = preparar(api, autenticado, fabrica_sessao, gravacao_consulta(portal.url))
    run_id = disparar(api, tarefa, autenticado, b"cnpj\n111\n")
    process_next_run(fabrica_sessao, navegador)
    item = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()["items"][0]["id"]

    outra = criar_conta()
    assert api.get(f"/api/v1/runs/{run_id}/items/{item}/output", headers=outra).status_code == 404
    assert api.get(f"/api/v1/runs/{run_id}/export?format=xlsx", headers=outra).status_code == 404
    assert (
        api.get(f"/api/v1/runs/{run_id}/export?format=exe", headers=autenticado).status_code == 422
    )


# Robustez em sites reais


def _tarefa_simples(
    api: TestClient, cabecalho: Cabecalho, fabrica: Fabrica, url_inicio: str, passos: list[dict]
) -> dict:
    return preparar(
        api,
        cabecalho,
        fabrica,
        {
            "name": "Tarefa",
            "start_url": url_inicio,
            "steps": [{"action": "navigate", "url": url_inicio}, *passos],
        },
    )


def test_espera_o_elemento_de_pagina_lenta_sem_chamar_reparo(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_simples(
        api,
        autenticado,
        fabrica_sessao,
        f"{portal.url}/lenta",
        [
            {
                "action": "click",
                "target": {
                    "role": "button",
                    "tag": "button",
                    "text": "Carregou",
                    "css": "#carregou",
                },
            }
        ],
    )
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)
    execucao = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()
    assert execucao["status"] == "succeeded", execucao["items"]
    assert execucao["items"][0]["resolved_layer"] is None


def test_segue_para_a_janela_aberta_pelo_clique(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_simples(
        api,
        autenticado,
        fabrica_sessao,
        f"{portal.url}/abre-janela",
        [
            {
                "action": "click",
                "target": {"role": "link", "tag": "a", "text": "Abrir", "css": "#abrir"},
            },
            {
                "action": "capture",
                "capture_name": "Situação",
                "target": {"anchor": "Situação", "anchor_kind": "definition"},
            },
        ],
    )
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)
    execucao = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()
    assert execucao["items"][0]["output"]["situacao"] == "ATIVA", execucao["items"]


def test_download_que_abre_em_nova_janela(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_simples(
        api,
        autenticado,
        fabrica_sessao,
        f"{portal.url}/abre-janela",
        [
            {
                "action": "click",
                "target": {"role": "link", "tag": "a", "text": "Baixar", "css": "#baixar"},
                "downloaded_extension": "pdf",
            }
        ],
    )
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)
    item = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()["items"][0]
    assert item["status"] == "succeeded", item
    assert item["file_artifact_id"]


def test_clica_em_botao_dentro_de_iframe(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_simples(
        api,
        autenticado,
        fabrica_sessao,
        f"{portal.url}/com-iframe",
        [
            {
                "action": "click",
                "target": {
                    "role": "button",
                    "tag": "button",
                    "text": "Botão no iframe",
                    "css": "#no-iframe",
                },
            }
        ],
    )
    run_id = api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado).json()[
        "id"
    ]
    process_next_run(fabrica_sessao, navegador)
    item = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()["items"][0]
    assert item["status"] == "succeeded", item
    assert item["resolved_layer"] is None
    assert "/clicou-no-iframe" in portal.requests


def _tarefa_dialogo(api, cabecalho, fabrica, portal, rota: str, texto: str) -> dict:
    return _tarefa_simples(
        api,
        cabecalho,
        fabrica,
        f"{portal.url}/{rota}",
        [
            {
                "action": "click",
                "target": {"role": "button", "tag": "button", "text": texto, "css": "#acao"},
            }
        ],
    )


def test_confirmacao_comum_do_navegador_e_aceita(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    tarefa = _tarefa_dialogo(api, autenticado, fabrica_sessao, portal, "dialogo-comum", "Continuar")
    api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado)
    process_next_run(fabrica_sessao, navegador)
    assert "/dialogo-aceito" in portal.requests


def test_confirmacao_que_parece_sem_volta_e_recusada(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
) -> None:
    # O botão parece inofensivo, mas a caixa do navegador pergunta sobre pagamento
    tarefa = _tarefa_dialogo(
        api, autenticado, fabrica_sessao, portal, "dialogo-perigoso", "Continuar"
    )
    api.post("/api/v1/runs", data={"flow_id": tarefa["id"]}, headers=autenticado)
    process_next_run(fabrica_sessao, navegador)
    assert "/dialogo-aceito" not in portal.requests


# Repetição em sites atuais


def _executar_na_pagina(
    navegador: Browser, portal: Portal, caminho: str, **campos: Any
) -> tuple[Any, Any]:
    contexto = new_guarded_context(navegador, ["localhost"])
    pagina = contexto.new_page()
    pagina.goto(f"{portal.url}{caminho}")
    plano = StepPlan(
        position=1,
        intent="Passo de teste",
        url=None,
        irreversible=False,
        allowed_domains=["localhost"],
        **{"value": None, **campos},
    )
    return StepRunner(pagina).run(plano), pagina


def test_repete_em_editor_de_texto_com_varias_linhas(navegador: Browser, portal: Portal) -> None:
    resultado, pagina = _executar_na_pagina(
        navegador,
        portal,
        "/site-moderno",
        action=StepAction.FILL,
        postcondition={"type": "field_value"},
        value="primeira\nsegunda",
        targets=[{"role": "textbox", "label": "Anotações", "css": "#editor"}],
    )
    assert resultado.status == "ok", resultado.message
    assert pagina.locator("#editor").inner_text().split() == ["primeira", "segunda"]
    pagina.context.close()


def test_campo_com_mascara_conta_como_preenchido(navegador: Browser, portal: Portal) -> None:
    resultado, pagina = _executar_na_pagina(
        navegador,
        portal,
        "/site-moderno",
        action=StepAction.FILL,
        postcondition={"type": "field_value"},
        value="11222",
        targets=[{"label": "CNPJ com máscara", "css": "#mascara"}],
    )
    assert resultado.status == "ok", resultado.message
    assert pagina.locator("#mascara").input_value() == "11.222"
    pagina.context.close()


def test_clique_que_so_troca_o_estado_conta_como_resposta(
    navegador: Browser, portal: Portal
) -> None:
    resultado, pagina = _executar_na_pagina(
        navegador,
        portal,
        "/site-moderno",
        action=StepAction.CLICK,
        postcondition={"type": "page_changed"},
        targets=[{"tag": "div", "text": "Aba de detalhes", "css": "#aba"}],
    )
    assert resultado.status == "ok", resultado.message
    pagina.context.close()


@pytest.mark.parametrize(
    "campos",
    [
        {"action": StepAction.CLICK, "postcondition": {"type": "page_changed"}},
        {"action": StepAction.CAPTURE, "postcondition": {"type": "none"}},
    ],
)
def test_explica_quando_o_site_pede_um_login_que_nao_foi_gravado(
    campos: dict[str, Any], navegador: Browser, portal: Portal
) -> None:
    resultado, pagina = _executar_na_pagina(
        navegador,
        portal,
        "/login",
        targets=[
            {"tag": "div", "text": "Algo do site logado", "anchor": "Saldo", "anchor_kind": "label"}
        ],
        **campos,
    )
    assert resultado.status == "needs_human"
    assert resultado.help_kind == HelpKind.UNCERTAIN
    assert "pediu login" in resultado.message
    pagina.context.close()


def test_login_gravado_nao_recebe_a_mensagem_de_login(navegador: Browser, portal: Portal) -> None:
    resultado, pagina = _executar_na_pagina(
        navegador,
        portal,
        "/login",
        has_recorded_login=True,
        action=StepAction.CLICK,
        postcondition={"type": "page_changed"},
        targets=[{"tag": "div", "text": "Algo do site logado"}],
    )
    assert "pediu login" not in resultado.message
    pagina.context.close()


def test_captura_espera_o_site_responder_antes_de_ler(navegador: Browser, portal: Portal) -> None:
    contexto = new_guarded_context(navegador, ["localhost"])
    pagina = contexto.new_page()
    pagina.goto(f"{portal.url}/resultado-demora")
    executor = StepRunner(pagina)
    comum = {"url": None, "irreversible": False, "allowed_domains": ["localhost"], "value": None}

    clique = executor.run(
        StepPlan(
            position=1,
            intent="Filtrar",
            action=StepAction.CLICK,
            postcondition={"type": "page_changed"},
            targets=[{"role": "button", "text": "Filtrar", "css": "#filtrar"}],
            **comum,
        )
    )
    assert clique.status == "ok", clique.message

    leitura = executor.run(
        StepPlan(
            position=2,
            intent="Capturar total",
            action=StepAction.CAPTURE,
            postcondition={"type": "none"},
            targets=[{"tag": "dd", "anchor": "Total", "anchor_kind": "definition"}],
            **comum,
        )
    )
    assert leitura.captured == "2"
    contexto.close()


def test_lista_de_sugestoes_com_o_mesmo_nome_nao_atrapalha_o_preenchimento(
    navegador: Browser, portal: Portal
) -> None:
    resultado, pagina = _executar_na_pagina(
        navegador,
        portal,
        "/site-moderno",
        action=StepAction.FILL,
        postcondition={"type": "field_value"},
        value="Fortaleza",
        targets=[{"label": "Busca com sugestões"}],
    )
    assert resultado.status == "ok", resultado.message
    assert pagina.locator("#sugere").input_value() == "Fortaleza"
    pagina.context.close()
