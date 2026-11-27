import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

ALGORITHM = "HS256"
RECORDING_SCOPE = "recording"
RUNNER_SCOPE = "runner"
# Comparado quando o e-mail não existe, para o tempo de resposta não revelar quem tem conta
# Mesmo custo das senhas de verdade: um custo diferente mudaria o tempo de resposta
_DUMMY_HASH = bcrypt.hashpw(
    b"ditto-usuario-inexistente", bcrypt.gensalt(rounds=settings.bcrypt_rounds)
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password.encode()
    if password_hash is None:
        bcrypt.checkpw(candidate, _DUMMY_HASH)
        return False
    return bcrypt.checkpw(candidate, password_hash.encode())


def _issued_at_ms(now: datetime) -> int:
    return int(now.timestamp() * 1000)


_ONE_MS = timedelta(milliseconds=1)


def _issue_moment(*revoked_at: datetime | None) -> datetime:
    """Agora, mas sempre num milissegundo depois da última revogação da conta. Um token do mesmo
    milissegundo da revogação não vale (veja issued_before): sem esta folga, o token novo dado
    logo depois de trocar a senha cairia junto com os antigos."""
    now = datetime.now(UTC)
    for moment in revoked_at:
        if moment is not None and _issued_at_ms(now) <= _issued_at_ms(moment):
            now = moment + _ONE_MS
    return now


def create_access_token(user_id: uuid.UUID, revoked_at: datetime | None = None) -> str:
    now = _issue_moment(revoked_at)
    payload = {
        "sub": str(user_id),
        "iat": now,
        # O "iat" do JWT só guarda segundos: um token emitido no mesmo segundo em que a senha
        # foi trocada escaparia da revogação. Os milissegundos tiram essa folga
        "iat_ms": _issued_at_ms(now),
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def _create_scoped_token(
    user_id: uuid.UUID,
    scope: str,
    lifetime: timedelta,
    extra: dict | None = None,
    revoked_at: tuple[datetime | None, ...] = (),
) -> tuple[str, datetime]:
    now = _issue_moment(*revoked_at)
    expires_at = now + lifetime
    payload = {
        "sub": str(user_id),
        "iat": now,
        "iat_ms": _issued_at_ms(now),
        "exp": expires_at,
        "scope": scope,
        **(extra or {}),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return token, expires_at


def create_recording_token(
    user_id: uuid.UUID, revoked_at: datetime | None = None
) -> tuple[str, datetime]:
    """Token da extensão: dura pouco e só serve para enviar gravações, nunca para ler a conta."""
    return _create_scoped_token(
        user_id,
        RECORDING_SCOPE,
        timedelta(minutes=settings.recording_token_minutes),
        revoked_at=(revoked_at,),
    )


def create_runner_token(
    user_id: uuid.UUID, email: str, revoked_at: tuple[datetime | None, ...] = ()
) -> tuple[str, datetime]:
    """Token que liga a extensão ao worker, para as tarefas rodarem no Chrome da pessoa.
    Não vale em nenhuma rota da API.

    Leva o e-mail da conta: a extensão mostra esse e-mail antes de a pessoa aceitar a ligação.
    Como o token é assinado, uma página que trocasse o e-mail teria o token recusado pelo relé.
    """
    return _create_scoped_token(
        user_id,
        RUNNER_SCOPE,
        timedelta(days=settings.runner_token_days),
        {"email": email},
        revoked_at=revoked_at,
    )


def decode_access_token(token: str) -> tuple[uuid.UUID, int, str | None]:
    """Devolve a conta, o instante de emissão (em milissegundos) e o escopo, se houver."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        # Tokens antigos, sem "iat_ms", contam como emitidos no começo do segundo
        issued_at_ms = payload.get("iat_ms")
        if not isinstance(issued_at_ms, int):
            issued_at_ms = int(payload["iat"]) * 1000
        return (uuid.UUID(payload["sub"]), issued_at_ms, payload.get("scope"))
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise UnauthorizedError from error


def issued_before(issued_at_ms: int, moment: datetime | None) -> bool:
    """O token saiu antes de `moment` (ou no mesmo milissegundo) e por isso deixou de valer?"""
    return moment is not None and issued_at_ms <= _issued_at_ms(moment)
