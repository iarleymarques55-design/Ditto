"""O worker aguenta o que dá errado de verdade: banco que pisca, Chrome que cai, cancelamento no
meio de um passo, desligamento, agendas atrasadas, análise que quebra e arquivos vencidos."""

import http.client
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Browser, Playwright
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import FlowStatus, HelpStatus, StepAction
from app.models.flow import Flow
from app.models.repair import HelpRequest
from app.models.run import Artifact, RunItem, RunLogEntry
from app.models.schedule import Schedule
from app.services import storage, worker_tasks
from app.services.ai_explorer import BrowserUnavailableError
from app.services.engine import browser as browser_module
from app.services.engine.browser import launch_browser
from app.services.engine.egress_proxy import EgressProxy
from app.services.engine.executor import StepRunner
from app.services.run_processor import _BROWSER_LOST, diagnostics_key_for
from app.services.worker_pool import WorkerPool
from app.services.worker_tasks import (
    analyze_next_flow,
    fire_due_schedules,
    process_next_run,
    purge_expired_artifacts,
)
from app.worker import BackgroundLane, MainLoop
from tests.conftest import gravacao_relatorio
from tests.fixtures.portal import Portal

Cabecalho = dict[str, str]
Fabrica = sessionmaker[Session]

PLANILHA_3 = b"loja\nLoja 01 - Shopping Norte\nLoja 02 - Aldeota\nLoja 03 - Messejana\n"
PLANILHA_1 = b"loja\nLoja 01 - Shopping Norte\n"
PASSOS_POR_LINHA = 4  # abrir, escolher a loja, informar o mês, exportar


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


def situacoes(execucao: dict[str, Any]) -> list[str]:
    return [item["status"] for item in execucao["items"]]


def interceptar_passos(monkeypatch: pytest.MonkeyPatch, antes=None, depois=None) -> list[int]:
    """Roda algo antes ou depois de cada passo do navegador. Devolve o contador de passos."""
    original = StepRunner.run
    chamadas: list[int] = []

    def rodar(self: StepRunner, plano: Any) -> Any:
        chamadas.append(len(chamadas) + 1)
        if antes is not None:
            antes(len(chamadas))
        resultado = original(self, plano)
        if depois is not None:
            depois(len(chamadas), resultado)
        return resultado

    monkeypatch.setattr(StepRunner, "run", rodar)
    return chamadas


# Sinal de vida


def test_aviso_de_vida_continua_depois_de_o_banco_piscar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regressão: uma falha do banco matava a thread do aviso, e a execução rodava duas vezes."""
    monkeypatch.setattr(worker_tasks, "HEARTBEAT_SECONDS", 0.01)
    chamadas = {"n": 0}
    segunda = threading.Event()

    def fabrica() -> Any:
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise ConnectionError("o banco caiu por um instante")
        segunda.set()
        return MagicMock()

    parar = threading.Event()
    aviso = threading.Thread(
        target=worker_tasks._heartbeat_loop, args=(fabrica, uuid.uuid4(), parar), daemon=True
    )
    aviso.start()
    assert segunda.wait(5), "o aviso de vida parou na primeira falha"
    assert aviso.is_alive()
    parar.set()
    aviso.join(5)
    assert not aviso.is_alive()


# Cancelamento no meio de um passo


def test_cancelar_durante_o_ultimo_passo_nao_vira_concluida(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)

    def cancelar_no_ultimo(numero: int, _resultado: Any) -> None:
        if numero == PASSOS_POR_LINHA:
            assert api.post(f"/api/v1/runs/{run_id}/cancel", headers=autenticado).status_code == 200

    interceptar_passos(monkeypatch, depois=cancelar_no_ultimo)
    process_next_run(fabrica_sessao, navegador)

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "canceled"
    assert situacoes(execucao) == ["skipped"]


def test_cancelar_durante_um_passo_que_pediria_ajuda_nao_abre_pedido(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    portal: Portal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão: o pedido de ajuda gravava "esperando você" por cima do cancelamento, e a
    resposta da pessoa punha a execução cancelada de volta na fila."""
    portal.layout = "ambiguo"
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)

    def cancelar_se_for_pedir_ajuda(_numero: int, resultado: Any) -> None:
        if resultado.status == "needs_human":
            api.post(f"/api/v1/runs/{run_id}/cancel", headers=autenticado)

    interceptar_passos(monkeypatch, depois=cancelar_se_for_pedir_ajuda)
    process_next_run(fabrica_sessao, navegador)

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "canceled"
    assert situacoes(execucao) == ["skipped"]
    with fabrica_sessao() as sessao:
        abertos = sessao.query(HelpRequest).filter(HelpRequest.status == HelpStatus.OPEN).count()
    assert abertos == 0
    assert api.get("/api/v1/help-requests", headers=autenticado).json() == []


