import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdTimestampMixin
from app.models.flow import Flow


class Schedule(IdTimestampMixin, Base):
    __tablename__ = "schedules"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), unique=True
    )
    cron: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Fortaleza")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # A planilha enviada ao criar a agenda: cada disparo repete estas linhas
    rows: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)

    flow: Mapped[Flow] = relationship()
