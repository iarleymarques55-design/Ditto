import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdTimestampMixin, enum_column
from app.models.enums import FlowStatus, StepAction, VariableSource, VariableStatus, VersionSource


class Flow(IdTimestampMixin, Base):
    __tablename__ = "flows"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    start_url: Mapped[str] = mapped_column(Text)
    status: Mapped[FlowStatus] = mapped_column(
        enum_column(FlowStatus), default=FlowStatus.ANALYZING, index=True
    )
    allowed_domains: Mapped[list[str]] = mapped_column(JSONB, default=list)

    steps: Mapped[list["Step"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan", order_by="Step.position"
    )
    variables: Mapped[list["Variable"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan", order_by="Variable.created_at"
    )


class Step(IdTimestampMixin, Base):
    __tablename__ = "steps"
    __table_args__ = (UniqueConstraint("flow_id", "position"),)

    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    action: Mapped[StepAction] = mapped_column(enum_column(StepAction))
    intent: Mapped[str] = mapped_column(String(300), default="")
    postcondition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Texto com {variavel}. Nulo quando o valor vem de uma credencial
    value_template: Mapped[str | None] = mapped_column(Text)
    url_template: Mapped[str | None] = mapped_column(Text)
    # "username" ou "password": o valor nunca fica neste registro, vem cifrado de credentials
    credential_field: Mapped[str | None] = mapped_column(String(16))
    irreversible: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    save_as: Mapped[str | None] = mapped_column(Text)

    flow: Mapped[Flow] = relationship(back_populates="steps")
    versions: Mapped[list["StepVersion"]] = relationship(
        back_populates="step", cascade="all, delete-orphan", order_by="StepVersion.version.desc()"
    )


class StepVersion(IdTimestampMixin, Base):
    """Cada caminho encontrado vira uma versão; as antigas ficam para auditoria e como tentativa."""

    __tablename__ = "step_versions"
    __table_args__ = (UniqueConstraint("step_id", "version"),)

    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("steps.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    target: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source: Mapped[VersionSource] = mapped_column(enum_column(VersionSource))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    step: Mapped[Step] = relationship(back_populates="versions")


class Variable(IdTimestampMixin, Base):
    __tablename__ = "variables"
    __table_args__ = (UniqueConstraint("flow_id", "name"),)

    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("steps.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    example: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[VariableSource] = mapped_column(
        enum_column(VariableSource), default=VariableSource.COLUMN
    )
    status: Mapped[VariableStatus] = mapped_column(
        enum_column(VariableStatus), default=VariableStatus.PENDING
    )

    flow: Mapped[Flow] = relationship(back_populates="variables")
