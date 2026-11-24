"""Processo que tira as cópias: python -m app.worker. Use a mesma imagem e o mesmo .env da API.

A linha principal cuida do que é rápido (agendas, manutenção) e abre ou fecha as linhas de
trabalho (app/services/worker_pool.py), que rodam as execuções em paralelo. O que pode demorar
(análise das gravações, que chama a IA, e a limpeza dos arquivos vencidos) roda numa linha
própria, para nunca segurar a principal: é ela que liga a linha de cada pessoa que conecta a
extensão, e é ela que dá o sinal de vida conferido pelo Docker.
"""

import logging
import signal
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

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
_PURGE_SECONDS = 10 * 60
# Ao desligar, quanto esperar (no total) as linhas devolverem as execuções à fila. O Docker
# precisa esperar mais que isso antes de derrubar o processo (stop_grace_period no compose)
SHUTDOWN_SECONDS = 20
# A cada volta da linha principal, o horário vai para este arquivo. O healthcheck do Docker
# confere se ele foi tocado há pouco: a linha principal nunca fica mais de alguns segundos parada
WORKER_ALIVE_FILE = Path(tempfile.gettempdir()) / "ditto-worker-alive"

SessionFactory = Callable[[], Session]


class Pool(Protocol):
    def refresh(self) -> None: ...

    def join(self, timeout: float) -> None: ...


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


def mark_alive(path: Path = WORKER_ALIVE_FILE) -> None:
    try:
        path.write_text(str(time.time()), encoding="ascii")
    except OSError:
        logger.debug("Não consegui gravar o sinal de vida em %s.", path, exc_info=True)


@dataclass
class MainLoop:
    """Uma volta da linha principal. Separada do processo para poder ser testada."""

    session_factory: SessionFactory
    pool: Pool
    alive_file: Path = WORKER_ALIVE_FILE
    last_maintenance: float = float("-inf")

    def tick(self, now: float) -> None:
        mark_alive(self.alive_file)
        try:
            if now - self.last_maintenance >= _MAINTENANCE_SECONDS:
                with self.session_factory() as session:
                    recover_stale_runs(session)
                    expire_help_requests(session)
                    fail_stale_drafts(session)
                self.last_maintenance = now
            with self.session_factory() as session:
                fire_due_schedules(session)
            self.pool.refresh()
        except Exception:
            # O banco pode ter caído por um instante: tenta de novo na próxima volta
            logger.exception("Erro na volta do worker")


class BackgroundLane(threading.Thread):
    """Análise das gravações e limpeza dos arquivos vencidos, fora da linha principal."""

    def __init__(self, session_factory: SessionFactory, stop: threading.Event) -> None:
        super().__init__(name="analise-e-limpeza", daemon=True)
        self._session_factory = session_factory
        self._stopping = stop
        self._last_purge = float("-inf")

    def run(self) -> None:
        while not self._stopping.is_set():
            worked = self.step(time.monotonic())
            if not worked:
                self._stopping.wait(settings.worker_poll_seconds)

    def step(self, now: float) -> bool:
        """Se trabalhou (havia uma gravação para analisar)."""
        try:
            if now - self._last_purge >= _PURGE_SECONDS:
                with self._session_factory() as session:
                    purge_expired_artifacts(session)
                self._last_purge = now
            with self._session_factory() as session:
                return analyze_next_flow(session)
        except Exception:
            logger.exception("Erro na análise ou na limpeza")
            return False


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stop.set())

    logger.info("Worker no ar.")
    relay = _start_relay()
    pool = WorkerPool(relay, stop)
    loop = MainLoop(SessionLocal, pool)
    background = BackgroundLane(SessionLocal, stop)
    background.start()
    try:
        while not stop.is_set():
            loop.tick(time.monotonic())
            stop.wait(settings.worker_poll_seconds)
    finally:
        stop.set()
        deadline = time.monotonic() + SHUTDOWN_SECONDS
        pool.join(SHUTDOWN_SECONDS)
        background.join(max(0.0, deadline - time.monotonic()))
        if relay is not None:
            relay.stop()
    logger.info("Worker encerrado.")


if __name__ == "__main__":
    main()
