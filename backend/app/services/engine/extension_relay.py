"""Relé entre o Playwright e a extensão do Ditto, para as tarefas rodarem no Chrome da pessoa.

O Playwright acha que está falando com um navegador comum (CDP), mas esse "navegador" só tem
as abas que o Ditto abriu. A extensão abre cada aba ao lado da aba ativa, controla a aba com
chrome.debugger e repassa os comandos. As outras abas da pessoa nunca entram aqui.

Roda numa thread do worker e atende várias pessoas ao mesmo tempo, cada uma isolada das outras.
São duas portas:
- a da extensão, que pode ficar aberta para a internet (Ditto publicado) e só aceita quem
  apresenta o token do executor;
- a do Playwright, que sempre escuta só em 127.0.0.1, num endereço com segredo: quem a alcança
  controla as abas do Ditto, então ela nunca sai da máquina do worker.
"""

import asyncio
import base64
import binascii
import concurrent.futures
import json
import logging
import re
import secrets
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from app.core.rate_limit import ip_behind_proxies
from app.services.engine.browser import MAX_DOWNLOAD_BYTES

logger = logging.getLogger(__name__)

_HELLO_TIMEOUT_SECONDS = 5
# Um download grande pode demorar: é o maior tempo que um comando à extensão pode levar
_EXTENSION_TIMEOUT_SECONDS = 120
# Antes do token, só cabe a apresentação: ninguém de fora ocupa memória do worker
_MAX_HELLO_BYTES = 16 * 1024
# Capturas de tela e arquivos baixados vêm em base64 e podem passar de alguns megabytes
_MAX_MESSAGE_BYTES = 64 * 1024 * 1024
# O mesmo limite do navegador do worker e da extensão
_MAX_DOWNLOAD_BYTES = MAX_DOWNLOAD_BYTES
_MAX_CONNECTIONS = 500
# Conexões ainda sem token vindas do mesmo IP: sem isto, um script ocupava as 500 vagas e
# nenhuma extensão conseguia ligar
_MAX_PENDING_PER_IP = 10
# O Chrome identifica cada download por um UUID. O valor vira nome de arquivo no worker, então
# qualquer outra coisa (como "../../") é recusada
_DOWNLOAD_GUID = re.compile(r"^[0-9A-Za-z-]{8,64}$")
_CLOSE_POLICY = 1008
_CLOSE_TRY_LATER = 1013
_CLOSE_UNAUTHORIZED = 4401
_CLOSE_IN_USE = 4409
# De quanto em quanto tempo o token de cada conexão é conferido de novo: senha trocada ou
# "sair de todas as sessões" derruba também o Chrome ligado
_RECHECK_SECONDS = 60
# Tempo para a conexão antiga provar que está viva antes de uma nova assumir o lugar dela
_ALIVE_SECONDS = 3
_BROWSER_TARGET = {
    "targetId": "ditto-browser",
    "type": "browser",
    "title": "",
    "url": "",
    "attached": True,
    "canAccessOpener": False,
}


class RelayError(Exception):
    pass


@dataclass
class _Tab:
    tab_id: int
    session_id: str
    target_id: str
    # Sessões de iframes de outro domínio, que chegam por dentro da aba
    children: set[str] = field(default_factory=set)


@dataclass
class _Link:
    """Tudo o que é de uma pessoa: a extensão dela, a conexão do Playwright e as abas."""

    user_id: uuid.UUID
    extension: ServerConnection
    # Guardado só para conferir de novo, de tempos em tempos, se ele ainda vale
    token: str
    cdp: ServerConnection | None = None
    next_id: int = 0
    pending: dict[int, asyncio.Future[Any]] = field(default_factory=dict)
    tabs: dict[int, _Tab] = field(default_factory=dict)
    next_session: int = 0
    download_path: str | None = None
    downloads: dict[str, str] = field(default_factory=dict)


