"""Execução no Chrome da pessoa: worker → relé → extensão (chrome.debugger) → aba ao lado.

Um Chromium sem janela, com a extensão de verdade carregada, faz o papel do Chrome da pessoa.
"""

import json
import shutil
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import BrowserContext, Playwright, Worker
from sqlalchemy.orm import Session, sessionmaker
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from app.core.config import BACKEND_DIR, Settings
from app.core.exceptions import UnauthorizedError
from app.services.auth_service import AuthService
from app.services.engine.browser import connect_user_browser
from app.services.engine.extension_relay import ExtensionRelay
from app.services.worker_tasks import process_next_run
from tests.fixtures.portal import Portal
from tests.test_execucao import disparar, situacoes, ver

ORIGEM_EXTENSAO = Path(BACKEND_DIR).parent / "extension"
ESPERA_S = 10

Cabecalho = dict[str, str]


def esperar(condicao: Callable[[], Any], segundos: float = ESPERA_S) -> Any:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        resultado = condicao()
        if resultado:
            return resultado
        time.sleep(0.1)
    raise AssertionError("A condição não aconteceu a tempo.")


@pytest.fixture
def rele(fabrica_sessao: sessionmaker[Session]) -> Iterator[ExtensionRelay]:
    def autenticar(token: str) -> uuid.UUID | None:
        with fabrica_sessao() as sessao:
            try:
                return AuthService(sessao).get_runner_user(token).id
            except UnauthorizedError:
                return None

    relay = ExtensionRelay(0, autenticar)
    relay.start()
    yield relay
    relay.stop()


@pytest.fixture
def chrome_da_pessoa(
    playwright_teste: Playwright, rele: ExtensionRelay, tmp_path: Path
) -> Iterator[tuple[BrowserContext, Worker]]:
    # Cópia da extensão apontando para a porta livre que o relé pegou neste teste
    copia = tmp_path / "extensao"
    shutil.copytree(ORIGEM_EXTENSAO, copia)
    executor = copia / "runner.js"
    executor.write_text(
        executor.read_text(encoding="utf-8").replace(
            "ws://127.0.0.1:8765/extension", f"ws://127.0.0.1:{rele.port}/extension"
        ),
        encoding="utf-8",
    )
    contexto = playwright_teste.chromium.launch_persistent_context(
        str(tmp_path / "perfil"),
        channel="chromium",
        headless=True,
        accept_downloads=True,
        args=[f"--disable-extensions-except={copia}", f"--load-extension={copia}"],
    )
    service_worker = (
        contexto.service_workers[0]
        if contexto.service_workers
        else contexto.wait_for_event("serviceworker")
    )
    yield contexto, service_worker
    contexto.close()


def ligar(api: TestClient, cabecalho: Cabecalho, service_worker: Worker) -> str:
    resposta = api.post("/api/v1/auth/runner-token", headers=cabecalho)
    assert resposta.status_code == 201, resposta.text
    token = resposta.json()["token"]
    service_worker.evaluate("(token) => salvarTokenDoExecutor(token)", token)
    return token


def id_da_conta(api: TestClient, cabecalho: Cabecalho) -> uuid.UUID:
    return uuid.UUID(api.get("/api/v1/auth/me", headers=cabecalho).json()["id"])


def test_execucao_roda_em_abas_do_chrome_da_pessoa_sem_tocar_nas_dela(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: sessionmaker[Session],
    portal: Portal,
    playwright_teste: Playwright,
    rele: ExtensionRelay,
    chrome_da_pessoa: tuple[BrowserContext, Worker],
) -> None:
    contexto, service_worker = chrome_da_pessoa
    aba_da_pessoa = contexto.pages[0] if contexto.pages else contexto.new_page()
    aba_da_pessoa.goto(f"{portal.url}/relatorios")
    abas_antes = len(contexto.pages)

    ligar(api, autenticado, service_worker)
    dono = esperar(lambda: rele.user_id)
    assert dono == id_da_conta(api, autenticado)
    assert service_worker.evaluate("statusDoExecutor()") == "conectado"

    navegador = connect_user_browser(playwright_teste, rele.cdp_url)
    try:
        # O "navegador" do relé não mostra nenhuma aba da pessoa
        assert navegador.contexts[0].pages == []

        run_id = disparar(api, tarefa_ativa, autenticado)
        assert process_next_run(fabrica_sessao, navegador, owner_id=dono) is True

        execucao = ver(api, run_id, autenticado)
        assert execucao["status"] == "succeeded", execucao
        assert situacoes(execucao) == ["succeeded"] * 3

        # O PDF baixado no Chrome da pessoa chegou ao Ditto
        arquivo = api.get(
            f"/api/v1/artifacts/{execucao['items'][0]['file_artifact_id']}", headers=autenticado
        )
        assert arquivo.status_code == 200
        assert arquivo.content.startswith(b"%PDF")

        # As abas do Ditto fecharam; a da pessoa continua aberta e o filtro de domínios
        # (só "localhost" nesta tarefa) não vale nela
        esperar(lambda: len(contexto.pages) == abas_antes)
        assert not aba_da_pessoa.is_closed()
        aba_da_pessoa.goto(portal.url.replace("localhost", "127.0.0.1") + "/relatorios")
        assert service_worker.evaluate("[...abasDoDitto].length") == 0
    finally:
        navegador.close()


