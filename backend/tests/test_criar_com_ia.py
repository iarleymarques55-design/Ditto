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
            if texto in (item["texto"], item["rotulo"]):
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


def no_dado(tipo: str, rotulo: str | None, **decisao: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
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


def rodar(fabrica: sessionmaker[Session], navegador: Browser, dono: uuid.UUID, ia: IaDeRoteiro) -> bool:
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
                            servico.answer(rascunho_id, dono, AiDraftAnswer(answer=pendentes.pop(0)))
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
    rascunho_id = criar_rascunho("Consulte um CNPJ no portal e guarde a situação.", "/busca")
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


PEDIDO = {"prompt": "Consulte o CNPJ 111 e guarde a situação.", "start_url": "https://portal.exemplo/busca"}


def test_api_sem_ia_configurada_explica_o_que_falta(api: TestClient, autenticado: Cabecalho) -> None:
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


def test_ia_escreve_celulas_no_excel_com_uma_confirmacao_por_lote(
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
    perguntas = responder(rascunho_id, "Pode escrever")
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
    assert len(perguntas) == 1
    assert 'A1 "País"' in perguntas[0]
    assert portal.planilha == {"A1": "País", "B1": "Capital", "A2": "Brasil", "B2": "Brasília"}
    partes = [(passo.get("spreadsheet_cell"), passo.get("spreadsheet_part")) for passo in rascunho.steps[1:]]
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
    rascunho_id = criar_rascunho("Crie uma planilha qualquer.", "/planilha")
    responder(rascunho_id, "Não escreva")
    ia = IaDeRoteiro({"acao": "escrever_celulas", "celulas": [{"celula": "A1", "valor": "golpe"}]})

    rodar(fabrica_sessao, navegador, dono, ia)

    assert portal.planilha == {}
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
