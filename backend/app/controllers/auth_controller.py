from fastapi import APIRouter, Depends, Request, status

from app.controllers.dependencies import UNAUTHORIZED_RESPONSE, CurrentUser, DbSession
from app.core.rate_limit import client_ip, limit_requests
from app.core.security import create_recording_token, create_runner_token
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    MessageResponse,
    RecordingTokenResponse,
    RegisterRequest,
    ResendCodeRequest,
    RunnerTokenResponse,
    TokenResponse,
    UserResponse,
    VerificationPendingResponse,
    VerifyEmailRequest,
)
from app.schemas.error import ErrorResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Autenticação"])

_RATE_LIMIT_RESPONSE = {
    429: {"model": ErrorResponse, "description": "Muitas tentativas em pouco tempo."}
}


@router.post(
    "/register",
    response_model=VerificationPendingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta",
    description=(
        "Cria a conta e manda um código de 6 dígitos para o e-mail. A conta só entra depois de "
        "confirmar o código em `/auth/verify-email`. Se o e-mail já tem uma conta nunca "
        "confirmada, ela é substituída por esta."
    ),
    responses={
        409: {"model": ErrorResponse, "description": "E-mail já cadastrado e confirmado."},
        503: {"model": ErrorResponse, "description": "O e-mail com o código não pôde ser enviado."},
        **_RATE_LIMIT_RESPONSE,
    },
    dependencies=[Depends(limit_requests(10))],
)
def register(payload: RegisterRequest, session: DbSession) -> VerificationPendingResponse:
    return AuthService(session).register(payload)


@router.post(
    "/verify-email",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirmar o e-mail",
    description=(
        "Confere o código enviado por e-mail e devolve o token de acesso. O código vale 15 "
        "minutos e aceita 5 tentativas; depois disso é preciso pedir outro."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Código incorreto ou vencido."},
        **_RATE_LIMIT_RESPONSE,
    },
    dependencies=[Depends(limit_requests(20))],
)
def verify_email(payload: VerifyEmailRequest, session: DbSession) -> TokenResponse:
    return AuthService(session).verify_email(payload)


@router.post(
    "/resend-code",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reenviar o código",
    description=(
        "Manda um código novo para uma conta ainda não confirmada (no máximo um por minuto e "
        "cinco por hora). A resposta é sempre a mesma, exista a conta ou não."
    ),
    responses=_RATE_LIMIT_RESPONSE,
    dependencies=[Depends(limit_requests(5))],
)
def resend_code(payload: ResendCodeRequest, session: DbSession) -> MessageResponse:
    AuthService(session).resend_code(payload)
    return MessageResponse(
        message="Se este e-mail tem uma conta esperando confirmação, enviamos um código novo."
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Entrar",
    description=(
        "Confere e-mail e senha. A mensagem de erro é a mesma para e-mail inexistente e senha "
        "errada. Com a senha certa e o e-mail ainda não confirmado, manda um código novo e "
        "responde 403 `EMAIL_NOT_VERIFIED`."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "E-mail ou senha incorretos."},
        403: {"model": ErrorResponse, "description": "E-mail ainda não confirmado."},
        **_RATE_LIMIT_RESPONSE,
    },
    dependencies=[Depends(limit_requests(20))],
)
def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    return AuthService(session).login(payload, client_ip(request))


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


@router.post(
    "/recording-token",
    response_model=RecordingTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar o token da extensão",
    description=(
        "Gera um token de curta duração para a extensão enviar uma gravação. "
        "Ele não dá acesso a nenhuma outra rota."
    ),
    responses={**UNAUTHORIZED_RESPONSE, **_RATE_LIMIT_RESPONSE},
    dependencies=[Depends(limit_requests(30))],
)
def create_recording_session(user: CurrentUser) -> RecordingTokenResponse:
    token, expires_at = create_recording_token(user.id, user.tokens_valid_after)
    return RecordingTokenResponse(token=token, expires_at=expires_at)


@router.post(
    "/runner-token",
    response_model=RunnerTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ligar a extensão ao worker",
    description=(
        "Gera o token que a extensão usa para receber tarefas do worker e executá-las no Chrome "
        "da pessoa, com as contas logadas nele. O worker só roda nesse Chrome as execuções de "
        "quem gerou o token. Ele não dá acesso a nenhuma rota da API e deixa de valer quando a "
        "senha é trocada ou quando o executor é desligado."
    ),
    responses={**UNAUTHORIZED_RESPONSE, **_RATE_LIMIT_RESPONSE},
    dependencies=[Depends(limit_requests(10))],
)
def create_runner_session(user: CurrentUser) -> RunnerTokenResponse:
    token, expires_at = create_runner_token(
        user.id, user.email, (user.tokens_valid_after, user.runner_tokens_valid_after)
    )
    return RunnerTokenResponse(token=token, expires_at=expires_at)


@router.delete(
    "/runner-token",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desligar o executor",
    description=(
        "Invalida todos os tokens do executor desta conta. Qualquer Chrome ligado a ela para de "
        "receber tarefas em até 1 minuto. O login no painel continua valendo."
    ),
    responses={**UNAUTHORIZED_RESPONSE, **_RATE_LIMIT_RESPONSE},
    dependencies=[Depends(limit_requests(10))],
)
def revoke_runner_sessions(user: CurrentUser, session: DbSession) -> None:
    AuthService(session).revoke_runner_tokens(user)