def test_execucao_de_outra_conta_nao_roda_no_chrome_da_pessoa(
    api: TestClient,
    autenticado: Cabecalho,
    criar_conta: Callable[..., Cabecalho],
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: sessionmaker[Session],
    playwright_teste: Playwright,
    rele: ExtensionRelay,
    chrome_da_pessoa: tuple[BrowserContext, Worker],
) -> None:
    _contexto, service_worker = chrome_da_pessoa
    run_id = disparar(api, tarefa_ativa, autenticado)

    # Quem conecta a extensão é outra conta
    outra = criar_conta()
    ligar(api, outra, service_worker)
    dono = esperar(lambda: rele.user_id)
    assert dono != id_da_conta(api, autenticado)

    navegador = connect_user_browser(playwright_teste, rele.cdp_url)
    try:
        assert process_next_run(fabrica_sessao, navegador, owner_id=dono) is False
    finally:
        navegador.close()
    assert ver(api, run_id, autenticado)["status"] == "queued"


def test_token_de_acesso_comum_nao_liga_a_extensao(
    autenticado: Cabecalho,
    rele: ExtensionRelay,
    chrome_da_pessoa: tuple[BrowserContext, Worker],
) -> None:
    _contexto, service_worker = chrome_da_pessoa
    token_de_acesso = autenticado["Authorization"].removeprefix("Bearer ")
    service_worker.evaluate("(token) => salvarTokenDoExecutor(token)", token_de_acesso)

    esperar(lambda: service_worker.evaluate("statusDoExecutor()") == "recusado")
    assert rele.user_id is None


def test_token_do_executor_nao_vale_na_api(api: TestClient, autenticado: Cabecalho) -> None:
    token = api.post("/api/v1/auth/runner-token", headers=autenticado).json()["token"]
    executor = {"Authorization": f"Bearer {token}"}

    assert api.get("/api/v1/auth/me", headers=executor).status_code == 401
    assert api.get("/api/v1/runs", headers=executor).status_code == 401
    assert api.post("/api/v1/auth/runner-token", headers=executor).status_code == 401


def test_rele_so_aceita_a_extensao_e_o_endereco_secreto(rele: ExtensionRelay) -> None:
    def fechado_pelo_rele(url: str, **opcoes: Any) -> bool:
        try:
            with connect(url, **opcoes) as conexao:
                conexao.send(json.dumps({"type": "hello", "token": "qualquer"}))
                conexao.recv(timeout=ESPERA_S)
        except ConnectionClosed as fechamento:
            return fechamento.rcvd is not None and fechamento.rcvd.code in {1008, 4401}
        return False

    base = f"ws://127.0.0.1:{rele.port}"
    # Uma página comum (ou programa) manda outra origem: recusada antes de olhar o token
    assert fechado_pelo_rele(f"{base}/extension", origin="http://site-qualquer.com")
    # Origem de extensão, mas token inválido
    assert fechado_pelo_rele(f"{base}/extension", origin="chrome-extension://abc")
    # Sem o segredo, ninguém fala com o lado do Playwright
    assert fechado_pelo_rele(f"{base}/cdp/errado")
    assert rele.user_id is None


def test_porta_da_extensao_e_recusada_em_producao() -> None:
    with pytest.raises(ValueError, match="EXTENSION_RUNNER_PORT"):
        # Os testes ligam ALLOW_PRIVATE_NETWORKS, que também é recusado em produção
        Settings(environment="production", allow_private_networks=False, extension_runner_port=8765)
    assert Settings(extension_runner_port="").extension_runner_port is None
