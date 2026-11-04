"""Processo que tira as cópias: python -m app.worker. Use a mesma imagem e o mesmo .env da API."""

import logging
import signal
import threading
import time

from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.engine.browser import launch_browser
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
        browser = launch_browser(playwright)
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
                    worked = process_next_run(SessionLocal, browser) or worked
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
