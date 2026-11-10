import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import HelpStatus
from app.models.flow import Step
from app.models.repair import HelpRequest, Repair
from app.models.run import Run


class RepairRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: Repair | HelpRequest) -> None:
        self.session.add(entity)

    def list_repairs(
        self, owner_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Repair], int]:
        total = (
            self.session.scalar(
                select(func.count()).select_from(Repair).where(Repair.owner_id == owner_id)
            )
            or 0
        )
        repairs = self.session.scalars(
            select(Repair)
            .where(Repair.owner_id == owner_id)
            .options(
                joinedload(Repair.step).joinedload(Step.flow),
                joinedload(Repair.old_version),
                joinedload(Repair.new_version),
            )
            .order_by(Repair.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(repairs), total

    def list_open_help(
        self, owner_id: uuid.UUID, run_id: uuid.UUID | None = None
    ) -> list[HelpRequest]:
        conditions = [HelpRequest.owner_id == owner_id, HelpRequest.status == HelpStatus.OPEN]
        if run_id:
            conditions.append(HelpRequest.run_id == run_id)
        return list(
            self.session.scalars(
                select(HelpRequest)
                .where(*conditions)
                .options(
                    joinedload(HelpRequest.run).joinedload(Run.flow), joinedload(HelpRequest.item)
                )
                .order_by(HelpRequest.created_at.desc())
            )
        )

    def get_help_for_update(self, help_id: uuid.UUID, owner_id: uuid.UUID) -> HelpRequest | None:
        """Trava o pedido: duas respostas ao mesmo tempo não podem valer as duas."""
        return self.session.scalar(
            select(HelpRequest)
            .where(HelpRequest.id == help_id, HelpRequest.owner_id == owner_id)
            .with_for_update(of=HelpRequest)
        )

    def has_open_help(self, run_id: uuid.UUID) -> bool:
        return bool(
            self.session.scalar(
                select(func.count())
                .select_from(HelpRequest)
                .where(HelpRequest.run_id == run_id, HelpRequest.status == HelpStatus.OPEN)
            )
        )

    def list_open_for_run(self, run_id: uuid.UUID) -> list[HelpRequest]:
        return list(
            self.session.scalars(
                select(HelpRequest).where(
                    HelpRequest.run_id == run_id, HelpRequest.status == HelpStatus.OPEN
                )
            )
        )

    def claim_expired_help(self, now: datetime) -> list[HelpRequest]:
        return list(
            self.session.scalars(
                select(HelpRequest)
                .where(HelpRequest.status == HelpStatus.OPEN, HelpRequest.expires_at <= now)
                .with_for_update(skip_locked=True)
            )
        )
