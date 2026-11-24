import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.account import AccountDeletion, AccountUpdate, PasswordChange
from app.schemas.auth import TokenResponse, UserResponse
from app.services import storage
from app.services.auth_service import token_for
from app.services.avatar import process_avatar

# Sem senha para conferir (conta do Google), só um login recente prova que é a própria pessoa,
# e não alguém com um token roubado
_RECENT_LOGIN_MS = 10 * 60 * 1000
_RECENT_LOGIN_MESSAGE = (
    "Por segurança, saia e entre de novo com o Google e faça isso nos próximos 10 minutos."
)


def _require_recent_login(issued_at_ms: int | None) -> None:
    if issued_at_ms is None or time.time() * 1000 - issued_at_ms > _RECENT_LOGIN_MS:
        raise BusinessRuleError(_RECENT_LOGIN_MESSAGE)


def _avatar_key(user: User) -> str:
    return f"{user.id}/foto-{user.avatar_id}.webp"


class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def update(self, user: User, payload: AccountUpdate) -> UserResponse:
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                raise BusinessRuleError("Escreva um nome.")
            user.name = name
        if payload.email_alerts is not None:
            user.email_alerts = payload.email_alerts
        self.session.commit()
        return UserResponse.model_validate(user)

    def save_avatar(self, user: User, content: bytes) -> UserResponse:
        processed = process_avatar(content)
        old_key = _avatar_key(user) if user.avatar_id else None

        user.avatar_id = uuid.uuid4().hex
        storage.save_bytes(_avatar_key(user), processed)
        self.session.commit()

        if old_key:
            storage.delete(old_key)
        return UserResponse.model_validate(user)

    def remove_avatar(self, user: User) -> UserResponse:
        if user.avatar_id:
            storage.delete(_avatar_key(user))
            user.avatar_id = None
            self.session.commit()
        return UserResponse.model_validate(user)

    def avatar_content(self, user: User) -> Iterator[bytes]:
        if not user.avatar_id:
            raise NotFoundError("Esta conta não tem foto.")
        return storage.open_for_read(_avatar_key(user))

    def change_password(
        self, user: User, payload: PasswordChange, issued_at_ms: int | None = None
    ) -> TokenResponse:
        if user.password_hash:
            if not verify_password(payload.current_password or "", user.password_hash):
                raise BusinessRuleError("A senha atual está incorreta.")
        else:
            _require_recent_login(issued_at_ms)

        user.password_hash = hash_password(payload.new_password)
        # Quem roubou um token antigo perde o acesso. Esta sessão continua, com um token novo.
        user.tokens_valid_after = datetime.now(UTC)
        self.session.commit()
        return token_for(user)

    def delete(self, user: User, payload: AccountDeletion, issued_at_ms: int | None = None) -> None:
        if payload.confirmation.strip().lower() != user.email:
            raise BusinessRuleError("O e-mail digitado não é o desta conta.")
        if user.password_hash:
            if not verify_password(payload.password or "", user.password_hash):
                raise BusinessRuleError("A senha está incorreta.")
        else:
            _require_recent_login(issued_at_ms)

        owner_id = user.id
        # O banco apaga em cascata tarefas, execuções, acessos e agendas
        self.session.delete(user)
        self.session.commit()
        storage.delete_tree(str(owner_id))
