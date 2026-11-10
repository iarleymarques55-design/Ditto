from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdTimestampMixin


class User(IdTimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Nulo em conta criada só pelo Google
    password_hash: Mapped[str | None] = mapped_column(String(128))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Muda a cada foto nova: serve de nome do arquivo e avisa o painel para buscar de novo
    avatar_id: Mapped[str | None] = mapped_column(String(32))
    email_alerts: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Tokens emitidos antes disto não valem mais: trocar a senha encerra as outras sessões
    tokens_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None
