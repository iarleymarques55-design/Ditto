from typing import Annotated

from fastapi import Depends, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.models.user import User
from app.schemas.error import ErrorResponse
from app.services.auth_service import AuthService

MAX_PAGE_SIZE = 100

_bearer = HTTPBearer(auto_error=False, description="Token recebido ao entrar ou criar a conta.")

UNAUTHORIZED_RESPONSE = {
    401: {"model": ErrorResponse, "description": "Token ausente, inválido ou vencido."}
}
NOT_FOUND_RESPONSE = {
    404: {"model": ErrorResponse, "description": "Não existe ou é de outra conta."}
}
RULE_RESPONSE = {
    400: {"model": ErrorResponse, "description": "Uma regra de negócio não permitiu a operação."}
}
CONFLICT_RESPONSE = {
    409: {"model": ErrorResponse, "description": "O estado atual não permite a operação."}
}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise UnauthorizedError
    return AuthService(session).get_user_from_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Tamanho da página (máximo 100).")]
Offset = Annotated[int, Query(ge=0, description="Quantos registros pular.")]
