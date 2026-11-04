from fastapi import APIRouter, Depends, status

from app.controllers.dependencies import UNAUTHORIZED_RESPONSE, CurrentUser, DbSession
from app.core.rate_limit import limit_requests
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.error import ErrorResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Autenticação"])

_RATE_LIMIT_RESPONSE = {
    429: {"model": ErrorResponse, "description": "Muitas tentativas em pouco tempo."}
}


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta",
    description="Cria a conta e já devolve o token de acesso. O e-mail precisa ser único.",
    responses={
        409: {"model": ErrorResponse, "description": "E-mail já cadastrado."},
        **_RATE_LIMIT_RESPONSE,
    },
    dependencies=[Depends(limit_requests(10))],
)
def register(payload: RegisterRequest, session: DbSession) -> TokenResponse:
    return AuthService(session).register(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Entrar",
    description="Confere e-mail e senha. A mensagem de erro é a mesma para e-mail inexistente e senha errada.",
    responses={
        401: {"model": ErrorResponse, "description": "E-mail ou senha incorretos."},
        **_RATE_LIMIT_RESPONSE,
    },
    dependencies=[Depends(limit_requests(20))],
)
def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    return AuthService(session).login(payload)


@router.post(
    "/google",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Entrar com Google",
    description="Valida o token emitido pelo Google. Cria a conta na primeira vez.",
    responses={
        401: {"model": ErrorResponse, "description": "Token do Google recusado."},
        503: {"model": ErrorResponse, "description": "Login com Google não configurado."},
        **_RATE_LIMIT_RESPONSE,
    },
    dependencies=[Depends(limit_requests(20))],
)
def login_with_google(payload: GoogleLoginRequest, session: DbSession) -> TokenResponse:
    return AuthService(session).login_with_google(payload)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Ver a conta logada",
    description="Devolve os dados de quem está usando o token.",
    responses=UNAUTHORIZED_RESPONSE,
)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
