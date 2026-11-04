import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.schedule import Schedule
from app.repositories.flow_repository import FlowRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.schedule import ScheduleResponse, ScheduleUpdate
from app.services import presenters, run_lifecycle
from app.services.run_service import ensure_valid_timezone, read_rows

_MIN_INTERVAL_SECONDS = 15 * 60


def next_occurrence(cron: str, timezone: str, after: datetime | None = None) -> datetime:
    """O cron é contado no fuso da pessoa; o banco guarda em UTC."""
    base = (after or datetime.now(UTC)).astimezone(ZoneInfo(timezone))
    return croniter(cron, base).get_next(datetime).astimezone(UTC)


def _ensure_valid_cron(cron: str, timezone: str) -> None:
    if not croniter.is_valid(cron) or len(cron.split()) != 5:
        raise BusinessRuleError("O horário da agenda é inválido.")
    first = next_occurrence(cron, timezone)
    second = next_occurrence(cron, timezone, first)
    if (second - first).total_seconds() < _MIN_INTERVAL_SECONDS:
        raise BusinessRuleError("A agenda pode rodar no máximo a cada 15 minutos.")


class ScheduleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.schedules = ScheduleRepository(session)
        self.flows = FlowRepository(session)

    def _get(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> Schedule:
        schedule = self.schedules.get_owned(schedule_id, owner_id)
        if schedule is None:
            raise NotFoundError("Esta agenda não foi encontrada.")
        return schedule

    def create(
        self,
        owner_id: uuid.UUID,
        flow_id: uuid.UUID,
        cron: str,
        timezone: str,
        file_name: str | None,
        content: bytes | None,
    ) -> ScheduleResponse:
        ensure_valid_timezone(timezone)
        _ensure_valid_cron(cron, timezone)

        flow = self.flows.get_owned(flow_id, owner_id)
        if flow is None:
            raise NotFoundError("Esta tarefa não foi encontrada.")
        run_lifecycle.ensure_can_run(self.session, flow)
        if self.schedules.get_for_flow(flow.id):
            raise ConflictError("Esta tarefa já tem uma agenda.")

        schedule = self.schedules.add(
            Schedule(
                owner_id=owner_id,
                flow_id=flow.id,
                cron=cron,
                timezone=timezone,
                next_run_at=next_occurrence(cron, timezone),
                rows=read_rows(flow, file_name, content),
            )
        )
        self.session.commit()
        return presenters.schedule_response(schedule)

    def list(self, owner_id: uuid.UUID, limit: int, offset: int) -> list[ScheduleResponse]:
        return [
            presenters.schedule_response(item)
            for item in self.schedules.list_owned(owner_id, limit, offset)
        ]

    def update(
        self, schedule_id: uuid.UUID, owner_id: uuid.UUID, payload: ScheduleUpdate
    ) -> ScheduleResponse:
        schedule = self._get(schedule_id, owner_id)
        timezone = ensure_valid_timezone(payload.timezone or schedule.timezone)
        cron = payload.cron or schedule.cron
        _ensure_valid_cron(cron, timezone)

        schedule.cron = cron
        schedule.timezone = timezone
        if payload.enabled is not None:
            schedule.enabled = payload.enabled
        # Ao retomar depois de uma pausa, os horários perdidos não disparam de uma vez
        schedule.next_run_at = next_occurrence(cron, timezone)
        self.session.commit()
        return presenters.schedule_response(schedule)

    def delete(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        self.schedules.delete(self._get(schedule_id, owner_id))
        self.session.commit()
