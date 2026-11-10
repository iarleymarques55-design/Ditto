import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestampMixin


class Credential(IdTimestampMixin, Base):
    __tablename__ = "credentials"
    __table_args__ = (UniqueConstraint("owner_id", "domain"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(255))
    # Fernet: usuário e senha só são lidos em memória pelo worker, na hora de preencher
    encrypted_payload: Mapped[str] = mapped_column(Text)
