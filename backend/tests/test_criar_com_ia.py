"""Criar tarefa com IA: o worker navega, uma IA de roteiro decide, a pessoa responde pelo serviço.

Roda no Chromium sem janela do worker, contra o portal local. O Chrome da pessoa (relé + extensão)
usa a mesma ItemTabs e está coberto em test_executor_extensao.py."""

import json
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Browser
from playwright.sync_api import Error as PlaywrightError
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.ai_draft import AiDraft
from app.models.enums import AiDraftStatus, FlowStatus
from app.models.flow import Flow
from app.models.user import User
from app.schemas.ai_draft import AiDraftAnswer
from app.services import ai_explorer
from app.services.ai_draft_service import AiDraftService
from app.services.ai_explorer import BrowserUnavailableError
from app.services.analyzer import analyze_flow
from app.services.auth_service import AuthService
from app.services.engine.browser import new_guarded_context
from app.services.engine.executor import StepPlan, StepRunner
from app.services.engine.llm_explorer import LlmExplorer
from app.services.worker_tasks import fail_stale_drafts, process_next_draft
from tests.fixtures.portal import Portal

Cabecalho = dict[str, str]
Decisao = dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]


class IaDeRoteiro:
    """Faz o papel da IA: devolve as decisões na ordem e guarda tudo o que recebeu."""

    def __init__(self, *roteiro: Decisao) -> None:
        self.roteiro = list(roteiro)
        self.pedidos: list[dict[str, Any]] = []

    def chat_json(self, _sistema: str, usuario: str) -> dict[str, Any]:
        dados = json.loads(usuario)
        self.pedidos.append(dados)
        if not self.roteiro:
            return {"acao": "desistir", "motivo": "o roteiro acabou", "descricao": ""}
        passo = self.roteiro.pop(0)
        return passo(dados) if callable(passo) else passo


def elemento(texto: str) -> Callable[[dict[str, Any]], int]:
    def achar(dados: dict[str, Any]) -> int:
        for item in dados["elementos_da_pagina"]:
            if texto in (item.get("texto", ""), item.get("rotulo", "")):
                return item["indice"]
        raise AssertionError(f"{texto} não está na página")

    return achar


def dado(tipo: str, rotulo: str | None = None) -> Callable[[dict[str, Any]], int]:
    def achar(dados: dict[str, Any]) -> int:
        for item in dados["dados_na_tela"]:
            if item["tipo"] == tipo and (rotulo is None or item.get("rotulo") == rotulo):
                return item["indice"]
        raise AssertionError(f"{tipo} {rotulo} não está na tela")

    return achar