class ExtensionRelay:
    def __init__(
        self,
        port: int,
        authenticate: Callable[[str], uuid.UUID | None],
        host: str = "127.0.0.1",
        allowed_origins: list[str] | None = None,
        local_downloads: bool = True,
        recheck_seconds: float = _RECHECK_SECONDS,
        on_leave: Callable[[uuid.UUID], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._authenticate = authenticate
        self._recheck_seconds = recheck_seconds
        # Avisado quando a extensão de uma conta sai, para o painel não achar que ela está ligada
        self._on_leave = on_leave
        # Vazio: qualquer extensão do Chrome pode tentar (o token ainda é exigido)
        self._allowed_origins = set(allowed_origins or [])
        # Worker e Chrome na mesma máquina: o arquivo baixado é copiado direto da pasta dele
        self._local_downloads = local_downloads
        # Muda a cada vez que o worker sobe: outro programa da máquina não acha o endereço
        self._secret = secrets.token_urlsafe(24)
        self._cdp_port = 0

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping: asyncio.Event | None = None
        self._startup_error: BaseException | None = None

        self._links: dict[uuid.UUID, _Link] = {}
        # Cópia que as linhas de trabalho do worker leem de outras threads: trocada inteira, nunca
        # alterada, para ninguém ler a lista no meio de uma mudança
        self._connected: tuple[uuid.UUID, ...] = ()
        self._connections = 0
        self._pending_by_ip: dict[str, int] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    # ─── Usado pelo worker ────────────────────────────────────────────────

    def connected_users(self) -> list[uuid.UUID]:
        """As contas com a extensão ligada agora."""
        return list(self._connected)

    def cdp_url_for(self, user_id: uuid.UUID) -> str:
        return f"ws://127.0.0.1:{self._cdp_port}/cdp/{self._secret}/{user_id}"

    def set_allowed_domains(self, user_id: uuid.UUID, domains: list[str]) -> bool:
        """Pede à extensão para barrar, ela mesma, a navegação das abas do Ditto para fora destes
        domínios. Sem isso, cada pedido do site ia e voltava pelo worker antes de seguir: com o
        worker na nuvem, uma viagem pela rede por imagem, script e chamada da página.

        Falso quando a extensão é de uma versão que não sabe fazer isso: aí o worker filtra."""
        link = self._links.get(user_id)
        loop = self._loop
        if link is None or loop is None:
            return False
        future = asyncio.run_coroutine_threadsafe(
            self._call_extension(link, "setAllowedDomains", domains=domains), loop
        )
        try:
            future.result(timeout=_EXTENSION_TIMEOUT_SECONDS)
        except (RelayError, TimeoutError, concurrent.futures.TimeoutError):
            return False
        return True

    def start(self) -> None:
        started = threading.Event()
        self._thread = threading.Thread(
            target=lambda: asyncio.run(self._main(started)), name="ditto-relay", daemon=True
        )
        self._thread.start()
        if not started.wait(10):
            raise RuntimeError("O relé da extensão não subiu.")
        if self._startup_error is not None:
            raise RuntimeError(
                f"Não consegui usar a porta {self.port} para a extensão."
            ) from self._startup_error

    def stop(self) -> None:
        if self._loop is not None and self._stopping is not None:
            self._loop.call_soon_threadsafe(self._stopping.set)
        if self._thread is not None:
            self._thread.join(timeout=5)

    async def _main(self, started: threading.Event) -> None:
        self._loop = asyncio.get_running_loop()
        self._stopping = asyncio.Event()
        try:
            async with (
                serve(
                    self._serve_extension, self.host, self.port, max_size=_MAX_HELLO_BYTES
                ) as extension_server,
                serve(self._serve_cdp, "127.0.0.1", 0, max_size=_MAX_MESSAGE_BYTES) as cdp_server,
            ):
                self.port = _bound_port(extension_server)
                self._cdp_port = _bound_port(cdp_server)
                started.set()
                recheck = asyncio.ensure_future(self._recheck_tokens())
                try:
                    await self._stopping.wait()
                finally:
                    recheck.cancel()
        except OSError as error:
            self._startup_error = error
            started.set()

    async def _recheck_tokens(self) -> None:
        """Um token conferido só na hora de conectar valeria para sempre naquela conexão."""
        while True:
            await asyncio.sleep(self._recheck_seconds)
            for link in list(self._links.values()):
                try:
                    user_id = await asyncio.to_thread(self._authenticate, link.token)
                except Exception:
                    # O banco pode ter caído por um instante: confere de novo na próxima volta
                    logger.warning("Não consegui conferir o token do executor.", exc_info=True)
                    continue
                if user_id != link.user_id and self._links.get(link.user_id) is link:
                    logger.info("Token do executor revogado: a conexão da extensão foi encerrada.")
                    await self._drop(
                        link, "Token revogado. Conecte de novo pelo painel.", _CLOSE_UNAUTHORIZED
                    )

    # ─── Lado da extensão ─────────────────────────────────────────────────

    def _origin_allowed(self, origin: str) -> bool:
        # Só uma extensão do Chrome abre este socket. Uma página comum mandaria a própria origem
        if not origin.startswith("chrome-extension://"):
            return False
        return not self._allowed_origins or origin in self._allowed_origins

    async def _serve_extension(self, connection: ServerConnection) -> None:
        request = connection.request
        if request is None or request.path != "/extension":
            await connection.close(_CLOSE_POLICY, "Endereço desconhecido.")
            return
        origin = request.headers.get("Origin", "")
        if not self._origin_allowed(origin):
            if origin.startswith("chrome-extension://"):
                # Quase sempre é EXTENSION_ORIGINS com o ID antigo da extensão: sem este aviso, a
                # extensão ficava "esperando o Ditto responder" e o log não dizia nada. O valor
                # vem de fora, então vai entre aspas e cortado
                logger.warning(
                    "Extensão recusada: a origem %r não está em EXTENSION_ORIGINS.", origin[:80]
                )
            await connection.close(_CLOSE_POLICY, "Origem não autorizada.")
            return
        if self._connections >= _MAX_CONNECTIONS:
            await connection.close(_CLOSE_TRY_LATER, "Muitas conexões. Tente de novo em instantes.")
            return

        ip = _client_ip(connection)
        if self._pending_by_ip.get(ip, 0) >= _MAX_PENDING_PER_IP:
            await connection.close(_CLOSE_TRY_LATER, "Muitas conexões. Tente de novo em instantes.")
            return

        self._connections += 1
        self._pending_by_ip[ip] = self._pending_by_ip.get(ip, 0) + 1
        pending = True

        def authenticated() -> None:
            nonlocal pending
            if pending:
                pending = False
                self._release_pending(ip)

        try:
            await self._welcome(connection, authenticated)
        finally:
            self._connections -= 1
            authenticated()

    def _release_pending(self, ip: str) -> None:
        left = self._pending_by_ip.get(ip, 1) - 1
        if left > 0:
            self._pending_by_ip[ip] = left
        else:
            self._pending_by_ip.pop(ip, None)

    async def _welcome(
        self, connection: ServerConnection, authenticated: Callable[[], None]
    ) -> None:
        try:
            hello = json.loads(await asyncio.wait_for(connection.recv(), _HELLO_TIMEOUT_SECONDS))
            token = str(hello.get("token", "")) if isinstance(hello, dict) else ""
        except (TimeoutError, ConnectionClosed, ValueError):
            await connection.close(_CLOSE_POLICY, "Apresentação inválida.")
            return

        user_id = await asyncio.to_thread(self._authenticate, token)
        if user_id is None:
            await connection.close(
                _CLOSE_UNAUTHORIZED, "Token recusado. Conecte de novo pelo painel."
            )
            return

        authenticated()
        old = self._links.get(user_id)
        if old is not None:
            if await _is_alive(old.extension):
                # Já há um Chrome ligado e respondendo nesta conta. Derrubá-lo deixaria quem tem
                # um token vazado tomar o lugar dele e receber o que o worker digita nos sites
                logger.warning(
                    "Segunda conexão da extensão recusada: a conta já tem um Chrome ligado."
                )
                await connection.close(
                    _CLOSE_IN_USE, "Outro Chrome já está ligado nesta conta. Desligue-o antes."
                )
                return
            # A conexão antiga morreu sem avisar (service worker reiniciou, rede caiu): a nova vale
            await self._drop(old, "Outra conexão da extensão assumiu.")
        link = _Link(user_id, connection, token)
        self._links[user_id] = link
        self._connected = tuple(self._links)
        # Depois do token, cabem as capturas de tela e os arquivos baixados. Vale a partir do
        # próximo quadro, e a extensão só manda algo depois do "welcome"
        connection.protocol.max_message_size = _MAX_MESSAGE_BYTES
        await connection.send(json.dumps({"type": "welcome", "email": _token_email(token)}))
        logger.info("Extensão conectada: as tarefas desta conta rodam no Chrome dela.")

        try:
            async for raw in connection:
                self._on_extension_message(link, json.loads(raw))
        except (ConnectionClosed, ValueError):
            pass
        finally:
            if self._links.get(user_id) is link:
                await self._drop(link, "A extensão desconectou.")
                logger.info("Extensão desconectada: as execuções desta conta esperam na fila.")
                await self._notify_leave(user_id)

    async def _notify_leave(self, user_id: uuid.UUID) -> None:
        if self._on_leave is None:
            return
        try:
            await asyncio.to_thread(self._on_leave, user_id)
        except Exception:
            # O banco pode ter caído por um instante: a marca vence sozinha em poucos minutos
            logger.warning("Não consegui anotar que a extensão saiu.", exc_info=True)

    async def _drop(self, link: _Link, reason: str, code: int = 1000) -> None:
        if self._links.get(link.user_id) is link:
            del self._links[link.user_id]
            self._connected = tuple(self._links)
        for future in link.pending.values():
            if not future.done():
                future.set_exception(RelayError(reason))
        link.pending.clear()
        link.tabs.clear()
        await link.extension.close(code, reason)
        if link.cdp is not None:
            await link.cdp.close(1000, reason)

    def _on_extension_message(self, link: _Link, message: dict[str, Any]) -> None:
        if "id" in message:
            future = link.pending.pop(message["id"], None)
            if future is None or future.done():
                return
            if "error" in message:
                future.set_exception(RelayError(str(message["error"])))
            else:
                future.set_result(message.get("result"))
            return

        event = message.get("event")
        if event == "cdpEvent":
            self._spawn(
                self._on_tab_event(
                    link,
                    message["tabId"],
                    message.get("sessionId"),
                    message["method"],
                    message.get("params") or {},
                )
            )
        elif event == "tabAttached":
            self._spawn(
                self._register_tab(
                    link, message["tabId"], message["targetInfo"], message.get("openerTabId")
                )
            )
        elif event == "tabDetached":
            self._spawn(self._forget_tab(link, message["tabId"]))

    async def _call_extension(self, link: _Link, command: str, **params: Any) -> Any:
        if self._links.get(link.user_id) is not link or self._loop is None:
            raise RelayError("A extensão não está conectada.")
        link.next_id += 1
        message_id = link.next_id
        future: asyncio.Future[Any] = self._loop.create_future()
        link.pending[message_id] = future
        try:
            await link.extension.send(
                json.dumps({"id": message_id, "method": command, "params": params})
            )
            return await asyncio.wait_for(future, _EXTENSION_TIMEOUT_SECONDS)
        except ConnectionClosed as error:
            raise RelayError("A extensão desconectou.") from error
        finally:
            link.pending.pop(message_id, None)

    # ─── Lado do Playwright ───────────────────────────────────────────────

    def _link_for_cdp_path(self, path: str) -> _Link | None:
        prefix = f"/cdp/{self._secret}/"
        if not secrets.compare_digest(path[: len(prefix)], prefix):
            return None
        try:
            user_id = uuid.UUID(path[len(prefix) :])
        except ValueError:
            return None
        return self._links.get(user_id)

    async def _serve_cdp(self, connection: ServerConnection) -> None:
        path = connection.request.path if connection.request else ""
        link = self._link_for_cdp_path(path)
        if link is None or link.cdp is not None:
            await connection.close(_CLOSE_POLICY, "A extensão desta conta não está conectada.")
            return
        link.cdp = connection
        try:
            async for raw in connection:
                # Em paralelo, como num navegador de verdade: a ordem de saída se mantém
                self._spawn(self._answer(link, json.loads(raw)))
        except (ConnectionClosed, ValueError):
            pass
        finally:
            if link.cdp is connection:
                link.cdp = None
                link.tabs.clear()
                try:
                    await self._call_extension(link, "detachAll")
                except RelayError:
                    pass

    async def _answer(self, link: _Link, message: dict[str, Any]) -> None:
        session_id = message.get("sessionId")
        reply: dict[str, Any] = {"id": message.get("id")}
        try:
            reply["result"] = await self._dispatch(
                link, message.get("method", ""), message.get("params") or {}, session_id
            )
        except (RelayError, TimeoutError) as error:
            reply["error"] = {"code": -32000, "message": str(error) or "Sem resposta da extensão."}
        if session_id:
            reply["sessionId"] = session_id
        await self._send_cdp(link, reply)

    async def _dispatch(
        self, link: _Link, method: str, params: dict[str, Any], session_id: str | None
    ) -> Any:
        if session_id:
            tab, child = self._resolve(link, session_id)
            return await self._call_extension(
                link, "send", tabId=tab.tab_id, sessionId=child, method=method, params=params
            )

        if method == "Browser.getVersion":
            return {
                "protocolVersion": "1.3",
                "product": "Chrome/Ditto-Extensao",
                "revision": "",
                "userAgent": "Mozilla/5.0 Ditto-Extensao",
                "jsVersion": "",
            }
        if method == "Browser.setDownloadBehavior":
            # O Chrome da pessoa baixa na pasta dela; o relé traz cada arquivo para cá
            link.download_path = params.get("downloadPath")
            return {}
        if method in {"Target.setAutoAttach", "Target.setDiscoverTargets"}:
            # Não anexa nada: as abas que já existem são da pessoa
            return {}
        if method == "Target.getTargetInfo":
            return {"targetInfo": _BROWSER_TARGET}
        if method == "Target.getBrowserContexts":
            return {"browserContextIds": []}
        if method == "Target.createTarget":
            created = await self._call_extension(link, "createTab")
            tab = await self._register_tab(link, created["tabId"], created["targetInfo"])
            return {"targetId": tab.target_id}
        if method == "Target.closeTarget":
            tab = next(
                (tab for tab in link.tabs.values() if tab.target_id == params.get("targetId")),
                None,
            )
            if tab is None:
                return {"success": False}
            await self._call_extension(link, "closeTab", tabId=tab.tab_id)
            return {"success": True}
        raise RelayError(f"{method} não é usado no Chrome da pessoa.")

    def _resolve(self, link: _Link, session_id: str) -> tuple[_Tab, str | None]:
        for tab in link.tabs.values():
            if tab.session_id == session_id:
                return tab, None
            if session_id in tab.children:
                return tab, session_id
        raise RelayError("Esta aba já foi fechada.")

    async def _send_cdp(self, link: _Link, message: dict[str, Any]) -> None:
        if link.cdp is None:
            return
        try:
            await link.cdp.send(json.dumps(message))
        except ConnectionClosed:
            pass

    # ─── Abas ─────────────────────────────────────────────────────────────

    async def _register_tab(
        self,
        link: _Link,
        tab_id: int,
        target_info: dict[str, Any],
        opener_tab_id: int | None = None,
    ) -> _Tab:
        existing = link.tabs.get(tab_id)
        if existing is not None:
            return existing
        link.next_session += 1
        tab = _Tab(tab_id, f"ditto-aba-{link.next_session}", target_info["targetId"])
        link.tabs[tab_id] = tab

        info = {**target_info, "attached": True}
        info.setdefault("browserContextId", "ditto-padrao")
        # Assim o Playwright entende a aba nova como janela aberta pelo site (evento popup)
        opener = link.tabs.get(opener_tab_id) if opener_tab_id is not None else None
        if opener is not None and not info.get("openerId"):
            info["openerId"] = opener.target_id
        await self._send_cdp(
            link,
            {
                "method": "Target.attachedToTarget",
                "params": {
                    "sessionId": tab.session_id,
                    "targetInfo": info,
                    "waitingForDebugger": False,
                },
            },
        )
        return tab

    async def _forget_tab(self, link: _Link, tab_id: int) -> None:
        tab = link.tabs.pop(tab_id, None)
        if tab is not None:
            await self._send_cdp(
                link,
                {
                    "method": "Target.detachedFromTarget",
                    "params": {"sessionId": tab.session_id, "targetId": tab.target_id},
                },
            )

    async def _on_tab_event(
        self,
        link: _Link,
        tab_id: int,
        child_session: str | None,
        method: str,
        params: dict[str, Any],
    ) -> None:
        tab = link.tabs.get(tab_id)
        if tab is None:
            return
        if method == "Target.attachedToTarget":
            tab.children.add(params.get("sessionId", ""))
        elif method == "Target.detachedFromTarget":
            tab.children.discard(params.get("sessionId", ""))
        elif method == "Page.downloadWillBegin":
            guid = params.get("guid")
            if not isinstance(guid, str) or not _DOWNLOAD_GUID.fullmatch(guid):
                logger.warning("Download com identificador inválido recusado.")
                return
            link.downloads[guid] = params["url"]
            await self._send_cdp(link, {"method": "Browser.downloadWillBegin", "params": params})
        elif method == "Page.downloadProgress" and not _DOWNLOAD_GUID.fullmatch(
            str(params.get("guid", ""))
        ):
            return
        elif method == "Page.downloadProgress" and params.get("state") == "completed":
            self._spawn(self._finish_download(link, params))
        elif method == "Page.downloadProgress" and params.get("state") == "canceled":
            link.downloads.pop(params.get("guid", ""), None)
            await self._send_cdp(link, {"method": "Browser.downloadProgress", "params": params})

        await self._send_cdp(
            link, {"sessionId": child_session or tab.session_id, "method": method, "params": params}
        )

    # ─── Downloads ────────────────────────────────────────────────────────

    async def _finish_download(self, link: _Link, progress: dict[str, Any]) -> None:
        """Traz o arquivo da pasta Downloads da pessoa para onde o Playwright espera e tira de
        lá, para 500 linhas não deixarem 500 arquivos para trás."""
        guid = progress["guid"]
        url = link.downloads.pop(guid, None)
        state = "canceled"
        try:
            if url is None or link.download_path is None:
                raise RelayError("Download sem origem conhecida.")
            found = await self._call_extension(link, "finishDownload", url=url)
            target = _inside(Path(link.download_path), guid)
            source = Path(found["path"])
            if self._local_downloads and _is_plain_file(source):
                await asyncio.to_thread(shutil.copyfile, source, target)
            else:
                # Worker em outra máquina: o conteúdo vem pela conexão
                read = await self._call_extension(
                    link, "readDownload", downloadId=found["downloadId"]
                )
                await asyncio.to_thread(target.write_bytes, _decode_download(read))
            await self._call_extension(link, "removeDownload", downloadId=found["downloadId"])
            state = "completed"
        except (RelayError, TimeoutError, OSError, KeyError, TypeError):
            logger.warning("Não consegui trazer um download do Chrome da pessoa.", exc_info=True)
        await self._send_cdp(
            link, {"method": "Browser.downloadProgress", "params": {**progress, "state": state}}
        )

    def _spawn(self, coroutine: Any) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


async def _is_alive(connection: ServerConnection) -> bool:
    """A conexão responde a um ping? Fechada, caída ou muda conta como morta."""
    try:
        pong = await connection.ping()
        await asyncio.wait_for(pong, _ALIVE_SECONDS)
    except (ConnectionClosed, TimeoutError):
        return False
    return True


def _token_email(token: str) -> str | None:
    """O e-mail gravado no token. Só é lido depois que o token passou pela conferência."""
    try:
        parts = token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (IndexError, ValueError, binascii.Error):
        return None
    email = payload.get("email") if isinstance(payload, dict) else None
    return email if isinstance(email, str) else None


def _client_ip(connection: ServerConnection) -> str:
    address = connection.remote_address
    peer = str(address[0]) if address else "desconhecido"
    request = connection.request
    forwarded = request.headers.get("X-Forwarded-For", "") if request is not None else ""
    return ip_behind_proxies(peer, forwarded)


def _inside(folder: Path, name: str) -> Path:
    """O caminho de `name` dentro de `folder`, ou erro se ele tentar sair dela."""
    if not _DOWNLOAD_GUID.fullmatch(name):
        raise RelayError("Identificador de download inválido.")
    base = folder.resolve()
    target = (base / name).resolve()
    if not target.is_relative_to(base) or target == base:
        raise RelayError("Identificador de download inválido.")
    return target


def _is_plain_file(path: Path) -> bool:
    """Arquivo comum (não atalho), dentro do limite de tamanho. No modo local é a extensão quem
    informa o caminho: sem isto, ela poderia pedir a cópia de qualquer arquivo da máquina."""
    try:
        return (
            path.is_file() and not path.is_symlink() and path.stat().st_size <= _MAX_DOWNLOAD_BYTES
        )
    except OSError:
        return False


def _bound_port(server: Server) -> int:
    return next(iter(server.sockets)).getsockname()[1]


def _decode_download(read: Any) -> bytes:
    encoded = read.get("base64") if isinstance(read, dict) else None
    if not isinstance(encoded, str) or len(encoded) > _MAX_DOWNLOAD_BYTES * 4 // 3 + 4:
        raise RelayError("O arquivo baixado veio vazio ou grande demais.")
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise RelayError("O arquivo baixado veio corrompido.") from error
