"""As linhas de trabalho do worker, que tiram as cópias em paralelo.

Com a extensão, cada conta conectada ganha a própria linha, com o próprio navegador (o Chrome
dela): a execução longa de uma pessoa, ou uma pergunta do Criar com IA esperando resposta, não
segura a fila das outras. A linha nasce quando a pessoa conecta e termina quando ela desconecta.

Sem a extensão, WORKER_CONCURRENCY linhas dividem a mesma fila, cada uma com o seu Chromium.
As travas do banco (SKIP LOCKED) garantem que duas linhas nunca pegam a mesma execução.

O Playwright não pode ser usado por mais de uma thread: cada linha abre o seu.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from playwright.sync_api import Browser, Playwright, sync_playwright

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import worker_tasks
from app.services.ai_explorer import BrowserUnavailableError
from app.services.engine.browser import connect_user_browser, launch_browser

logger = logging.getLogger("ditto.worker")

# Depois de falhar ao abrir o navegador, quanto esperar antes de tentar de novo
_RETRY_OPEN_SECONDS = 5

OpenBrowser = Callable[[Playwright], Browser]
PlaywrightFactory = Callable[[], AbstractContextManager[Any]]


class Relay(Protocol):
    def connected_users(self) -> list[uuid.UUID]: ...

    def cdp_url_for(self, user_id: uuid.UUID) -> str: ...


class Lane(threading.Thread):
    """Uma linha de trabalho: um navegador e a fila de uma conta (ou de todas, sem a extensão)."""

    def __init__(
        self,
        name: str,
        owner_id: uuid.UUID | None,
        open_browser: OpenBrowser,
        still_wanted: Callable[[], bool],
        stop: threading.Event,
        playwright_factory: PlaywrightFactory = sync_playwright,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.owner_id = owner_id
        self._open_browser = open_browser
        self._still_wanted = still_wanted
        # Não pode se chamar _stop: o threading.Thread já tem um método interno com esse nome
        self._stopping = stop
        self._playwright_factory = playwright_factory

    def run(self) -> None:
        try:
            with self._playwright_factory() as playwright:
                self._loop(playwright)
        except Exception:
            logger.exception("A linha de trabalho %s parou com erro.", self.name)

    def _loop(self, playwright: Playwright) -> None:
        browser: Browser | None = None
        try:
            while not self._stopping.is_set() and self._still_wanted():
                if browser is None or not browser.is_connected():
                    browser = self._open(playwright)
                    if browser is None:
                        self._stopping.wait(_RETRY_OPEN_SECONDS)
                        continue
                worked = self._work(browser)
                if worked is None:
                    # A ligação com o Chrome caiu: a próxima volta abre outra
                    _close(browser)
                    browser = None
                elif not worked:
                    self._stopping.wait(settings.worker_poll_seconds)
        finally:
            if browser is not None:
                _close(browser)

    def _open(self, playwright: Playwright) -> Browser | None:
        try:
            return self._open_browser(playwright)
        except Exception:
            logger.warning("A linha %s não conseguiu abrir o navegador.", self.name, exc_info=True)
            return None

    def _work(self, browser: Browser) -> bool | None:
        """Se trabalhou; None quando o navegador precisa ser aberto de novo."""
        try:
            worked = worker_tasks.process_next_run(SessionLocal, browser, owner_id=self.owner_id)
            if self.owner_id is not None:
                # O Criar com IA só existe no Chrome da pessoa
                worked = (
                    worker_tasks.process_next_draft(SessionLocal, browser, self.owner_id) or worked
                )
        except BrowserUnavailableError:
            logger.warning(
                "A ligação com o Chrome da linha %s caiu. Conectando de novo.", self.name
            )
            return None
        except Exception:
            # O banco pode ter caído por um instante: tenta de novo na próxima volta
            logger.exception("Erro na linha de trabalho %s.", self.name)
            return False
        return worked


def _close(browser: Browser) -> None:
    try:
        # No Chrome da pessoa, só desconecta: as janelas dela continuam abertas
        browser.close()
    except Exception:
        logger.info("A ligação com o navegador já estava fechada.")


class WorkerPool:
    """Abre e fecha linhas de trabalho conforme quem está conectado. O worker chama `refresh` a
    cada volta."""

    def __init__(
        self,
        relay: Relay | None,
        stop: threading.Event,
        playwright_factory: PlaywrightFactory = sync_playwright,
        launch: OpenBrowser = launch_browser,
        connect: Callable[[Playwright, str], Browser] = connect_user_browser,
    ) -> None:
        self._relay = relay
        self._stopping = stop
        self._playwright_factory = playwright_factory
        self._launch = launch
        self._connect = connect
        self._lanes: dict[Any, Lane] = {}
        self._warned_full = False

    def lanes(self) -> list[Lane]:
        return [lane for lane in self._lanes.values() if lane.is_alive()]

    def refresh(self) -> None:
        # Linhas que terminaram (pessoa desconectou, erro) saem da lista
        self._lanes = {key: lane for key, lane in self._lanes.items() if lane.is_alive()}
        if self._relay is None:
            self._fill_own_browsers()
        else:
            self._follow_connected_accounts(self._relay)

    def _fill_own_browsers(self) -> None:
        for slot in range(settings.worker_concurrency):
            if slot not in self._lanes:
                self._start(slot, f"linha-{slot + 1}", None, self._launch, lambda: True)

    def _follow_connected_accounts(self, relay: Relay) -> None:
        for owner_id in relay.connected_users():
            if owner_id in self._lanes:
                continue
            if len(self._lanes) >= settings.worker_max_accounts:
                if not self._warned_full:
                    logger.warning(
                        "Limite de %s contas ao mesmo tempo: as outras esperam uma vaga.",
                        settings.worker_max_accounts,
                    )
                    self._warned_full = True
                return
            url = relay.cdp_url_for(owner_id)
            self._start(
                owner_id,
                f"conta-{str(owner_id)[:8]}",
                owner_id,
                lambda playwright, url=url: self._connect(playwright, url),
                lambda owner_id=owner_id: owner_id in relay.connected_users(),
            )
        self._warned_full = False

    def _start(
        self,
        key: Any,
        name: str,
        owner_id: uuid.UUID | None,
        open_browser: OpenBrowser,
        still_wanted: Callable[[], bool],
    ) -> None:
        lane = Lane(
            name, owner_id, open_browser, still_wanted, self._stopping, self._playwright_factory
        )
        self._lanes[key] = lane
        lane.start()
        logger.info("Linha de trabalho %s aberta.", name)

    def join(self, timeout: float) -> None:
        for lane in list(self._lanes.values()):
            lane.join(timeout)
