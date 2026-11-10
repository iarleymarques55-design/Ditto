import uuid
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

    def avatar_path(self, user: User) -> str:
        if not user.avatar_id:
            raise NotFoundError("Esta conta não tem foto.")
        return str(storage.path_for_read(_avatar_key(user)))

    def change_password(self, user: User, payload: PasswordChange) -> TokenResponse:
        if user.password_hash and not verify_password(
            payload.current_password or "", user.password_hash
        ):
            raise BusinessRuleError("A senha atual está incorreta.")

        user.password_hash = hash_password(payload.new_password)
        # Quem roubou um token antigo perde o acesso. Esta sessão continua, com um token novo.
        user.tokens_valid_after = datetime.now(UTC)
        self.session.commit()
        return token_for(user)

    def delete(self, user: User, payload: AccountDeletion) -> None:
        if payload.confirmation.strip().lower() != user.email:
            raise BusinessRuleError("O e-mail digitado não é o desta conta.")
        if user.password_hash and not verify_password(payload.password or "", user.password_hash):
            raise BusinessRuleError("A senha está incorreta.")

        owner_id = user.id
        # O banco apaga em cascata tarefas, execuções, acessos e agendas
        self.session.delete(user)
        self.session.commit()
        storage.delete_tree(str(owner_id))
