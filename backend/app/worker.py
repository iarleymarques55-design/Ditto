"""Processo que tira as cópias: python -m app.worker. Use a mesma imagem e o mesmo .env da API.

A linha principal cuida do que não usa navegador (análise das gravações, agendas, manutenção) e
abre ou fecha as linhas de trabalho (app/services/worker_pool.py), que rodam as execuções em
paralelo.
"""

import logging
import signal
import threading
import time
import uuid

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import UnauthorizedError
from app.services.auth_service import AuthService
from app.services.engine.extension_relay import ExtensionRelay
from app.services.worker_pool import WorkerPool
from app.services.worker_tasks import (
    analyze_next_flow,
    expire_help_requests,
    fail_stale_drafts,
    fire_due_schedules,
    purge_expired_artifacts,
    recover_stale_runs,
)

logger = logging.getLogger("ditto.worker")

_MAINTENANCE_SECONDS = 60
_PURGE_SECONDS = 60 * 60
# Ao desligar, quanto esperar cada linha terminar o que está fazendo
_SHUTDOWN_SECONDS = 10


def _authenticate_runner(token: str) -> uuid.UUID | None:
    with SessionLocal() as session:
        try:
            return AuthService(session).get_runner_user(token).id
        except UnauthorizedError:
            return None


def _start_relay() -> ExtensionRelay | None:
    """Com EXTENSION_RUNNER_PORT, as tarefas rodam no Chrome de cada pessoa, pela extensão: sem
    a extensão de alguém conectada, as execuções dessa pessoa esperam na fila em vez de falhar."""
    if not settings.extension_runner_port:
        return None
    relay = ExtensionRelay(
        settings.extension_runner_port,
        _authenticate_runner,
        host=settings.extension_relay_host,
        allowed_origins=settings.extension_origins,
        # Worker em outra máquina não lê a pasta Downloads da pessoa: nem tenta
        local_downloads=not settings.relay_is_public,
    )
    relay.start()
    logger.info("Esperando a extensão na porta %s.", relay.port)
    return relay


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stop.set())

    last_maintenance = last_purge = 0.0
    logger.info("Worker no ar.")

    relay = _start_relay()
    pool = WorkerPool(relay, stop)
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
                pool.refresh()
            except Exception:
                # O banco pode ter caído por um instante: tenta de novo na próxima volta
                logger.exception("Erro na volta do worker")

            if not worked:
                stop.wait(settings.worker_poll_seconds)
    finally:
        stop.set()
        pool.join(_SHUTDOWN_SECONDS)
        if relay is not None:
            relay.stop()
    logger.info("Worker encerrado.")


if __name__ == "__main__":
    main()
