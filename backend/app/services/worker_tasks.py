"""O que o worker faz a cada volta. Separado do processo para poder ser testado."""

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from playwright.sync_api import Browser
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DomainError
from app.models.enums import HelpStatus, ItemStatus, LogLevel, RunStatus, RunTrigger
from app.models.run import Run
from app.repositories.flow_repository import FlowRepository
from app.repositories.repair_repository import RepairRepository
from app.repositories.run_repository import RunRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.services import run_lifecycle, storage
from app.services.analyzer import analyze_flow
from app.services.engine.llm_repair import LlmRepairer
from app.services.llm_client import LlmClient
from app.services.run_processor import RunProcessor, items_of, requeue_item_after_crash
from app.services.schedule_service import next_occurrence

logger = logging.getLogger(__name__)

_HEARTBEAT_SECONDS = 30


def analyze_next_flow(session: Session, client: LlmClient | None = None) -> bool:
    flow = FlowRepository(session).claim_for_analysis()
    if flow is None:
        session.rollback()
        return False
    analyze_flow(session, flow, client)
    return True


def recover_stale_runs(session: Session) -> int:
    """Um worker que caiu para de dar sinal: a execução volta para a fila, sem refazer o que já terminou."""
    limit = datetime.now(UTC) - timedelta(minutes=settings.stale_run_minutes)
    stale = RunRepository(session).list_stale(limit)
    for run in stale:
        for item in items_of(session, run):
            requeue_item_after_crash(item)
        run.status = RunStatus.QUEUED
        run_lifecycle.add_log(
            session, run, LogLevel.INFO, "o processo parou no meio: execução de volta à fila"
        )
    session.commit()
    return len(stale)


def expire_help_requests(session: Session) -> int:
    expired = RepairRepository(session).claim_expired_help(datetime.now(UTC))
    for request in expired:
        request.status = HelpStatus.EXPIRED
        run = session.get(Run, request.run_id)
        run_lifecycle.fail_item(request.item, "Ninguém respondeu ao pedido a tempo.")
        run_lifecycle.add_log(
            session,
            run,
            LogLevel.FAILURE,
            f"linha {request.item.position}: pedido expirou sem resposta",
        )
        run_lifecycle.resume(session, run)
    session.commit()
    return len(expired)


def fire_due_schedules(session: Session) -> int:
    now = datetime.now(UTC)
    due = ScheduleRepository(session).claim_due(now)
    for schedule in due:
        schedule.last_run_at = now
        schedule.next_run_at = next_occurrence(schedule.cron, schedule.timezone, now)
        try:
            run_lifecycle.ensure_can_run(session, schedule.flow)
            run_lifecycle.create_run(
                session,
                schedule.flow,
                schedule.rows,
                trigger=RunTrigger.SCHEDULE,
                timezone=schedule.timezone,
            )
        except DomainError as error:
            # A próxima data já foi calculada: um problema desta vez não trava a agenda para sempre
            logger.warning("Agenda %s não disparou: %s", schedule.id, error.detail)
    session.commit()
    return len(due)


def purge_expired_artifacts(session: Session) -> int:
    limit = datetime.now(UTC) - timedelta(days=settings.artifact_retention_days)
    runs = RunRepository(session)
    artifacts = runs.list_expired_artifacts(limit)
    for artifact in artifacts:
        storage.delete(artifact.storage_key)
    if artifacts:
        runs.delete_artifacts([artifact.id for artifact in artifacts])
    session.commit()
    return len(artifacts)


def claim_next_run(session: Session) -> uuid.UUID | None:
    runs = RunRepository(session)
    run = runs.claim_queued()
    if run is None:
        session.rollback()
        return None

    now = datetime.now(UTC)
    run.status = RunStatus.RUNNING
    run.started_at = run.started_at or now
    run.heartbeat_at = now
    for item in items_of(session, run):
        if item.status == ItemStatus.RUNNING:
            item.status = ItemStatus.PENDING
    session.commit()
    return run.id


def _heartbeat_loop(
    session_factory: Callable[[], Session], run_id: uuid.UUID, stop: threading.Event
) -> None:
    while not stop.wait(_HEARTBEAT_SECONDS):
        with session_factory() as session:
            RunRepository(session).touch_heartbeat(run_id, datetime.now(UTC))
            session.commit()


def process_next_run(
    session_factory: Callable[[], Session],
    browser: Browser,
    repairer: LlmRepairer | None = None,
) -> bool:
    with session_factory() as session:
        run_id = claim_next_run(session)
    if run_id is None:
        return False

    stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop, args=(session_factory, run_id, stop), daemon=True
    )
    heartbeat.start()
    try:
        with session_factory() as session:
            RunProcessor(session, session.get(Run, run_id), browser, repairer).process()
    except Exception:
        # Para a execução, nunca o worker: as outras da fila continuam
        logger.exception("Falha inesperada na execução %s", run_id)
        with session_factory() as session:
            run = session.get(Run, run_id)
            # A conta pode ter sido excluída enquanto a execução rodava
            if run is not None and run.status == RunStatus.RUNNING:
                run_lifecycle.skip_open_items(session, run)
                run_lifecycle.add_log(
                    session, run, LogLevel.FAILURE, "erro interno: execução interrompida"
                )
                run_lifecycle.finalize(session, run)
                session.commit()
    finally:
        stop.set()
        heartbeat.join(timeout=5)
    return True
