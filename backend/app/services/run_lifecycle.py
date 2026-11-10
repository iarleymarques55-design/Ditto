"""Mudanças de estado de uma execução, usadas pela API e pelo worker."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError
from app.models.enums import FlowStatus, ItemStatus, LogLevel, RunStatus, RunTrigger
from app.models.flow import Flow
from app.models.run import Run, RunItem, RunLogEntry
from app.repositories.credential_repository import CredentialRepository
from app.repositories.repair_repository import RepairRepository

_MAX_LABEL = 200
_CONCLUDED = {ItemStatus.SUCCEEDED, ItemStatus.REPAIRED}
_OPEN_ITEM = {ItemStatus.PENDING, ItemStatus.RUNNING}


def add_log(session: Session, run: Run, level: LogLevel, message: str) -> None:
    session.add(RunLogEntry(run_id=run.id, level=level, message=message))


def ensure_can_run(session: Session, flow: Flow) -> None:
    if flow.status != FlowStatus.ACTIVE:
        raise BusinessRuleError("Revise esta tarefa antes de rodar.")
    if any(step.credential_field for step in flow.steps):
        found = CredentialRepository(session).list_for_domains(flow.owner_id, flow.allowed_domains)
        if not found:
            raise BusinessRuleError("Salve o acesso ao portal antes de rodar esta tarefa.")


def create_run(
    session: Session,
    flow: Flow,
    rows: list[dict[str, str]],
    *,
    trigger: RunTrigger,
    timezone: str,
) -> Run:
    run = Run(owner_id=flow.owner_id, flow_id=flow.id, trigger=trigger, timezone=timezone)
    for position, row in enumerate(rows, start=1):
        label = next((value for value in row.values() if value), "") or f"Cópia {position}"
        run.items.append(RunItem(position=position, label=label[:_MAX_LABEL], input=row))
    session.add(run)
    session.flush()
    add_log(
        session,
        run,
        LogLevel.INFO,
        f"{len(rows)} {'cópia' if len(rows) == 1 else 'cópias'} na fila",
    )
    return run


def _items_of(session: Session, run: Run) -> list[RunItem]:
    return list(
        session.scalars(select(RunItem).where(RunItem.run_id == run.id).order_by(RunItem.position))
    )


def finalize(session: Session, run: Run) -> None:
    """Decide o resultado pelo que aconteceu com as linhas."""
    items = _items_of(session, run)
    done = sum(item.status in _CONCLUDED for item in items)
    if items and done == len(items):
        run.status = RunStatus.SUCCEEDED
    elif done == 0:
        run.status = RunStatus.FAILED
    else:
        run.status = RunStatus.PARTIAL
    run.finished_at = datetime.now(UTC)
    add_log(
        session,
        run,
        LogLevel.OK if run.status == RunStatus.SUCCEEDED else LogLevel.INFO,
        f"{done} de {len(items)} concluídas",
    )


def skip_open_items(session: Session, run: Run) -> None:
    for item in _items_of(session, run):
        if item.status in _OPEN_ITEM or item.status == ItemStatus.WAITING_HUMAN:
            item.status = ItemStatus.SKIPPED
            item.finished_at = datetime.now(UTC)


def resume(session: Session, run: Run) -> None:
    """Depois de uma resposta: volta para a fila se ainda há trabalho e ninguém mais está sendo esperado."""
    session.flush()
    if RepairRepository(session).has_open_help(run.id):
        return
    if any(item.status in _OPEN_ITEM for item in _items_of(session, run)):
        run.status = RunStatus.QUEUED
    else:
        finalize(session, run)


def fail_item(item: RunItem, message: str) -> None:
    item.status = ItemStatus.FAILED
    item.error_message = message
    item.finished_at = datetime.now(UTC)
