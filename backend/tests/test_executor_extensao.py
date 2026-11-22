"""Execução no Chrome da pessoa: worker → relé → extensão (chrome.debugger) → aba ao lado.

Um Chromium sem janela, com a extensão de verdade carregada, faz o papel do Chrome da pessoa.
"""

import base64
import json
import shutil
import threading
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


def autenticador(fabrica_sessao: sessionmaker[Session]) -> Callable[[str], uuid.UUID | None]:
    def autenticar(token: str) -> uuid.UUID | None:
        with fabrica_sessao() as sessao:
            try:
                return AuthService(sessao).get_runner_user(token).id
            except UnauthorizedError:
                return None

    return autenticar


@pytest.fixture
def rele(
    fabrica_sessao: sessionmaker[Session], request: pytest.FixtureRequest
) -> Iterator[ExtensionRelay]:
    # Com "mesma_maquina" falso, o relé age como no Ditto publicado: não lê o disco da pessoa
    mesma_maquina = getattr(request, "param", True)
    relay = ExtensionRelay(0, autenticador(fabrica_sessao), local_downloads=mesma_maquina)
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
    configuracao = copia / "config.js"
    configuracao.write_text(
        configuracao.read_text(encoding="utf-8").replace(
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


# Na mesma máquina, o arquivo baixado é copiado da pasta da pessoa; com o worker em outra
# máquina (nuvem, Docker), ele vem pela conexão
@pytest.mark.parametrize(
    "rele", [True, False], ids=["mesma-maquina", "worker-remoto"], indirect=True
)
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
    dono = esperar(lambda: rele.connected_users() and rele.connected_users()[0])
    assert dono == id_da_conta(api, autenticado)
    assert service_worker.evaluate("statusDoExecutor()") == "conectado"

    navegador = connect_user_browser(playwright_teste, rele.cdp_url_for(dono))
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
    dono = esperar(lambda: rele.connected_users() and rele.connected_users()[0])
    assert dono != id_da_conta(api, autenticado)

    navegador = connect_user_browser(playwright_teste, rele.cdp_url_for(dono))
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
    assert rele.connected_users() == []


def test_token_do_executor_nao_vale_na_api(api: TestClient, autenticado: Cabecalho) -> None:
    token = api.post("/api/v1/auth/runner-token", headers=autenticado).json()["token"]
    executor = {"Authorization": f"Bearer {token}"}

    assert api.get("/api/v1/auth/me", headers=executor).status_code == 401
    assert api.get("/api/v1/runs", headers=executor).status_code == 401
    assert api.post("/api/v1/auth/runner-token", headers=executor).status_code == 401


def fechado_pelo_rele(url: str, **opcoes: Any) -> int | None:
    """O código com que o relé fechou a conexão, ou None se ela continuou aberta."""
    try:
        with connect(url, **opcoes) as conexao:
            conexao.send(json.dumps({"type": "hello", "token": "qualquer"}))
            conexao.recv(timeout=ESPERA_S)
    except ConnectionClosed as fechamento:
        return fechamento.rcvd.code if fechamento.rcvd is not None else None
    return None


def test_rele_so_aceita_a_extensao_e_o_endereco_secreto(rele: ExtensionRelay) -> None:
    base = f"ws://127.0.0.1:{rele.port}"
    # Uma página comum (ou programa) manda outra origem: recusada antes de olhar o token
    assert fechado_pelo_rele(f"{base}/extension", origin="http://site-qualquer.com") == 1008
    # Origem de extensão, mas token inválido
    assert fechado_pelo_rele(f"{base}/extension", origin="chrome-extension://abc") == 4401
    # O lado do Playwright não fica na porta da extensão
    assert fechado_pelo_rele(f"{base}/cdp/errado") == 1008
    # Nem com o segredo certo dá para pegar o Chrome de uma conta que não conectou
    assert fechado_pelo_rele(rele.cdp_url_for(uuid.uuid4())) == 1008
    errado = rele.cdp_url_for(uuid.uuid4()).replace("/cdp/", "/cdp/x")
    assert fechado_pelo_rele(errado) == 1008
    assert rele.connected_users() == []


def test_lado_do_playwright_so_escuta_nesta_maquina(rele: ExtensionRelay) -> None:
    assert rele.cdp_url_for(uuid.uuid4()).startswith("ws://127.0.0.1:")


def test_apresentacao_grande_e_recusada_antes_do_token(rele: ExtensionRelay) -> None:
    with connect(
        f"ws://127.0.0.1:{rele.port}/extension", origin="chrome-extension://abc"
    ) as conexao:
        conexao.send(json.dumps({"type": "hello", "token": "x" * 100_000}))
        with pytest.raises(ConnectionClosed) as fechamento:
            conexao.recv(timeout=ESPERA_S)
    # 1009: mensagem grande demais
    assert fechamento.value.rcvd is not None and fechamento.value.rcvd.code == 1009


def test_so_a_extensao_da_lista_conecta(fabrica_sessao: sessionmaker[Session]) -> None:
    relay = ExtensionRelay(
        0, autenticador(fabrica_sessao), allowed_origins=["chrome-extension://ditto"]
    )
    relay.start()
    try:
        url = f"ws://127.0.0.1:{relay.port}/extension"
        assert fechado_pelo_rele(url, origin="chrome-extension://outra") == 1008
        # A da lista passa da origem e só para no token
        assert fechado_pelo_rele(url, origin="chrome-extension://ditto") == 4401
    finally:
        relay.stop()


def test_rele_aberto_para_a_rede_exige_a_lista_de_extensoes() -> None:
    with pytest.raises(ValueError, match="EXTENSION_ORIGINS"):
        Settings(extension_runner_port=8765, extension_relay_host="0.0.0.0")
    publico = Settings(
        environment="production",
        allow_private_networks=False,
        extension_runner_port=8765,
        extension_relay_host="0.0.0.0",
        extension_origins=["chrome-extension://ditto"],
    )
    assert publico.relay_is_public
    # No próprio computador, a lista é opcional
    assert not Settings(extension_runner_port=8765).relay_is_public
    assert Settings(extension_runner_port="").extension_runner_port is None


# ---------- várias contas no mesmo relé ----------


class ExtensaoFalsa:
    """Faz o papel da extensão de uma conta: responde aos comandos do relé e anota cada um."""

    def __init__(self, porta: int, token: str, respostas: dict[str, Any] | None = None) -> None:
        self.comandos: list[dict[str, Any]] = []
        self.respostas = respostas or {}
        self.conexao = connect(
            f"ws://127.0.0.1:{porta}/extension", origin="chrome-extension://ditto"
        )
        self.conexao.send(json.dumps({"type": "hello", "token": token}))
        assert json.loads(self.conexao.recv(timeout=ESPERA_S))["type"] == "welcome"
        self.linha = threading.Thread(target=self._responder, daemon=True)
        self.linha.start()

    def _responder(self) -> None:
        try:
            for bruto in self.conexao:
                comando = json.loads(bruto)
                self.comandos.append(comando)
                resposta = self.respostas.get(comando["method"], {})
                self.conexao.send(json.dumps({"id": comando["id"], "result": resposta}))
        except ConnectionClosed:
            pass

    def evento(self, **mensagem: Any) -> None:
        self.conexao.send(json.dumps(mensagem))

    def fechar(self) -> None:
        self.conexao.close()


class ControleCdp:
    """Faz o papel do Playwright: manda comandos CDP e espera cada resposta."""

    def __init__(self, url: str) -> None:
        self.conexao = connect(url, max_size=None)
        self.numero = 0

    def pedir(self, metodo: str, **params: Any) -> dict[str, Any]:
        self.numero += 1
        self.conexao.send(json.dumps({"id": self.numero, "method": metodo, "params": params}))
        while True:
            mensagem = json.loads(self.conexao.recv(timeout=ESPERA_S))
            if mensagem.get("id") == self.numero:
                return mensagem

    def fechar(self) -> None:
        self.conexao.close()


def token_do_executor(api: TestClient, cabecalho: Cabecalho) -> str:
    return api.post("/api/v1/auth/runner-token", headers=cabecalho).json()["token"]


def test_duas_contas_ao_mesmo_tempo_cada_uma_no_seu_chrome(
    api: TestClient, criar_conta: Callable[..., Cabecalho], rele: ExtensionRelay
) -> None:
    ana, bia = criar_conta(), criar_conta()
    aba = {"tabId": 7, "targetInfo": {"targetId": "alvo-7", "type": "page", "url": "about:blank"}}
    chrome_ana = ExtensaoFalsa(rele.port, token_do_executor(api, ana), {"createTab": aba})
    chrome_bia = ExtensaoFalsa(rele.port, token_do_executor(api, bia), {"createTab": aba})
    controle_ana = None
    try:
        id_ana, id_bia = id_da_conta(api, ana), id_da_conta(api, bia)
        esperar(lambda: set(rele.connected_users()) == {id_ana, id_bia})

        controle_ana = ControleCdp(rele.cdp_url_for(id_ana))
        resposta = controle_ana.pedir("Target.createTarget", url="about:blank")
        assert resposta["result"] == {"targetId": "alvo-7"}
        # A aba abriu no Chrome da Ana; o da Bia não recebeu nada
        assert [comando["method"] for comando in chrome_ana.comandos] == ["createTab"]
        assert chrome_bia.comandos == []

        # Ninguém pega o Chrome da Ana uma segunda vez
        assert fechado_pelo_rele(rele.cdp_url_for(id_ana)) == 1008

        # A Ana desconecta: a Bia continua
        chrome_ana.fechar()
        esperar(lambda: rele.connected_users() == [id_bia])
    finally:
        if controle_ana is not None:
            controle_ana.fechar()
        chrome_ana.fechar()
        chrome_bia.fechar()


@pytest.mark.parametrize("rele", [False], ids=["worker-remoto"], indirect=True)
def test_worker_remoto_nunca_le_o_caminho_que_a_extensao_informa(
    api: TestClient, autenticado: Cabecalho, rele: ExtensionRelay, tmp_path: Path
) -> None:
    # Uma extensão adulterada aponta para um arquivo do servidor: ele não pode sair dali
    segredo = tmp_path / "segredo-do-servidor.env"
    segredo.write_text("JWT_SECRET=nao-pode-sair")
    destino = tmp_path / "downloads"
    destino.mkdir()
    conteudo = b"%PDF arquivo da pessoa"
    respostas = {
        "createTab": {"tabId": 3, "targetInfo": {"targetId": "alvo-3", "type": "page"}},
        "finishDownload": {"downloadId": 1, "path": str(segredo)},
        "readDownload": {"base64": base64.b64encode(conteudo).decode()},
    }
    chrome = ExtensaoFalsa(rele.port, token_do_executor(api, autenticado), respostas)
    controle = None
    try:
        dono = id_da_conta(api, autenticado)
        esperar(lambda: rele.connected_users() == [dono])
        controle = ControleCdp(rele.cdp_url_for(dono))
        controle.pedir("Browser.setDownloadBehavior", behavior="allow", downloadPath=str(destino))
        controle.pedir("Target.createTarget", url="about:blank")

        chrome.evento(
            event="cdpEvent",
            tabId=3,
            method="Page.downloadWillBegin",
            params={"guid": "g1", "url": "https://portal.exemplo/a.pdf"},
        )
        chrome.evento(
            event="cdpEvent",
            tabId=3,
            method="Page.downloadProgress",
            params={"guid": "g1", "state": "completed"},
        )

        arquivo = destino / "g1"
        esperar(lambda: arquivo.is_file() and arquivo.stat().st_size > 0)
        assert arquivo.read_bytes() == conteudo
        assert "readDownload" in [comando["method"] for comando in chrome.comandos]
    finally:
        if controle is not None:
            controle.fechar()
        chrome.fechar()


def test_extensao_so_manda_o_token_para_fora_com_criptografia(
    chrome_da_pessoa: tuple[BrowserContext, Worker],
) -> None:
    _contexto, service_worker = chrome_da_pessoa
    seguro = "(endereco) => releSeguro(endereco)"
    assert service_worker.evaluate(seguro, "wss://ditto.exemplo/extension") is True
    assert service_worker.evaluate(seguro, "ws://127.0.0.1:8765/extension") is True
    assert service_worker.evaluate(seguro, "ws://ditto.exemplo/extension") is False
    assert service_worker.evaluate(seguro, "https://ditto.exemplo/extension") is False
