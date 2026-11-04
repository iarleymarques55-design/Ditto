import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.schedule import Schedule


class ScheduleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, schedule: Schedule) -> Schedule:
        self.session.add(schedule)
        return schedule

    def delete(self, schedule: Schedule) -> None:
        self.session.delete(schedule)

    def get_owned(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> Schedule | None:
        return self.session.scalar(
            select(Schedule).where(Schedule.id == schedule_id, Schedule.owner_id == owner_id)
        )

    def get_for_flow(self, flow_id: uuid.UUID) -> Schedule | None:
        return self.session.scalar(select(Schedule).where(Schedule.flow_id == flow_id))

    def list_for_flows(self, flow_ids: list[uuid.UUID]) -> list[Schedule]:
        if not flow_ids:
            return []
        return list(self.session.scalars(select(Schedule).where(Schedule.flow_id.in_(flow_ids))))

    def list_owned(self, owner_id: uuid.UUID, limit: int, offset: int) -> list[Schedule]:
        return list(
            self.session.scalars(
                select(Schedule)
                .where(Schedule.owner_id == owner_id)
                .order_by(Schedule.next_run_at)
                .limit(limit)
                .offset(offset)
            )
        )

    def list_upcoming(self, owner_id: uuid.UUID, limit: int) -> list[Schedule]:
        return list(
            self.session.scalars(
                select(Schedule)
                .where(Schedule.owner_id == owner_id, Schedule.enabled.is_(True))
                .options(joinedload(Schedule.flow))
                .order_by(Schedule.next_run_at)
                .limit(limit)
            )
        )

    def claim_due(self, now: datetime) -> list[Schedule]:
        return list(
            self.session.scalars(
                select(Schedule)
                .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
            )
        )