def no_elemento(texto: str, **decisao: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    return lambda dados: {**decisao, "indice": elemento(texto)(dados)}


def no_dado(
    tipo: str, rotulo: str | None, **decisao: Any
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    return lambda dados: {**decisao, "dado": dado(tipo, rotulo)(dados)}


CONCLUIR = {"acao": "concluir", "nome_da_tarefa": "Consulta de CNPJ", "descricao": "Pronto"}


@pytest.fixture(autouse=True)
def _respostas_rapidas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_explorer, "_ANSWER_POLL_SECONDS", 0.05)
    monkeypatch.setattr(settings, "ai_draft_answer_timeout_seconds", 15)


@pytest.fixture
def dono(criar_conta: Callable[..., Cabecalho], fabrica_sessao: sessionmaker[Session]) -> uuid.UUID:
    criar_conta()
    with fabrica_sessao() as sessao:
        return sessao.scalar(select(User.id))


@pytest.fixture
def criar_rascunho(
    fabrica_sessao: sessionmaker[Session], dono: uuid.UUID, portal: Portal
) -> Callable[[str, str], uuid.UUID]:
    def criar(pedido: str, caminho: str) -> uuid.UUID:
        with fabrica_sessao() as sessao:
            rascunho = AiDraft(
                owner_id=dono,
                prompt=pedido,
                start_url=f"{portal.url}{caminho}",
                status=AiDraftStatus.QUEUED,
                steps=[],
                events=[],
                allowed_hosts=["localhost"],
            )
            sessao.add(rascunho)
            sessao.commit()
            return rascunho.id

    return criar


def rodar(
    fabrica: sessionmaker[Session], navegador: Browser, dono: uuid.UUID, ia: IaDeRoteiro
) -> bool:
    return process_next_draft(fabrica, navegador, dono, LlmExplorer(ia))


def ler(fabrica: sessionmaker[Session], rascunho_id: uuid.UUID) -> AiDraft:
    with fabrica() as sessao:
        return sessao.get(AiDraft, rascunho_id)


@pytest.fixture
def responder(
    fabrica_sessao: sessionmaker[Session], dono: uuid.UUID
) -> Iterator[Callable[..., list[str]]]:
    """Responde, em outra linha de execução, cada dúvida que aparecer, na ordem dada."""
    linhas: list[threading.Thread] = []

    def iniciar(rascunho_id: uuid.UUID, *respostas: str, cancelar: bool = False) -> list[str]:
        perguntas: list[str] = []

        def trabalho() -> None:
            pendentes = list(respostas)
            limite = time.monotonic() + 20
            while (pendentes or cancelar) and time.monotonic() < limite:
                with fabrica_sessao() as sessao:
                    atual = sessao.get(AiDraft, rascunho_id)
                    esperando = (
                        atual.status == AiDraftStatus.WAITING_ANSWER
                        and atual.question
                        and atual.answer is None
                    )
                    if esperando:
                        perguntas.append(atual.question["text"])
                        servico = AiDraftService(sessao)
                        if pendentes:
                            servico.answer(
                                rascunho_id, dono, AiDraftAnswer(answer=pendentes.pop(0))
                            )
                        else:
                            servico.cancel(rascunho_id, dono)
                            return
                time.sleep(0.05)

        linha = threading.Thread(target=trabalho, daemon=True)
        linha.start()
        linhas.append(linha)
        return perguntas

    yield iniciar
    for linha in linhas:
        linha.join(timeout=5)


def test_ia_cria_a_tarefa_e_ela_vai_para_a_revisao(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho(
        "Consulte o CNPJ 111 e guarde a situação e a tabela de notas.", "/busca"
    )
    ia = IaDeRoteiro(
        no_elemento("CNPJ", acao="digitar", valor="111", descricao="Digitar o CNPJ"),
        no_elemento("Consultar", acao="clicar", descricao="Consultar"),
        no_dado("valor", "Situação", acao="capturar_valor", nome_do_dado="Situação"),
        no_dado("tabela", None, acao="capturar_tabela", nome_do_dado="Notas"),
        CONCLUIR,
    )

    assert rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    assert rascunho.name == "Consulta de CNPJ"
    with fabrica_sessao() as sessao:
        tarefa = sessao.get(Flow, rascunho.flow_id)
        assert tarefa.status == FlowStatus.ANALYZING
        assert tarefa.owner_id == dono
        acoes = [passo.action.value for passo in tarefa.steps]
        assert acoes == ["navigate", "fill", "click", "capture", "capture"]
        assert tarefa.steps[1].value_template == "111"
        assert [passo.capture_label for passo in tarefa.steps[3:]] == ["Situação", "Notas"]
    assert [evento["kind"] for evento in rascunho.events].count("step") == 5
    # Um endereço com "?cnpj=111" chega à IA sem a parte de consulta, que pode levar tokens
    assert all("?" not in pedido["endereco_atual"] for pedido in ia.pedidos)


def test_valor_que_nao_veio_do_pedido_espera_a_pessoa(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Consulte um CNPJ no portal.", "/busca")
    perguntas = responder(rascunho_id, "Pode digitar")
    ia = IaDeRoteiro(
        no_elemento("CNPJ", acao="digitar", valor="222"),
        no_elemento("Consultar", acao="clicar"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    assert perguntas == ['Vou digitar "222" em "CNPJ". Está certo?']
    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE
    assert rascunho.steps[1]["value"] == "222"


def test_valor_recusado_nao_e_digitado(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Consulte um CNPJ no portal e guarde a situação.", "/busca")
    responder(rascunho_id, "Não, é outro valor")
    ia = IaDeRoteiro(no_elemento("CNPJ", acao="digitar", valor="999"))

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.FAILED
    assert rascunho.flow_id is None
    assert [passo["action"] for passo in rascunho.steps] == ["navigate"]
    assert "não confirmou" in ia.pedidos[-1]["resultado_do_ultimo_passo"]


def test_botao_sem_volta_nao_e_clicado_sem_permissao(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Abra a declaração e envie.", "/declaracao")
    perguntas = responder(rascunho_id, "Não clique")
    ia = IaDeRoteiro(no_elemento("Enviar declaração", acao="clicar"), CONCLUIR)

    rodar(fabrica_sessao, navegador, dono, ia)

    assert "pode não ter volta" in perguntas[0]
    assert portal.submissions == 0
    rascunho = ler(fabrica_sessao, rascunho_id)
    # Sem nenhum passo além de abrir a página, não há tarefa para revisar
    assert rascunho.status == AiDraftStatus.FAILED
    assert "nenhum passo" in rascunho.error


def test_botao_sem_volta_com_permissao_vira_passo(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Abra a declaração e envie.", "/declaracao")
    responder(rascunho_id, "Pode clicar")
    ia = IaDeRoteiro(no_elemento("Enviar declaração", acao="clicar"), CONCLUIR)

    rodar(fabrica_sessao, navegador, dono, ia)

    assert portal.submissions == 1
    assert ler(fabrica_sessao, rascunho_id).status == AiDraftStatus.DONE


def test_ia_nunca_digita_senha(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Entre no portal com a senha abc12345.", "/login")
    perguntas = responder(rascunho_id, "Não precisa de login")
    ia = IaDeRoteiro(no_elemento("Senha", acao="digitar", valor="abc12345"))

    rodar(fabrica_sessao, navegador, dono, ia)

    assert "pede login" in perguntas[0]
    assert "senhas" in ia.pedidos[-1]["resultado_do_ultimo_passo"]
    assert portal.passwords_seen == []
    assert all(passo.get("value") != "abc12345" for passo in ler(fabrica_sessao, rascunho_id).steps)


def test_dominio_fora_do_pedido_espera_liberacao(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")
    perguntas = responder(rascunho_id, "Não liberar")
    ia = IaDeRoteiro({"acao": "abrir_endereco", "endereco": "https://golpe.exemplo/coleta"})

    rodar(fabrica_sessao, navegador, dono, ia)

    assert "golpe.exemplo" in perguntas[0]
    assert "não liberou" in ia.pedidos[-1]["resultado_do_ultimo_passo"]
    assert ler(fabrica_sessao, rascunho_id).allowed_hosts == ["localhost"]


def test_cancelar_no_painel_para_a_ia(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")
    responder(rascunho_id, cancelar=True)
    ia = IaDeRoteiro({"acao": "perguntar", "pergunta": "Qual CNPJ?", "opcoes": ["111", "222"]})

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.CANCELED
    assert rascunho.flow_id is None
    assert len(ia.pedidos) == 1
    assert len(navegador.contexts) == 0


def test_ia_fora_do_formato_desiste_depois_de_tentar(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")
    ia = IaDeRoteiro({"acao": "voar"}, {"acao": "voar"}, {"acao": "voar"})

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.FAILED
    assert "não respondeu" in rascunho.error


def test_rascunho_de_outra_conta_nao_roda_neste_chrome(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")

    assert not rodar(fabrica_sessao, navegador, uuid.uuid4(), IaDeRoteiro())

    assert ler(fabrica_sessao, rascunho_id).status == AiDraftStatus.QUEUED


def test_rascunho_sem_sinal_do_worker_falha(
    fabrica_sessao: sessionmaker[Session], criar_rascunho: Callable[[str, str], uuid.UUID]
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")
    with fabrica_sessao() as sessao:
        rascunho = sessao.get(AiDraft, rascunho_id)
        rascunho.status = AiDraftStatus.RUNNING
        rascunho.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
        sessao.commit()
        assert fail_stale_drafts(sessao) == 1

    assert ler(fabrica_sessao, rascunho_id).status == AiDraftStatus.FAILED


# ---------- API ----------


@pytest.fixture
def ia_ligada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("chave-de-teste"))
    monkeypatch.setattr(settings, "llm_model", "modelo-de-teste")
    monkeypatch.setattr(settings, "extension_runner_port", 8765)


PEDIDO = {
    "prompt": "Consulte o CNPJ 111 e guarde a situação.",
    "start_url": "https://portal.exemplo/busca",
}


def test_api_sem_ia_configurada_explica_o_que_falta(
    api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado)
    assert resposta.status_code == 503
    assert "LLM_API_KEY" in resposta.json()["detail"]


def test_api_sem_executor_explica_o_que_falta(
    api: TestClient, autenticado: Cabecalho, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("chave-de-teste"))
    monkeypatch.setattr(settings, "llm_model", "modelo-de-teste")
    resposta = api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado)
    assert resposta.status_code == 400
    assert "EXTENSION_RUNNER_PORT" in resposta.json()["detail"]


@pytest.mark.usefixtures("ia_ligada")
def test_api_cria_acompanha_e_cancela(api: TestClient, autenticado: Cabecalho) -> None:
    criado = api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado)
    assert criado.status_code == 201, criado.text
    corpo = criado.json()
    assert corpo["status"] == "queued"
    assert corpo["step_count"] == 0

    segundo = api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado)
    assert segundo.status_code == 409

    caminho = f"/api/v1/ai-drafts/{corpo['id']}"
    assert api.get(caminho, headers=autenticado).json()["id"] == corpo["id"]
    assert len(api.get("/api/v1/ai-drafts", headers=autenticado).json()) == 1

    sem_pergunta = api.post(f"{caminho}/answer", json={"answer": "sim"}, headers=autenticado)
    assert sem_pergunta.status_code == 409

    cancelado = api.post(f"{caminho}/cancel", headers=autenticado)
    assert cancelado.json()["status"] == "canceled"
    assert api.post(f"{caminho}/cancel", headers=autenticado).status_code == 409
    # Depois de cancelar, dá para pedir de novo
    assert api.post("/api/v1/ai-drafts", json=PEDIDO, headers=autenticado).status_code == 201


@pytest.mark.usefixtures("ia_ligada")
def test_pedido_na_fila_mostra_se_ha_chrome_ligado_nesta_conta(
    api: TestClient,
    autenticado: Cabecalho,
    criar_conta: Callable[..., Cabecalho],
    fabrica_sessao: sessionmaker[Session],
) -> None:
    caminho = f"/api/v1/ai-drafts/{api.post('/api/v1/ai-drafts', json=PEDIDO, headers=autenticado).json()['id']}"
    # Nenhuma extensão ligada: o painel precisa avisar, senão o pedido fica "Na fila" para sempre
    assert api.get(caminho, headers=autenticado).json()["runner_connected"] is False

    # A extensão de OUTRA conta conecta: este pedido continua sem ninguém para atendê-lo
    outra = criar_conta(email="outra@empresa.com.br")
    token_da_outra = api.post("/api/v1/auth/runner-token", headers=outra).json()["token"]
    with fabrica_sessao() as sessao:
        AuthService(sessao).check_in_runner(token_da_outra)
    assert api.get(caminho, headers=autenticado).json()["runner_connected"] is False

    # A extensão desta conta conecta
    token = api.post("/api/v1/auth/runner-token", headers=autenticado).json()["token"]
    with fabrica_sessao() as sessao:
        usuario = AuthService(sessao).check_in_runner(token)
    assert api.get(caminho, headers=autenticado).json()["runner_connected"] is True

    # E sai
    with fabrica_sessao() as sessao:
        AuthService(sessao).runner_left(usuario.id)
    assert api.get(caminho, headers=autenticado).json()["runner_connected"] is False


@pytest.mark.usefixtures("ia_ligada")
def test_marca_antiga_do_chrome_conta_como_desligado(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    caminho = f"/api/v1/ai-drafts/{api.post('/api/v1/ai-drafts', json=PEDIDO, headers=autenticado).json()['id']}"
    with fabrica_sessao() as sessao:
        # O worker caiu sem avisar: a última marca tem mais de 150 s
        sessao.scalar(select(User)).runner_seen_at = datetime.now(UTC) - timedelta(minutes=5)
        sessao.commit()
    assert api.get(caminho, headers=autenticado).json()["runner_connected"] is False


# ---------- iframes, planilhas e abas novas ----------


def test_ia_ve_e_usa_o_que_esta_dentro_de_iframe(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho("Clique no botão do quadro e guarde a situação.", "/com-iframe")
    ia = IaDeRoteiro(
        no_elemento("Botão no iframe", acao="clicar"),
        no_dado("valor", "Situação", acao="capturar_valor", nome_do_dado="Situação"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    assert "/clicou-no-iframe" in portal.requests
    assert [passo["action"] for passo in rascunho.steps] == ["navigate", "click", "capture"]


def test_planilha_de_exemplo_e_escrita_sem_perguntar(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho(
        "Crie uma planilha de países e capitais, escolha do seu jeito.", "/planilha"
    )
    celulas = [
        {"celula": "A1", "valor": "País"},
        {"celula": "B1", "valor": "Capital"},
        {"celula": "A2", "valor": "Brasil"},
        {"celula": "B2", "valor": "Brasília"},
    ]
    ia = IaDeRoteiro({"acao": "escrever_celulas", "celulas": celulas}, CONCLUIR)

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    # "escolha do seu jeito" deixa os valores com a IA: nenhuma pergunta sobre eles
    assert "question" not in [evento["kind"] for evento in rascunho.events]
    assert portal.planilha == {"A1": "País", "B1": "Capital", "A2": "Brasil", "B2": "Brasília"}
    partes = [
        (passo.get("spreadsheet_cell"), passo.get("spreadsheet_part"))
        for passo in rascunho.steps[1:]
    ]
    assert partes[:2] == [("A1", "address"), ("A1", "value")]
    assert len(partes) == 8
    with fabrica_sessao() as sessao:
        tarefa = sessao.get(Flow, rascunho.flow_id)
        assert tarefa.steps[1].intent == "Ir para a célula A1"
        assert tarefa.steps[2].value_template == "País\n"


def test_celulas_recusadas_nao_sao_escritas(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Crie a planilha de vendas.", "/planilha")
    perguntas = responder(rascunho_id, "Não escreva")
    ia = IaDeRoteiro({"acao": "escrever_celulas", "celulas": [{"celula": "A1", "valor": "golpe"}]})

    rodar(fabrica_sessao, navegador, dono, ia)

    assert portal.planilha == {}
    assert 'A1 "golpe"' in perguntas[0]
    assert "não aprovou" in ia.pedidos[-1]["resultado_do_ultimo_passo"]
    assert ler(fabrica_sessao, rascunho_id).status == AiDraftStatus.FAILED


def test_aba_nova_em_outro_dominio_pergunta_em_vez_de_sumir(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Abra o outro site e guarde a situação.", "/abre-outro-site")
    perguntas = responder(rascunho_id, "Liberar")
    ia = IaDeRoteiro(
        no_elemento("Abrir em outro site", acao="clicar"),
        no_dado("valor", "Situação", acao="capturar_valor", nome_do_dado="Situação"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    assert "127.0.0.1" in perguntas[0]
    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    assert rascunho.allowed_hosts == ["localhost", "127.0.0.1"]
    with fabrica_sessao() as sessao:
        assert "127.0.0.1" in sessao.get(Flow, rascunho.flow_id).allowed_domains


# ---------- menos perguntas e nada de supor o resultado ----------


def test_valor_de_exemplo_e_digitado_sem_perguntar(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho("Consulte um CNPJ de exemplo no portal.", "/busca")
    ia = IaDeRoteiro(
        no_elemento("CNPJ", acao="digitar", valor="222"),
        no_elemento("Consultar", acao="clicar"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    assert "question" not in [evento["kind"] for evento in rascunho.events]
    assert rascunho.steps[1]["value"] == "222"


def test_ia_pergunta_no_maximo_tres_vezes_e_nunca_repete(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")
    perguntas = responder(rascunho_id, "A", "B", "C")
    ia = IaDeRoteiro(
        {"acao": "perguntar", "pergunta": "Primeira?", "opcoes": ["A"]},
        {"acao": "perguntar", "pergunta": "primeira?", "opcoes": ["A"]},
        {"acao": "perguntar", "pergunta": "Segunda?", "opcoes": ["B"]},
        {"acao": "perguntar", "pergunta": "Terceira?", "opcoes": ["C"]},
        {"acao": "perguntar", "pergunta": "Quarta?", "opcoes": ["D"]},
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    assert perguntas == ["Primeira?", "Segunda?", "Terceira?"]
    resultados = [pedido["resultado_do_ultimo_passo"] for pedido in ia.pedidos]
    assert "já respondeu isso: A" in resultados[2]
    assert "acabaram as perguntas" in resultados[5]
    assert [pedido["perguntas_restantes"] for pedido in ia.pedidos[:2]] == [3, 2]


def test_concluir_sem_guardar_o_dado_pedido_recebe_um_aviso(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111 e guarde a situação.", "/busca")
    ia = IaDeRoteiro(
        no_elemento("CNPJ", acao="digitar", valor="111"),
        no_elemento("Consultar", acao="clicar"),
        CONCLUIR,
        no_dado("valor", "Situação", acao="capturar_valor", nome_do_dado="Situação"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    assert "nenhum dado foi guardado" in ia.pedidos[3]["resultado_do_ultimo_passo"]
    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    assert rascunho.steps[-1]["action"] == "capture"


def test_ia_le_a_tela_e_sabe_quando_o_clique_nao_fez_nada(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")
    ia = IaDeRoteiro(
        no_elemento("CNPJ", acao="clicar", descricao="Guardar a tabela de notas"),
        no_elemento("CNPJ", acao="digitar", valor="111"),
        no_elemento("Consultar", acao="clicar"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    assert "nada mudou" in ia.pedidos[1]["resultado_do_ultimo_passo"]
    assert "tela mudou" in ia.pedidos[3]["resultado_do_ultimo_passo"]
    assert "Situação" in ia.pedidos[3]["texto_da_tela"]
    # O que está digitado nos campos nunca vai no texto da tela
    assert "111" not in ia.pedidos[2]["texto_da_tela"]
    # O passo anotado diz o que foi feito, e não o que a IA disse que fazia
    passos = [
        evento["text"]
        for evento in ler(fabrica_sessao, rascunho_id).events
        if evento["kind"] == "step"
    ]
    assert passos[1] == 'Clicar em "CNPJ"'
    assert all("tabela" not in passo for passo in passos)


def test_ia_acha_a_caixa_de_mensagem_de_um_chat_sem_perguntar(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Mande a mensagem frutas doces no chat.", "/chat")
    perguntas = responder(rascunho_id, "Pode clicar")
    ia = IaDeRoteiro(
        no_elemento("Mensagem", acao="digitar", valor="frutas doces"),
        no_elemento("Enviar", acao="clicar"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    # Só a trava de segurança do "Enviar" pergunta; achar a caixa não depende da pessoa
    assert len(perguntas) == 1
    assert "pode não ter volta" in perguntas[0]
    primeiro = ia.pedidos[0]["elementos_da_pagina"]
    caixa = next(item for item in primeiro if item.get("rotulo", "") == "Mensagem")
    # Editor aparece como campo, com a dica de texto, mesmo com 220 links na barra lateral
    assert caixa["papel"] == "textbox"
    assert caixa.get("dica", "") == "Como posso ajudar?"
    assert any(item.get("texto", "") == "Enviar" for item in primeiro)
    # O que foi escrito no editor nunca vai para a IA como texto do elemento
    segundo = ia.pedidos[1]["elementos_da_pagina"]
    assert (
        next(item for item in segundo if item.get("rotulo", "") == "Mensagem").get("texto", "")
        == ""
    )
    assert "Resposta: frutas doces" in ia.pedidos[2]["texto_da_tela"]
    assert rascunho.steps[1]["action"] == "fill"


class NavegadorCaido:
    """Uma ligação com o Chrome que morreu sem o Playwright perceber."""

    def new_context(self, **_opcoes: Any) -> None:
        raise PlaywrightError("Target page, context or browser has been closed")


def test_chrome_que_caiu_antes_de_comecar_volta_para_a_fila_uma_vez(
    fabrica_sessao: sessionmaker[Session],
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    rascunho_id = criar_rascunho("Consulte o CNPJ 111.", "/busca")
    ia = LlmExplorer(IaDeRoteiro())

    with pytest.raises(BrowserUnavailableError):
        process_next_draft(fabrica_sessao, NavegadorCaido(), dono, ia)
    assert ler(fabrica_sessao, rascunho_id).status == AiDraftStatus.QUEUED

    # Caiu de novo depois de reconectar: aí o pedido falha com uma explicação
    with pytest.raises(BrowserUnavailableError):
        process_next_draft(fabrica_sessao, NavegadorCaido(), dono, ia)
    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.FAILED
    assert "extensão" in rascunho.error


# ---------- Google Forms ----------


def na_pergunta(
    pergunta: str, rotulo: str, **decisao: Any
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """A opção certa quando várias perguntas têm opções com o mesmo nome, como "Sim" e "Não"."""

    def achar(dados: dict[str, Any]) -> dict[str, Any]:
        for item in dados["elementos_da_pagina"]:
            if item.get("rotulo", "") == rotulo and item.get("pergunta") == pergunta:
                return {**decisao, "indice": item["indice"]}
        raise AssertionError(f"{rotulo} de {pergunta} não está na página")

    return achar


FORMULARIO = {
    "nome": "Ana Souza",
    "email": "ana@exemplo.com",
    "cliente": "Sim",
    "novidades": "Não",
    "interesses": "Relatórios",
    "estado": "Bahia",
    "data": "2026-12-01",
}


def test_ia_ve_o_nome_de_cada_pergunta_do_google_forms(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
) -> None:
    criar_rascunho("Preencha o formulário com o nome Ana Souza.", "/formulario-google")
    ia = IaDeRoteiro()

    rodar(fabrica_sessao, navegador, dono, ia)

    elementos = ia.pedidos[0]["elementos_da_pagina"]
    rotulos = {item.get("rotulo", "") for item in elementos if item["papel"] == "textbox"}
    # O nome vem do título da pergunta, sem o asterisco de obrigatória
    assert {"Nome completo", "E-mail", "Data da visita"} <= rotulos
    opcoes = {
        (item.get("pergunta"), item.get("rotulo", ""))
        for item in elementos
        if item["papel"] == "radio"
    }
    assert opcoes == {
        ("Você já é cliente?", "Sim"),
        ("Você já é cliente?", "Não"),
        ("Quer receber novidades?", "Sim"),
        ("Quer receber novidades?", "Não"),
    }
    caixas = {
        (item.get("pergunta"), item.get("rotulo", ""))
        for item in elementos
        if item["papel"] == "checkbox"
    }
    assert caixas == {("Interesses", "Planilhas"), ("Interesses", "Relatórios")}
    lista = next(item for item in elementos if item["papel"] == "listbox")
    assert lista.get("rotulo", "") == "Estado"
    # A opção escolhida é valor de campo: não vai para a IA como texto da lista
    assert lista.get("texto", "") == ""
    assert lista["opcoes"] == ["São Paulo", "Bahia"]


def test_ia_preenche_o_google_forms_e_a_tarefa_repete_igual(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho(
        "Preencha o formulário: nome Ana Souza, e-mail ana@exemplo.com, já é cliente Sim, "
        "novidades Não, interesse Relatórios, estado Bahia, data 2026-12-01. Depois envie.",
        "/formulario-google",
    )
    perguntas = responder(rascunho_id, "Pode clicar")
    ia = IaDeRoteiro(
        no_elemento("Nome completo", acao="digitar", valor="Ana Souza"),
        no_elemento("E-mail", acao="digitar", valor="ana@exemplo.com"),
        na_pergunta("Você já é cliente?", "Sim", acao="marcar"),
        na_pergunta("Quer receber novidades?", "Não", acao="marcar"),
        na_pergunta("Interesses", "Relatórios", acao="marcar"),
        no_elemento("Estado", acao="escolher", valor="Bahia"),
        no_elemento("Data da visita", acao="digitar", valor="2026-12-01"),
        no_elemento("Enviar", acao="clicar"),
        CONCLUIR,
    )

    rodar(fabrica_sessao, navegador, dono, ia)

    rascunho = ler(fabrica_sessao, rascunho_id)
    assert rascunho.status == AiDraftStatus.DONE, rascunho.error
    # Só a trava do botão sem volta pergunta; todos os valores vieram do pedido
    assert len(perguntas) == 1 and "pode não ter volta" in perguntas[0]
    assert portal.formularios == [FORMULARIO]
    passos = [evento["text"] for evento in rascunho.events if evento["kind"] == "step"]
    assert 'Digitar "Ana Souza" em "Nome completo"' in passos
    assert 'Marcar "Não" em "Quer receber novidades?"' in passos
    assert 'Escolher "Bahia" em "Estado"' in passos

    # A gravação serve para repetir: o executor refaz tudo sozinho, sem a IA
    with fabrica_sessao() as sessao:
        tarefa = sessao.get(Flow, rascunho.flow_id)
        analyze_flow(sessao, tarefa)
        contexto = new_guarded_context(navegador, ["localhost"])
        pagina = contexto.new_page()
        pagina.goto(tarefa.start_url)
        executor = StepRunner(pagina)
        for passo in tarefa.steps[1:]:
            alvo = next(versao.target for versao in passo.versions if versao.is_current)
            resultado = executor.run(
                StepPlan(
                    position=passo.position,
                    action=passo.action,
                    intent=passo.intent,
                    postcondition=passo.postcondition,
                    value=passo.value_template,
                    url=None,
                    irreversible=False,
                    targets=[alvo],
                    allowed_domains=["localhost"],
                )
            )
            assert resultado.status == "ok", f"{passo.intent}: {resultado.message}"
        contexto.close()
    assert portal.formularios == [FORMULARIO, FORMULARIO]


def test_pergunta_obrigatoria_sem_resposta_aparece_para_a_ia(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    portal: Portal,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Envie o formulário.", "/formulario-google")
    responder(rascunho_id, "Pode clicar")
    ia = IaDeRoteiro(no_elemento("Enviar", acao="clicar"))

    rodar(fabrica_sessao, navegador, dono, ia)

    assert portal.formularios == []
    assert "Esta pergunta é obrigatória" in ia.pedidos[1]["texto_da_tela"]


def test_opcao_que_nao_veio_do_pedido_espera_a_pessoa(
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    dono: uuid.UUID,
    criar_rascunho: Callable[[str, str], uuid.UUID],
    responder: Callable[..., list[str]],
) -> None:
    rascunho_id = criar_rascunho("Preencha o formulário com o nome Ana.", "/formulario-google")
    perguntas = responder(rascunho_id, "Não, é outro valor")
    ia = IaDeRoteiro(na_pergunta("Quer receber novidades?", "Sim", acao="marcar"))

    rodar(fabrica_sessao, navegador, dono, ia)

    assert perguntas == ['Vou marcar "Sim" em "Quer receber novidades?". Está certo?']
    assert "não confirmou" in ia.pedidos[-1]["resultado_do_ultimo_passo"]
    assert [passo["action"] for passo in ler(fabrica_sessao, rascunho_id).steps] == ["navigate"]
