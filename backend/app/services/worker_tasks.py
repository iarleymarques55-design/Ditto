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
from app.models.ai_draft import AiDraft
from app.models.enums import AiDraftStatus, HelpStatus, ItemStatus, LogLevel, RunStatus, RunTrigger
from app.models.run import Run
from app.repositories.ai_draft_repository import AiDraftRepository
from app.repositories.flow_repository import FlowRepository
from app.repositories.repair_repository import RepairRepository
from app.repositories.run_repository import RunRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.services import run_lifecycle, storage
from app.services.ai_explorer import AiExplorer, BrowserUnavailableError, claim_next_draft
from app.services.analyzer import analyze_flow, prepare_for_manual_review
from app.services.engine.llm_explorer import LlmExplorer
from app.services.engine.llm_repair import LlmRepairer
from app.services.llm_client import LlmClient, LlmUnavailableError
from app.services.run_lifecycle import HEARTBEAT_SECONDS
from app.services.run_processor import (
    RunProcessor,
    diagnostics_key_for,
    requeue_item_after_crash,
)
from app.services.schedule_service import next_occurrence

logger = logging.getLogger(__name__)

# A limpeza apaga em lotes, até acabar o que venceu. O teto por volta só existe para a volta
# não ficar presa por muito tempo; o que sobrar sai na próxima
_PURGE_BATCH = 200
_PURGE_MAX_BATCHES = 10


class _WithoutLlm:
    """Para a segunda tentativa da análise: as regras do Ditto, sem chamar a IA."""

    def chat_json(self, _system: str, _user: str) -> dict:
        raise LlmUnavailableError("análise sem a IA")


def analyze_next_flow(session: Session, client: LlmClient | None = None) -> bool:
    """Analisa a gravação mais antiga na fila. Uma falha inesperada nunca deixa a gravação
    presa em "analisando" (ela voltaria em toda volta e seguraria as outras): tenta de novo
    sem a IA e, se ainda falhar, libera a gravação para a pessoa revisar à mão."""
    repository = FlowRepository(session)
    flow = repository.claim_for_analysis()
    if flow is None:
        session.rollback()
        return False
    flow_id = flow.id
    try:
        analyze_flow(session, flow, client)
        return True
    except Exception:
        logger.exception("A análise da gravação %s falhou. Tentando sem a IA.", flow_id)
        session.rollback()

    flow = repository.lock_for_analysis(flow_id)
    if flow is None:
        session.rollback()
        return True
    try:
        analyze_flow(session, flow, _WithoutLlm())
        return True
    except Exception:
        logger.exception("A análise sem a IA da gravação %s também falhou.", flow_id)
        session.rollback()

    flow = repository.lock_for_analysis(flow_id)
    if flow is not None:
        prepare_for_manual_review(flow)
    session.commit()
    return True


def recover_stale_runs(session: Session) -> int:
    """Um worker que caiu para de dar sinal: a execução volta para a fila, sem refazer o que já terminou."""
    limit = datetime.now(UTC) - timedelta(minutes=settings.stale_run_minutes)
    runs = RunRepository(session)
    stale = runs.list_stale(limit)
    for run in stale:
        for item in runs.items_of(run.id):
            requeue_item_after_crash(item)
        run.status = RunStatus.QUEUED
        run_lifecycle.add_log(
            session, run, LogLevel.INFO, "o processo parou no meio: execução de volta à fila"
        )
    session.commit()
    return len(stale)


def fail_stale_drafts(session: Session) -> int:
    """Um rascunho sem sinal do worker não volta para a fila: a aba que a IA usava já se perdeu."""
    limit = datetime.now(UTC) - timedelta(minutes=settings.stale_run_minutes)
    count = AiDraftRepository(session).fail_stale(
        limit, "O worker parou no meio. Peça de novo para a IA criar a tarefa."
    )
    session.commit()
    return count


def process_next_draft(
    session_factory: Callable[[], Session],
    browser: Browser,
    owner_id: uuid.UUID,
    explorer: LlmExplorer | None = None,
) -> bool:
    """A IA só monta tarefas no Chrome da pessoa, e só as da conta que ligou a extensão."""
    with session_factory() as session:
        draft = claim_next_draft(session, owner_id)
        if draft is None:
            return False
        try:
            AiExplorer(session, draft, browser, explorer).run()
        except BrowserUnavailableError:
            _retry_draft_later(session, draft)
            raise
        except Exception:
            # Para o rascunho, nunca o worker
            logger.exception("Falha inesperada no rascunho %s", draft.id)
            session.rollback()
            AiDraftRepository(session).update_if_open(
                draft.id,
                {
                    "status": AiDraftStatus.FAILED,
                    "error": "Erro interno ao montar a tarefa.",
                    "question": None,
                },
            )
            session.commit()
    return True


