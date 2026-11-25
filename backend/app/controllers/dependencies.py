from typing import Annotated, Any

from fastapi import Depends, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import RECORDING_SCOPE, decode_access_token
from app.models.user import User
from app.schemas.error import ErrorResponse
from app.services.auth_service import AuthService

MAX_PAGE_SIZE = 100

_bearer = HTTPBearer(auto_error=False, description="Token recebido ao entrar ou criar a conta.")

# O mesmo tipo que o FastAPI espera em "responses": sem ele, o verificador de tipos reclama
ResponsesDoc = dict[int | str, dict[str, Any]]

UNAUTHORIZED_RESPONSE: ResponsesDoc = {
    401: {"model": ErrorResponse, "description": "Token ausente, inválido ou vencido."}
}
NOT_FOUND_RESPONSE: ResponsesDoc = {
    404: {"model": ErrorResponse, "description": "Não existe ou é de outra conta."}
}
RULE_RESPONSE: ResponsesDoc = {
    400: {"model": ErrorResponse, "description": "Uma regra de negócio não permitiu a operação."}
}
CONFLICT_RESPONSE: ResponsesDoc = {
    409: {"model": ErrorResponse, "description": "O estado atual não permite a operação."}
}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise UnauthorizedError
    return AuthService(session).get_user_from_token(credentials.credentials)


def get_recording_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    """Aceita também o token da extensão, que não vale em nenhuma outra rota."""
    if credentials is None:
        raise UnauthorizedError
    return AuthService(session).get_user_from_token(
        credentials.credentials, allowed_scope=RECORDING_SCOPE
    )


def get_token_issued_at(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> int:
    """Quando o token desta sessão foi emitido (ms). Serve para pedir um login recente."""
    if credentials is None:
        raise UnauthorizedError
    _, issued_at_ms, _ = decode_access_token(credentials.credentials)
    return issued_at_ms


CurrentUser = Annotated[User, Depends(get_current_user)]
TokenIssuedAt = Annotated[int, Depends(get_token_issued_at)]
RecordingUser = Annotated[User, Depends(get_recording_user)]
DbSession = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Tamanho da página (máximo 100).")]
Offset = Annotated[int, Query(ge=0, description="Quantos registros pular.")]
