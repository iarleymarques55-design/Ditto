import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base das tabelas. Importe cada model novo em models/__init__.py para o Alembic vê-lo."""

    # Nomes previsíveis de restrições: sem isso, o Alembic não consegue alterá-las depois
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class IdTimestampMixin:
    """UUID em vez de número sequencial: o id de um recurso não permite adivinhar o de outro."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def enum_column(enum_class: type[StrEnum]) -> Enum:
    """Guarda o valor como texto com CHECK: adicionar um estado novo não exige ALTER TYPE."""
    return Enum(
        enum_class,
        native_enum=False,
        create_constraint=True,
        length=32,
        name=enum_class.__name__.lower(),
        values_callable=lambda items: [item.value for item in items],
    )
