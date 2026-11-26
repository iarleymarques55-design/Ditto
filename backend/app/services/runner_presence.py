"""Se há um Chrome ligado a uma conta, para o painel avisar quando um pedido não vai andar.

O worker (outro processo) marca no banco quando vê a extensão: na conexão e a cada conferência
do token, de minuto em minuto. Com a extensão ligada a outra conta, ou desligada, a fila dessa
conta não anda, e antes o painel mostrava só "Na fila" para sempre.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.repositories.user_repository import UserRepository

# O worker confere o token a cada 60 s: duas conferências perdidas contam como desligado
SEEN_WINDOW = timedelta(seconds=150)


def mark_seen(user: User) -> None:
    user.runner_seen_at = datetime.now(UTC)


def mark_gone(user: User) -> None:
    user.runner_seen_at = None


def runner_connected(session: Session, owner_id: uuid.UUID) -> bool | None:
    """None quando as tarefas não rodam pela extensão: aí o worker usa o próprio navegador."""
    if not settings.extension_runner_port:
        return None
    user = UserRepository(session).get_by_id(owner_id)
    seen = user.runner_seen_at if user is not None else None
    return seen is not None and datetime.now(UTC) - seen <= SEEN_WINDOW
