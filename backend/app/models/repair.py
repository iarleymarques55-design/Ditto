import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdTimestampMixin, enum_column
from app.models.enums import HelpKind, HelpStatus
from app.models.flow import Step, StepVersion
from app.models.run import Run, RunItem


class Repair(IdTimestampMixin, Base):
    __tablename__ = "repairs"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("steps.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    layer: Mapped[int] = mapped_column(Integer)
    old_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("step_versions.id", ondelete="SET NULL")
    )
    new_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("step_versions.id", ondelete="SET NULL")
    )
    score: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text, default="")

    step: Mapped[Step] = relationship()
    old_version: Mapped[StepVersion | None] = relationship(foreign_keys=[old_version_id])
    new_version: Mapped[StepVersion | None] = relationship(foreign_keys=[new_version_id])


class HelpRequest(IdTimestampMixin, Base):
    __tablename__ = "help_requests"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    run_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run_items.id", ondelete="CASCADE"))
    step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("steps.id", ondelete="CASCADE"))
    kind: Mapped[HelpKind] = mapped_column(enum_column(HelpKind))
    status: Mapped[HelpStatus] = mapped_column(
        enum_column(HelpStatus), default=HelpStatus.OPEN, index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    # Em "choose": elementos candidatos, com id, texto, nota e impressão digital
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    answer: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[Run] = relationship()
    item: Mapped[RunItem] = relationship()
    step: Mapped[Step | None] = relationship()