# Queda do navegador no meio


@pytest.fixture
def navegador_descartavel(playwright_teste: Playwright) -> Iterator[Browser]:
    navegador = launch_browser(playwright_teste)
    yield navegador
    if navegador.is_connected():
        navegador.close()


def test_chrome_que_cai_no_meio_devolve_a_execucao_para_a_fila(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    navegador_descartavel: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão: com o Chrome fora do ar, as linhas que faltavam viravam "puladas" e a
    execução terminava como falha, com 300 linhas perdidas."""
    run_id = disparar(api, tarefa_ativa, autenticado)

    def derrubar_na_segunda_linha(numero: int) -> None:
        if numero == PASSOS_POR_LINHA + 1:
            navegador_descartavel.close()

    interceptar_passos(monkeypatch, antes=derrubar_na_segunda_linha)
    with pytest.raises(BrowserUnavailableError):
        process_next_run(fabrica_sessao, navegador_descartavel)

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "queued"
    assert situacoes(execucao) == ["succeeded", "pending", "pending"]
    assert any("navegador caiu" in linha["message"] for linha in execucao["log"])

    # Com o navegador de volta, a execução continua de onde parou
    monkeypatch.undo()
    process_next_run(fabrica_sessao, navegador)
    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "succeeded"
    assert situacoes(execucao) == ["succeeded", "succeeded", "succeeded"]


def test_chrome_que_cai_toda_hora_termina_a_execucao(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador_descartavel: Browser,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    with fabrica_sessao() as sessao:
        for _ in range(2):
            sessao.add(RunLogEntry(run_id=uuid.UUID(run_id), level="info", message=_BROWSER_LOST))
        sessao.commit()

    navegador_descartavel.close()
    with pytest.raises(BrowserUnavailableError):
        process_next_run(fabrica_sessao, navegador_descartavel)

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "failed"
    assert situacoes(execucao) == ["skipped"]


def test_proxy_de_saida_fecha_junto_com_o_navegador(
    playwright_teste: Playwright, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressão: cada navegador reaberto deixava um proxy (porta e thread) para trás."""
    criados: list[EgressProxy] = []

    class ProxyAnotado(EgressProxy):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            criados.append(self)

    monkeypatch.setattr(browser_module, "EgressProxy", ProxyAnotado)
    navegador = launch_browser(playwright_teste)
    assert len(criados) == 1 and not criados[0].stopped
    navegador.close()
    assert criados[0].stopped


# Desligamento


def test_worker_desligando_devolve_a_execucao_para_a_fila(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado)
    desligando = threading.Event()
    desligando.set()

    process_next_run(fabrica_sessao, navegador, stop_worker=desligando)

    execucao = ver(api, run_id, autenticado)
    assert execucao["status"] == "queued"
    assert situacoes(execucao) == ["pending", "pending", "pending"]


def test_desligar_espera_um_prazo_total_e_nao_um_por_linha() -> None:
    pool = WorkerPool(None, threading.Event())
    for chave in range(4):
        linha = threading.Thread(target=time.sleep, args=(3,), daemon=True)
        linha.start()
        pool._lanes[chave] = linha  # type: ignore[assignment]

    comeco = time.monotonic()
    pool.join(0.5)
    assert time.monotonic() - comeco < 1.5


# Agendas


def test_agenda_nao_empilha_execucoes_enquanto_a_anterior_nao_termina(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
) -> None:
    """Regressão: com o Chrome desligado o dia todo, uma agenda a cada 15 min criava 96 execuções."""
    criada = api.post(
        "/api/v1/schedules",
        data={"flow_id": tarefa_ativa["id"], "cron": "*/15 * * * *"},
        files={"file": ("a.csv", PLANILHA_1)},
        headers=autenticado,
    ).json()

    with fabrica_sessao() as sessao:
        for _ in range(3):
            agenda = sessao.get(Schedule, criada["id"])
            agenda.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
            sessao.commit()
            assert fire_due_schedules(sessao) == 1
            assert sessao.get(Schedule, criada["id"]).next_run_at > datetime.now(UTC)

    assert api.get("/api/v1/runs", headers=autenticado).json()["total"] == 1


# Análise das gravações


def _gravar(api: TestClient, cabecalho: Cabecalho, portal: Portal) -> str:
    resposta = api.post("/api/v1/flows", json=gravacao_relatorio(portal.url), headers=cabecalho)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


class IaQuebrada:
    def chat_json(self, _sistema: str, _usuario: str) -> dict[str, Any]:
        raise RuntimeError("resposta que ninguém esperava")


def test_erro_inesperado_da_ia_nao_prende_a_gravacao(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: Fabrica, portal: Portal
) -> None:
    flow_id = _gravar(api, autenticado, portal)
    with fabrica_sessao() as sessao:
        assert analyze_next_flow(sessao, IaQuebrada()) is True
        assert analyze_next_flow(sessao, IaQuebrada()) is False  # não volta para a fila
        assert sessao.get(Flow, flow_id).status == FlowStatus.AWAITING_CONFIRMATION


def test_analise_que_sempre_quebra_libera_a_gravacao_para_revisao(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: Fabrica,
    portal: Portal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def quebrar(*_args: Any) -> None:
        raise RuntimeError("defeito na análise")

    monkeypatch.setattr(worker_tasks, "analyze_flow", quebrar)
    flow_id = _gravar(api, autenticado, portal)
    outra = _gravar(api, autenticado, portal)
    with fabrica_sessao() as sessao:
        assert analyze_next_flow(sessao) is True
        flow = sessao.get(Flow, flow_id)
        assert flow.status == FlowStatus.AWAITING_CONFIRMATION
        # Ninguém conferiu se o clique tem volta: ele passa a pedir confirmação
        assert all(step.irreversible for step in flow.steps if step.action == StepAction.CLICK)
        assert all(step.intent for step in flow.steps)
        # A próxima gravação da fila não fica presa atrás da que quebrou
        assert analyze_next_flow(sessao) is True
        assert sessao.get(Flow, outra).status == FlowStatus.AWAITING_CONFIRMATION


# Limpeza dos arquivos vencidos


def _envelhecer_artefatos(fabrica: Fabrica) -> None:
    with fabrica() as sessao:
        for artefato in sessao.query(Artifact).all():
            artefato.created_at = datetime.now(UTC) - timedelta(days=90)
        sessao.commit()


def test_limpeza_apaga_em_lotes_ate_acabar(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão: só 200 arquivos saíam por hora, menos do que lotes grandes geram."""
    monkeypatch.setattr(worker_tasks, "_PURGE_BATCH", 1)
    disparar(api, tarefa_ativa, autenticado)
    process_next_run(fabrica_sessao, navegador)
    _envelhecer_artefatos(fabrica_sessao)

    with fabrica_sessao() as sessao:
        assert purge_expired_artifacts(sessao) == 3
        assert sessao.query(Artifact).count() == 0


def test_limpeza_apaga_os_detalhes_da_falha_junto_com_a_tela(
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

    with fabrica_sessao() as sessao:
        tela = sessao.query(Artifact).one()
        detalhes = diagnostics_key_for(tela.storage_key)
    assert detalhes is not None
    storage.save_bytes(detalhes, b"{}")  # como o processador guarda ao lado da tela
    _envelhecer_artefatos(fabrica_sessao)

    with fabrica_sessao() as sessao:
        assert purge_expired_artifacts(sessao) == 1
    for chave in (tela.storage_key, detalhes):
        with pytest.raises(Exception, match="não encontrado"):
            storage.open_for_read(chave)


def test_falha_ao_apagar_do_armazenamento_nao_deixa_registro_sem_arquivo(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    process_next_run(fabrica_sessao, navegador)
    _envelhecer_artefatos(fabrica_sessao)

    def bucket_fora_do_ar(_chave: str) -> None:
        raise ConnectionError("bucket fora do ar")

    monkeypatch.setattr(storage, "delete", bucket_fora_do_ar)
    with fabrica_sessao() as sessao:
        assert purge_expired_artifacts(sessao) == 1
        assert sessao.query(Artifact).count() == 0


def test_nomes_dos_detalhes_da_falha() -> None:
    assert diagnostics_key_for("c/r/.telas/linha-3.png") == "c/r/.telas/linha-3-foco.json"
    assert diagnostics_key_for("c/r/relatorio.pdf") is None
    assert diagnostics_key_for("c/r/pasta/linha-3.png") is None


# Tela da execução


def test_tela_da_execucao_mostra_textos_e_o_tamanho_das_tabelas(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    with fabrica_sessao() as sessao:
        item = sessao.query(RunItem).filter(RunItem.run_id == run_id).one()
        item.output = {"protocolo": "12345", "itens": [{"a": "1"}, {"a": "2"}], "vazio": None}
        sessao.commit()

    linha = ver(api, run_id, autenticado)["items"][0]
    assert linha["output"] == {"protocolo": "12345"}
    assert linha["table_rows"] == {"itens": 2}
    # A tabela inteira continua disponível onde ela é pedida
    resposta = api.get(f"/api/v1/runs/{run_id}/items/{linha['id']}/output", headers=autenticado)
    assert resposta.status_code == 200
    assert resposta.json()["itens"] == [{"a": "1"}, {"a": "2"}]


# Linha principal do worker


class PiscinaFalsa:
    def __init__(self) -> None:
        self.voltas = 0

    def refresh(self) -> None:
        self.voltas += 1

    def join(self, _timeout: float) -> None:
        pass


def test_volta_da_linha_principal(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    tmp_path: Path,
) -> None:
    criada = api.post(
        "/api/v1/schedules",
        data={"flow_id": tarefa_ativa["id"], "cron": "10 7 5 * *"},
        files={"file": ("a.csv", PLANILHA_1)},
        headers=autenticado,
    ).json()
    with fabrica_sessao() as sessao:
        sessao.get(Schedule, criada["id"]).next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        sessao.commit()

    piscina = PiscinaFalsa()
    vida = tmp_path / "vivo"
    volta = MainLoop(fabrica_sessao, piscina, alive_file=vida)
    volta.tick(time.monotonic())

    assert piscina.voltas == 1
    assert vida.exists()
    assert api.get("/api/v1/runs", headers=autenticado).json()["total"] == 1


def test_volta_da_linha_principal_sobrevive_ao_banco_fora_do_ar(tmp_path: Path) -> None:
    def banco_fora() -> Session:
        raise ConnectionError("banco fora do ar")

    piscina = PiscinaFalsa()
    vida = tmp_path / "vivo"
    MainLoop(banco_fora, piscina, alive_file=vida).tick(time.monotonic())
    # O sinal de vida sai mesmo assim: o processo está de pé e tenta de novo na próxima volta
    assert vida.exists()


def test_analise_e_limpeza_rodam_fora_da_linha_principal(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: Fabrica, portal: Portal
) -> None:
    flow_id = _gravar(api, autenticado, portal)
    linha = BackgroundLane(fabrica_sessao, threading.Event())
    assert linha.step(time.monotonic()) is True
    assert linha.step(time.monotonic()) is False
    with fabrica_sessao() as sessao:
        assert sessao.get(Flow, flow_id).status == FlowStatus.AWAITING_CONFIRMATION


# Proxy de saída


class _Eco(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        pass

    def do_POST(self) -> None:
        if "chunked" in self.headers.get("Transfer-Encoding", ""):
            corpo = b""
            while True:
                tamanho = int(self.rfile.readline().strip(), 16)
                if tamanho == 0:
                    self.rfile.readline()
                    break
                corpo += self.rfile.read(tamanho)
                self.rfile.readline()
        else:
            corpo = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def eco() -> Iterator[int]:
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Eco)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield servidor.server_address[1]
    servidor.shutdown()
    servidor.server_close()


def _pelo_proxy(porta: int, corpo: Any, **opcoes: Any) -> bytes:
    proxy = EgressProxy(lambda _host, _address: True)
    try:
        host, porta_proxy = proxy.url.removeprefix("http://").split(":")
        conexao = http.client.HTTPConnection(host, int(porta_proxy), timeout=10)
        conexao.request("POST", f"http://127.0.0.1:{porta}/eco", body=corpo, **opcoes)
        return conexao.getresponse().read()
    finally:
        proxy.stop()


def test_post_http_chega_inteiro_pelo_proxy(eco: int) -> None:
    """Regressão: o corpo que chegava junto com os cabeçalhos ficava no buffer do proxy."""
    corpo = b"campo=valor&" * 20_000  # maior que o buffer de leitura
    assert _pelo_proxy(eco, corpo) == corpo


def test_post_http_em_pedacos_chega_inteiro_pelo_proxy(eco: int) -> None:
    pedacos = [b"primeiro;", b"segundo;" * 5000, b"terceiro"]
    resposta = _pelo_proxy(
        eco, iter(pedacos), encode_chunked=True, headers={"Transfer-Encoding": "chunked"}
    )
    assert resposta == b"".join(pedacos)
