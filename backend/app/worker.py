"""Processo que tira as cópias: python -m app.worker. Use a mesma imagem e o mesmo .env da API."""

import logging
import signal
import threading
import time
import uuid

from playwright.sync_api import Browser, Playwright, sync_playwright

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import UnauthorizedError
from app.services.ai_explorer import BrowserUnavailableError
from app.services.auth_service import AuthService
from app.services.engine.browser import connect_user_browser, launch_browser
from app.services.engine.extension_relay import ExtensionRelay
from app.services.worker_tasks import (
    analyze_next_flow,
    expire_help_requests,
    fail_stale_drafts,
    fire_due_schedules,
    process_next_draft,
    process_next_run,
    purge_expired_artifacts,
    recover_stale_runs,
)

logger = logging.getLogger("ditto.worker")

_MAINTENANCE_SECONDS = 60
_PURGE_SECONDS = 60 * 60


def _authenticate_runner(token: str) -> uuid.UUID | None:
    with SessionLocal() as session:
        try:
            return AuthService(session).get_runner_user(token).id
        except UnauthorizedError:
            return None


class _WorkerBrowser:
    """Os navegadores onde as linhas rodam. Com EXTENSION_RUNNER_PORT, é o Chrome de cada pessoa
    que ligou a extensão, um por conta: sem a extensão de alguém conectada, as execuções dessa
    pessoa esperam na fila em vez de falhar."""

    def __init__(self, playwright: Playwright) -> None:
        self._playwright = playwright
        self._own_browser: Browser | None = None
        self._user_browsers: dict[uuid.UUID, Browser] = {}
        self._relay: ExtensionRelay | None = None
        if settings.extension_runner_port:
            self._relay = ExtensionRelay(
                settings.extension_runner_port,
                _authenticate_runner,
                host=settings.extension_relay_host,
                allowed_origins=settings.extension_origins,
                # Worker em outra máquina não lê a pasta Downloads da pessoa: nem tenta
                local_downloads=not settings.relay_is_public,
            )
            self._relay.start()
            logger.info("Esperando a extensão na porta %s.", self._relay.port)

    def targets(self) -> list[tuple[Browser, uuid.UUID | None]]:
        """Cada navegador e a única conta cujas execuções podem rodar nele."""
        if self._relay is None:
            current = self._own_browser
            if current is None or not current.is_connected():
                current = self._own_browser = launch_browser(self._playwright)
            return [(current, None)]

        connected = set(self._relay.connected_users())
        for owner_id, browser in list(self._user_browsers.items()):
            if owner_id not in connected or not browser.is_connected():
                self.reset(owner_id)

        targets: list[tuple[Browser, uuid.UUID | None]] = []
        for owner_id in connected:
            browser = self._user_browsers.get(owner_id)
            if browser is None:
                try:
                    browser = connect_user_browser(
                        self._playwright, self._relay.cdp_url_for(owner_id)
                    )
                except Exception:
                    logger.warning("Não consegui falar com a extensão.", exc_info=True)
                    continue
                self._user_browsers[owner_id] = browser
            targets.append((browser, owner_id))
        return targets

    def reset(self, owner_id: uuid.UUID | None) -> None:
        """Esquece a ligação com um navegador: a próxima volta conecta de novo."""
        if owner_id is None:
            browser, self._own_browser = self._own_browser, None
        else:
            browser = self._user_browsers.pop(owner_id, None)
        if browser is None:
            return
        try:
            # No Chrome da pessoa, só desconecta: as janelas dela continuam abertas
            browser.close()
        except Exception:
            logger.info("A ligação antiga com o navegador já estava fechada.")

    def close(self) -> None:
        self.reset(None)
        for owner_id in list(self._user_browsers):
            self.reset(owner_id)
        if self._relay is not None:
            self._relay.stop()


def _work_on(target: tuple[Browser, uuid.UUID | None], browser: _WorkerBrowser) -> bool:
    current, owner_id = target
    try:
        worked = process_next_run(SessionLocal, current, owner_id=owner_id)
        if owner_id is not None:
            worked = process_next_draft(SessionLocal, current, owner_id) or worked
    except BrowserUnavailableError:
        logger.warning("A ligação com o Chrome caiu. Conectando de novo.")
        browser.reset(owner_id)
        return False
    return worked


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stop.set())

    last_maintenance = last_purge = 0.0
    logger.info("Worker no ar.")

    with sync_playwright() as playwright:
        browser = _WorkerBrowser(playwright)
        try:
            while not stop.is_set():
                now = time.monotonic()
                worked = False
                try:
                    if now - last_maintenance >= _MAINTENANCE_SECONDS:
                        with SessionLocal() as session:
                            recover_stale_runs(session)
                            expire_help_requests(session)
                            fail_stale_drafts(session)
                        last_maintenance = now
                    if now - last_purge >= _PURGE_SECONDS:
                        with SessionLocal() as session:
                            purge_expired_artifacts(session)
                        last_purge = now

                    with SessionLocal() as session:
                        fire_due_schedules(session)
                        worked = analyze_next_flow(session)
                    # Uma rodada para cada conta conectada, uma depois da outra
                    for target in browser.targets():
                        worked = _work_on(target, browser) or worked
                except Exception:
                    # O banco pode ter caído por um instante: tenta de novo na próxima volta
                    logger.exception("Erro na volta do worker")

                if not worked:
                    stop.wait(settings.worker_poll_seconds)
        finally:
            browser.close()
    logger.info("Worker encerrado.")


if __name__ == "__main__":
    main()
