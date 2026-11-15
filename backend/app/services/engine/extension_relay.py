"""Relé entre o Playwright e a extensão do Ditto, para as tarefas rodarem no Chrome da pessoa.

O Playwright acha que está falando com um navegador comum (CDP), mas esse "navegador" só tem
as abas que o Ditto abriu. A extensão abre cada aba ao lado da aba ativa, controla a aba com
chrome.debugger e repassa os comandos. As outras abas da pessoa nunca entram aqui.

Roda numa thread do worker e só escuta em 127.0.0.1.
"""

import asyncio
import json
import logging
import secrets
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

_HELLO_TIMEOUT_SECONDS = 10
# Um download grande pode demorar: é o maior tempo que um comando à extensão pode levar
_EXTENSION_TIMEOUT_SECONDS = 120
# Capturas de tela vêm em base64 e podem passar de alguns megabytes
_MAX_MESSAGE_BYTES = 64 * 1024 * 1024
_CLOSE_POLICY = 1008
_CLOSE_UNAUTHORIZED = 4401
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


class ExtensionRelay:
    def __init__(
        self,
        port: int,
        authenticate: Callable[[str], uuid.UUID | None],
        host: str = "127.0.0.1",
    ) -> None:
        self.host = host
        self.port = port
        self._authenticate = authenticate
        # Muda a cada vez que o worker sobe: outro programa do computador não acha o endereço
        self._secret = secrets.token_urlsafe(24)

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping: asyncio.Event | None = None
        self._startup_error: BaseException | None = None

        self._extension: ServerConnection | None = None
        self._user_id: uuid.UUID | None = None
        self._cdp: ServerConnection | None = None

        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._tabs: dict[int, _Tab] = {}
        self._next_session = 0
        self._download_path: str | None = None
        self._downloads: dict[str, str] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    # ─── Usado pelo worker ────────────────────────────────────────────────

    @property
    def cdp_url(self) -> str:
        return f"ws://{self.host}:{self.port}/cdp/{self._secret}"

    @property
    def user_id(self) -> uuid.UUID | None:
        """A conta que conectou a extensão. Nulo enquanto não há extensão."""
        return self._user_id if self._extension is not None else None

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
            async with serve(
                self._handle, self.host, self.port, max_size=_MAX_MESSAGE_BYTES
            ) as server:
                self.port = next(iter(server.sockets)).getsockname()[1]
                started.set()
                await self._stopping.wait()
        except OSError as error:
            self._startup_error = error
            started.set()

    async def _handle(self, connection: ServerConnection) -> None:
        path = connection.request.path if connection.request else ""
        if path == "/extension":
            await self._serve_extension(connection)
        elif secrets.compare_digest(path, f"/cdp/{self._secret}"):
            await self._serve_cdp(connection)
        else:
            await connection.close(_CLOSE_POLICY, "Endereço desconhecido.")

    # ─── Lado da extensão ─────────────────────────────────────────────────

    async def _serve_extension(self, connection: ServerConnection) -> None:
        # Só uma extensão do Chrome abre este socket. Uma página comum mandaria a própria origem
        origin = connection.request.headers.get("Origin", "") if connection.request else ""
        if not origin.startswith("chrome-extension://"):
            await connection.close(_CLOSE_POLICY, "Origem não autorizada.")
            return
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

        if self._extension is not None:
            # O service worker da extensão reiniciou: a conexão nova vale
            await self._drop_extension("Outra conexão da extensão assumiu.")
        self._extension = connection
        self._user_id = user_id
        await connection.send(json.dumps({"type": "welcome"}))
        logger.info("Extensão conectada: as tarefas desta conta rodam no Chrome dela.")

        try:
            async for raw in connection:
                self._on_extension_message(json.loads(raw))
        except (ConnectionClosed, ValueError):
            pass
        finally:
            if self._extension is connection:
                await self._drop_extension("A extensão desconectou.")
                logger.info("Extensão desconectada: as execuções esperam na fila.")

    async def _drop_extension(self, reason: str) -> None:
        old = self._extension
        self._extension = None
        self._user_id = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RelayError(reason))
        self._pending.clear()
        self._tabs.clear()
        if old is not None:
            await old.close(1000, reason)
        if self._cdp is not None:
            await self._cdp.close(1000, reason)

    def _on_extension_message(self, message: dict[str, Any]) -> None:
        if "id" in message:
            future = self._pending.pop(message["id"], None)
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
                    message["tabId"],
                    message.get("sessionId"),
                    message["method"],
                    message.get("params") or {},
                )
            )
        elif event == "tabAttached":
            self._spawn(
                self._register_tab(
                    message["tabId"], message["targetInfo"], message.get("openerTabId")
                )
            )
        elif event == "tabDetached":
            self._spawn(self._forget_tab(message["tabId"]))

    async def _call_extension(self, command: str, **params: Any) -> Any:
        if self._extension is None or self._loop is None:
            raise RelayError("A extensão não está conectada.")
        self._next_id += 1
        message_id = self._next_id
        future: asyncio.Future[Any] = self._loop.create_future()
        self._pending[message_id] = future
        try:
            await self._extension.send(
                json.dumps({"id": message_id, "method": command, "params": params})
            )
            return await asyncio.wait_for(future, _EXTENSION_TIMEOUT_SECONDS)
        except ConnectionClosed as error:
            raise RelayError("A extensão desconectou.") from error
        finally:
            self._pending.pop(message_id, None)

    # ─── Lado do Playwright ───────────────────────────────────────────────

    async def _serve_cdp(self, connection: ServerConnection) -> None:
        if self._extension is None or self._cdp is not None:
            await connection.close(_CLOSE_POLICY, "A extensão não está conectada.")
            return
        self._cdp = connection
        try:
            async for raw in connection:
                # Em paralelo, como num navegador de verdade: a ordem de saída se mantém
                self._spawn(self._answer(json.loads(raw)))
        except (ConnectionClosed, ValueError):
            pass
        finally:
            if self._cdp is connection:
                self._cdp = None
                self._tabs.clear()
                if self._extension is not None:
                    try:
                        await self._call_extension("detachAll")
                    except RelayError:
                        pass

    async def _answer(self, message: dict[str, Any]) -> None:
        session_id = message.get("sessionId")
        reply: dict[str, Any] = {"id": message.get("id")}
        try:
            reply["result"] = await self._dispatch(
                message.get("method", ""), message.get("params") or {}, session_id
            )
        except (RelayError, TimeoutError) as error:
            reply["error"] = {"code": -32000, "message": str(error) or "Sem resposta da extensão."}
        if session_id:
            reply["sessionId"] = session_id
        await self._send_cdp(reply)

    async def _dispatch(self, method: str, params: dict[str, Any], session_id: str | None) -> Any:
        if session_id:
            tab, child = self._resolve(session_id)
            return await self._call_extension(
                "send", tabId=tab.tab_id, sessionId=child, method=method, params=params
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
            # O Chrome da pessoa baixa na pasta dela; o relé copia cada arquivo para cá
            self._download_path = params.get("downloadPath")
            return {}
        if method in {"Target.setAutoAttach", "Target.setDiscoverTargets"}:
            # Não anexa nada: as abas que já existem são da pessoa
            return {}
        if method == "Target.getTargetInfo":
            return {"targetInfo": _BROWSER_TARGET}
        if method == "Target.getBrowserContexts":
            return {"browserContextIds": []}
        if method == "Target.createTarget":
            created = await self._call_extension("createTab")
            tab = await self._register_tab(created["tabId"], created["targetInfo"])
            return {"targetId": tab.target_id}
        if method == "Target.closeTarget":
            tab = next(
                (tab for tab in self._tabs.values() if tab.target_id == params.get("targetId")),
                None,
            )
            if tab is None:
                return {"success": False}
            await self._call_extension("closeTab", tabId=tab.tab_id)
            return {"success": True}
        raise RelayError(f"{method} não é usado no Chrome da pessoa.")

    def _resolve(self, session_id: str) -> tuple[_Tab, str | None]:
        for tab in self._tabs.values():
            if tab.session_id == session_id:
                return tab, None
            if session_id in tab.children:
                return tab, session_id
        raise RelayError("Esta aba já foi fechada.")

    async def _send_cdp(self, message: dict[str, Any]) -> None:
        if self._cdp is None:
            return
        try:
            await self._cdp.send(json.dumps(message))
        except ConnectionClosed:
            pass

    # ─── Abas ─────────────────────────────────────────────────────────────

    async def _register_tab(
        self, tab_id: int, target_info: dict[str, Any], opener_tab_id: int | None = None
    ) -> _Tab:
        existing = self._tabs.get(tab_id)
        if existing is not None:
            return existing
        self._next_session += 1
        tab = _Tab(tab_id, f"ditto-aba-{self._next_session}", target_info["targetId"])
        self._tabs[tab_id] = tab

        info = {**target_info, "attached": True}
        info.setdefault("browserContextId", "ditto-padrao")
        # Assim o Playwright entende a aba nova como janela aberta pelo site (evento popup)
        opener = self._tabs.get(opener_tab_id) if opener_tab_id is not None else None
        if opener is not None and not info.get("openerId"):
            info["openerId"] = opener.target_id
        await self._send_cdp(
            {
                "method": "Target.attachedToTarget",
                "params": {
                    "sessionId": tab.session_id,
                    "targetInfo": info,
                    "waitingForDebugger": False,
                },
            }
        )
        return tab

    async def _forget_tab(self, tab_id: int) -> None:
        tab = self._tabs.pop(tab_id, None)
        if tab is not None:
            await self._send_cdp(
                {
                    "method": "Target.detachedFromTarget",
                    "params": {"sessionId": tab.session_id, "targetId": tab.target_id},
                }
            )

    async def _on_tab_event(
        self, tab_id: int, child_session: str | None, method: str, params: dict[str, Any]
    ) -> None:
        tab = self._tabs.get(tab_id)
        if tab is None:
            return
        if method == "Target.attachedToTarget":
            tab.children.add(params.get("sessionId", ""))
        elif method == "Target.detachedFromTarget":
            tab.children.discard(params.get("sessionId", ""))
        elif method == "Page.downloadWillBegin":
            self._downloads[params["guid"]] = params["url"]
            await self._send_cdp({"method": "Browser.downloadWillBegin", "params": params})
        elif method == "Page.downloadProgress" and params.get("state") == "completed":
            self._spawn(self._finish_download(params))
        elif method == "Page.downloadProgress" and params.get("state") == "canceled":
            self._downloads.pop(params.get("guid", ""), None)
            await self._send_cdp({"method": "Browser.downloadProgress", "params": params})

        await self._send_cdp(
            {"sessionId": child_session or tab.session_id, "method": method, "params": params}
        )

    async def _finish_download(self, progress: dict[str, Any]) -> None:
        """O arquivo foi para a pasta Downloads da pessoa: copia para onde o Playwright espera
        e tira de lá, para 500 linhas não deixarem 500 arquivos para trás."""
        guid = progress["guid"]
        url = self._downloads.pop(guid, None)
        state = "canceled"
        try:
            if url is None or self._download_path is None:
                raise RelayError("Download sem origem conhecida.")
            found = await self._call_extension("finishDownload", url=url)
            source = Path(found["path"])
            if not source.is_file():
                raise RelayError("O arquivo baixado não foi encontrado.")
            await asyncio.to_thread(shutil.copyfile, source, Path(self._download_path) / guid)
            await self._call_extension("removeDownload", downloadId=found["downloadId"])
            state = "completed"
        except (RelayError, TimeoutError, OSError, KeyError):
            logger.warning("Não consegui trazer um download do Chrome da pessoa.", exc_info=True)
        await self._send_cdp(
            {"method": "Browser.downloadProgress", "params": {**progress, "state": state}}
        )

    def _spawn(self, coroutine: Any) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
