import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

ALGORITHM = "HS256"
# Comparado quando o e-mail não existe, para o tempo de resposta não revelar quem tem conta
_DUMMY_HASH = bcrypt.hashpw(b"ditto-usuario-inexistente", bcrypt.gensalt())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password.encode()
    if password_hash is None:
        bcrypt.checkpw(candidate, _DUMMY_HASH)
        return False
    return bcrypt.checkpw(candidate, password_hash.encode())


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> tuple[uuid.UUID, int]:
    """Devolve a conta e o instante em que o token foi emitido."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        return uuid.UUID(payload["sub"]), int(payload["iat"])
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise UnauthorizedError from error
