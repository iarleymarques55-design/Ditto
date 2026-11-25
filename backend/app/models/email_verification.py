import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestampMixin


class EmailVerification(IdTimestampMixin, Base):
    """O código de confirmação de e-mail que está valendo para uma conta. Um por conta."""

    __tablename__ = "email_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    # Só o resumo (HMAC) do código: quem lê o banco não consegue confirmar a conta de ninguém
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Limite de reenvios: quantos e-mails saíram desde o começo da janela atual
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sends_in_window: Mapped[int] = mapped_column(Integer, default=1)
