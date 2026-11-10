import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdTimestampMixin, enum_column
from app.models.enums import (
    ArtifactKind,
    EventStatus,
    ItemStatus,
    LogLevel,
    RunStatus,
    RunTrigger,
)
from app.models.flow import Flow


class Run(IdTimestampMixin, Base):
    __tablename__ = "runs"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        enum_column(RunStatus), default=RunStatus.QUEUED, index=True
    )
    trigger: Mapped[RunTrigger] = mapped_column(enum_column(RunTrigger), default=RunTrigger.MANUAL)
    # Fuso de quem disparou: "mês anterior" e "hoje" dependem dele
    timezone: Mapped[str] = mapped_column(String(64), default="America/Fortaleza")
    # Passos sem volta que a pessoa já autorizou nesta execução
    confirmed_step_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    flow: Mapped[Flow] = relationship()
    items: Mapped[list["RunItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunItem.position"
    )
    log_entries: Mapped[list["RunLogEntry"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunLogEntry.created_at"
    )


class RunItem(IdTimestampMixin, Base):
    """Uma linha da planilha: uma "cópia"."""

    __tablename__ = "run_items"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    # O que foi capturado da tela: {chave: texto} ou, em tabelas, {chave: [linhas]}
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[ItemStatus] = mapped_column(
        enum_column(ItemStatus), default=ItemStatus.PENDING, index=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    problem_step_position: Mapped[int | None] = mapped_column(Integer)
    resolved_layer: Mapped[int | None] = mapped_column(Integer)
    # Marcado antes de tocar em um passo sem volta: uma cópia assim nunca é repetida
    irreversible_done: Mapped[bool] = mapped_column(Boolean, default=False)

    run: Mapped[Run] = relationship(back_populates="items")
    events: Mapped[list["StepEvent"]] = relationship(cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(cascade="all, delete-orphan")


class StepEvent(IdTimestampMixin, Base):
    __tablename__ = "step_events"

    run_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("run_items.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("steps.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[EventStatus] = mapped_column(enum_column(EventStatus))
    layer: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class RunLogEntry(IdTimestampMixin, Base):
    __tablename__ = "run_log_entries"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    level: Mapped[LogLevel] = mapped_column(enum_column(LogLevel), default=LogLevel.INFO)
    message: Mapped[str] = mapped_column(Text)

    run: Mapped[Run] = relationship(back_populates="log_entries")


class Artifact(IdTimestampMixin, Base):
    """Só os metadados: o arquivo fica no armazenamento, fora do banco."""

    __tablename__ = "artifacts"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    run_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("run_items.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ArtifactKind] = mapped_column(enum_column(ArtifactKind))
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    storage_key: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