_RECONNECTING = "A ligação com o Chrome caiu. Reconectando para tentar de novo."


def _retry_draft_later(session: Session, draft: AiDraft) -> None:
    """Uma volta para a fila, enquanto o worker reconecta. Na segunda queda, o pedido falha."""
    session.rollback()
    events = list(draft.events or [])
    if any(event.get("text") == _RECONNECTING for event in events):
        values = {
            "status": AiDraftStatus.FAILED,
            "error": "O Chrome não respondeu. Confira se a extensão do Ditto está ligada.",
            "question": None,
        }
    else:
        entry = {"at": datetime.now(UTC).isoformat(), "kind": "info", "text": _RECONNECTING}
        values = {"status": AiDraftStatus.QUEUED, "events": [*events, entry]}
    AiDraftRepository(session).update_if_open(draft.id, values)
    session.commit()


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
    runs = RunRepository(session)
    for schedule in due:
        schedule.last_run_at = now
        schedule.next_run_at = next_occurrence(schedule.cron, schedule.timezone, now)
        if runs.has_open_for_flow(schedule.flow_id):
            # A anterior ainda não terminou (o Chrome da pessoa pode estar desligado): uma cópia
            # por vez, em vez de uma fila que cresce a cada horário
            logger.info(
                "Agenda %s pulou este horário: a execução anterior não terminou.", schedule.id
            )
            continue
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
    """Primeiro sai do banco, depois do armazenamento: se apagar um arquivo falhar, sobra um
    arquivo sem dono, e nunca um registro apontando para um arquivo que não existe mais."""
    limit = datetime.now(UTC) - timedelta(days=settings.artifact_retention_days)
    runs = RunRepository(session)
    total = 0
    for _ in range(_PURGE_MAX_BATCHES):
        artifacts = runs.list_expired_artifacts(limit, _PURGE_BATCH)
        if not artifacts:
            break
        keys = [artifact.storage_key for artifact in artifacts]
        # Os detalhes da falha ficam ao lado da tela, sem registro próprio: saem junto com ela
        keys.extend(
            diagnostics
            for artifact in artifacts
            if (diagnostics := diagnostics_key_for(artifact.storage_key)) is not None
        )
        runs.delete_artifacts([artifact.id for artifact in artifacts])
        session.commit()
        for key in keys:
            try:
                storage.delete(key)
            except Exception:
                logger.warning("Não consegui apagar um arquivo vencido do armazenamento.")
        total += len(artifacts)
        if len(artifacts) < _PURGE_BATCH:
            break
    return total


def claim_next_run(session: Session, owner_id: uuid.UUID | None = None) -> uuid.UUID | None:
    """Com `owner_id`, só pega execuções daquela conta: no Chrome da pessoa, nunca roda
    a tarefa de outra."""
    runs = RunRepository(session)
    run = runs.claim_queued(owner_id)
    if run is None:
        session.rollback()
        return None

    now = datetime.now(UTC)
    run.status = RunStatus.RUNNING
    run.started_at = run.started_at or now
    run.heartbeat_at = now
    for item in runs.items_of(run.id):
        if item.status == ItemStatus.RUNNING:
            item.status = ItemStatus.PENDING
    session.commit()
    return run.id


def _heartbeat_loop(
    session_factory: Callable[[], Session], run_id: uuid.UUID, stop: threading.Event
) -> None:
    """Avisa que a execução continua viva enquanto um passo longo roda. Uma falha do banco não
    pode parar o aviso: sem ele, a execução voltaria para a fila e rodaria duas vezes."""
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with session_factory() as session:
                RunRepository(session).touch_heartbeat(run_id, datetime.now(UTC))
                session.commit()
        except Exception:
            logger.warning(
                "Não consegui avisar que a execução %s continua viva. Tento de novo.",
                run_id,
                exc_info=True,
            )


def process_next_run(
    session_factory: Callable[[], Session],
    browser: Browser,
    repairer: LlmRepairer | None = None,
    owner_id: uuid.UUID | None = None,
    stop_worker: threading.Event | None = None,
) -> bool:
    """Com `stop_worker` ligado (o worker está desligando), a execução volta para a fila entre
    uma linha e outra, em vez de seguir até ser derrubada."""
    with session_factory() as session:
        run_id = claim_next_run(session, owner_id)
    if run_id is None:
        return False

    stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop, args=(session_factory, run_id, stop), daemon=True
    )
    heartbeat.start()
    try:
        with session_factory() as session:
            RunProcessor(
                session, session.get(Run, run_id), browser, repairer, stop=stop_worker
            ).process()
    except BrowserUnavailableError:
        # A execução já voltou para a fila: quem chama abre o navegador de novo
        raise
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
