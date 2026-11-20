import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.ai_draft import AiDraft
from app.models.enums import AiDraftStatus

OPEN_STATUSES = (AiDraftStatus.QUEUED, AiDraftStatus.RUNNING, AiDraftStatus.WAITING_ANSWER)


class AiDraftRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, draft: AiDraft) -> AiDraft:
        self.session.add(draft)
        self.session.flush()
        return draft

    def get_owned(self, draft_id: uuid.UUID, owner_id: uuid.UUID) -> AiDraft | None:
        return self.session.scalar(
            select(AiDraft).where(AiDraft.id == draft_id, AiDraft.owner_id == owner_id)
        )

    def list_owned(self, owner_id: uuid.UUID, limit: int) -> list[AiDraft]:
        return list(
            self.session.scalars(
                select(AiDraft)
                .where(AiDraft.owner_id == owner_id)
                .order_by(AiDraft.created_at.desc())
                .limit(limit)
            )
        )

    def has_open(self, owner_id: uuid.UUID) -> bool:
        return (
            self.session.scalar(
                select(AiDraft.id)
                .where(AiDraft.owner_id == owner_id, AiDraft.status.in_(OPEN_STATUSES))
                .limit(1)
            )
            is not None
        )

    def claim_queued(self, owner_id: uuid.UUID) -> AiDraft | None:
        """Só da conta ligada ao Chrome: a IA nunca navega no navegador de outra pessoa."""
        return self.session.scalar(
            select(AiDraft)
            .where(AiDraft.owner_id == owner_id, AiDraft.status == AiDraftStatus.QUEUED)
            .order_by(AiDraft.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    def fail_stale(self, limit: datetime, message: str) -> int:
        result = self.session.execute(
            update(AiDraft)
            .where(
                AiDraft.status.in_((AiDraftStatus.RUNNING, AiDraftStatus.WAITING_ANSWER)),
                AiDraft.heartbeat_at < limit,
            )
            .values(status=AiDraftStatus.FAILED, error=message, question=None)
        )
        return result.rowcount or 0

    def update_if_open(self, draft_id: uuid.UUID, values: dict) -> bool:
        """Muda o rascunho só se ele ainda está aberto: um cancelamento no painel vence o worker."""
        result = self.session.execute(
            update(AiDraft)
            .where(AiDraft.id == draft_id, AiDraft.status.in_(OPEN_STATUSES))
            .values(**values)
        )
        return bool(result.rowcount)
