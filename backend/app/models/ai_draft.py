import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestampMixin, enum_column
from app.models.enums import AiDraftStatus


class AiDraft(IdTimestampMixin, Base):
    """Uma tarefa que a IA está montando a partir de um pedido escrito. No fim, vira uma
    gravação comum e segue para a revisão como se a pessoa tivesse gravado."""

    __tablename__ = "ai_drafts"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    prompt: Mapped[str] = mapped_column(Text)
    start_url: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[AiDraftStatus] = mapped_column(
        enum_column(AiDraftStatus), default=AiDraftStatus.QUEUED, index=True
    )
    # Passos no formato da gravação da extensão (RecordedStep)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # O que a IA já fez, em frases curtas, para o painel acompanhar
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    allowed_hosts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # {"text": ..., "options": [...]} enquanto espera a pessoa responder
    question: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    answer: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("flows.id", ondelete="SET NULL"), index=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
