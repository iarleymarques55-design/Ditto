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
from app.services.auth_service import AuthService
from app.services.engine.browser import connect_user_browser, launch_browser
from app.services.engine.extension_relay import ExtensionRelay
from app.services.worker_tasks import (
    analyze_next_flow,
    expire_help_requests,
    fire_due_schedules,
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
    """O navegador onde as linhas rodam. Com EXTENSION_RUNNER_PORT, é o Chrome da pessoa, pela
    extensão: sem ela conectada, as execuções esperam na fila em vez de falhar."""

    def __init__(self, playwright: Playwright) -> None:
        self._playwright = playwright
        self._browser: Browser | None = None
        self._owner_id: uuid.UUID | None = None
        self._relay: ExtensionRelay | None = None
        if settings.extension_runner_port:
            self._relay = ExtensionRelay(settings.extension_runner_port, _authenticate_runner)
            self._relay.start()
            logger.info("Esperando a extensão na porta %s.", self._relay.port)

    def get(self) -> tuple[Browser, uuid.UUID | None] | None:
        """O navegador e, no Chrome da pessoa, a única conta cujas execuções podem rodar nele."""
        if self._relay is None:
            if self._browser is None or not self._browser.is_connected():
                self._browser = launch_browser(self._playwright)
            return self._browser, None

        owner_id = self._relay.user_id
        connected = self._browser is not None and self._browser.is_connected()
        if connected and owner_id == self._owner_id:
            return self._browser, owner_id
        if connected:
            # A extensão trocou de conta: a conexão antiga não serve mais
            self._browser.close()
        self._browser = None
        if owner_id is None:
            return None
        try:
            self._browser = connect_user_browser(self._playwright, self._relay.cdp_url)
        except Exception:
            logger.warning("Não consegui falar com a extensão.", exc_info=True)
            return None
        self._owner_id = owner_id
        return self._browser, owner_id

    def close(self) -> None:
        # No Chrome da pessoa, só desconecta: as janelas dela continuam abertas
        if self._browser is not None and self._browser.is_connected():
            self._browser.close()
        if self._relay is not None:
            self._relay.stop()


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
        browser.get()
        try:
            while not stop.is_set():
                now = time.monotonic()
                worked = False
                try:
                    if now - last_maintenance >= _MAINTENANCE_SECONDS:
                        with SessionLocal() as session:
                            recover_stale_runs(session)
                            expire_help_requests(session)
                        last_maintenance = now
                    if now - last_purge >= _PURGE_SECONDS:
                        with SessionLocal() as session:
                            purge_expired_artifacts(session)
                        last_purge = now

                    with SessionLocal() as session:
                        fire_due_schedules(session)
                        worked = analyze_next_flow(session)
                    target = browser.get()
                    if target is not None:
                        current, owner_id = target
                        worked = (
                            process_next_run(SessionLocal, current, owner_id=owner_id) or worked
                        )
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
