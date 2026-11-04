from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, UploadFile, status
from fastapi.responses import FileResponse

from app.controllers.dependencies import (
    NOT_FOUND_RESPONSE,
    RULE_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    CurrentUser,
    DbSession,
)
from app.core.exceptions import PayloadTooLargeError
from app.core.rate_limit import limit_requests
from app.schemas.account import AccountDeletion, AccountUpdate, PasswordChange
from app.schemas.auth import TokenResponse, UserResponse
from app.schemas.error import ErrorResponse
from app.services.account_service import AccountService
from app.services.avatar import MAX_AVATAR_BYTES

router = APIRouter(prefix="/account", tags=["Conta"], responses=UNAUTHORIZED_RESPONSE)

_RATE_LIMIT_RESPONSE = {429: {"model": ErrorResponse, "description": "Muitas tentativas."}}


@router.patch(
    "",
    response_model=UserResponse,
    summary="Editar a conta",
    description="Muda o nome e a preferência de alertas por e-mail. O e-mail de acesso não muda por aqui.",
    responses=RULE_RESPONSE,
)
def update_account(payload: AccountUpdate, user: CurrentUser, session: DbSession) -> UserResponse:
    return AccountService(session).update(user, payload)


@router.put(
    "/avatar",
    response_model=UserResponse,
    summary="Trocar a foto de perfil",
    description="Aceita PNG, JPG ou WebP de até 3 MB. A foto é regravada em 256x256, sem metadados.",
    responses={
        **RULE_RESPONSE,
        413: {"model": ErrorResponse, "description": "Foto acima do limite."},
        **_RATE_LIMIT_RESPONSE,
    },
    dependencies=[Depends(limit_requests(20))],
)
def upload_avatar(
    user: CurrentUser,
    session: DbSession,
    file: Annotated[UploadFile, File(description="A imagem da foto de perfil.")],
) -> UserResponse:
    # Lê no máximo um byte além do limite: arquivo grande não chega à memória inteiro
    content = file.file.read(MAX_AVATAR_BYTES + 1)
    if len(content) > MAX_AVATAR_BYTES:
        raise PayloadTooLargeError("A foto passa de 3 MB. Escolha uma imagem menor.")
    return AccountService(session).save_avatar(user, content)


@router.get(
    "/avatar",
    response_class=FileResponse,
    summary="Ver a foto de perfil",
    description="Devolve a foto da conta logada.",
    responses={
        **NOT_FOUND_RESPONSE,
        200: {"content": {"image/webp": {}}, "description": "A foto."},
    },
)
def get_avatar(user: CurrentUser, session: DbSession) -> FileResponse:
    return FileResponse(AccountService(session).avatar_path(user), media_type="image/webp")


@router.delete(
    "/avatar",
    response_model=UserResponse,
    summary="Remover a foto de perfil",
    description="Apaga a foto. O painel volta a mostrar as iniciais do nome.",
)
def delete_avatar(user: CurrentUser, session: DbSession) -> UserResponse:
    return AccountService(session).remove_avatar(user)


@router.post(
    "/password",
    response_model=TokenResponse,
    summary="Trocar a senha",
    description=(
        "Troca a senha e encerra as outras sessões. Devolve um token novo para esta sessão continuar. "
        "Em conta criada pelo Google, define a primeira senha."
    ),
    responses={**RULE_RESPONSE, **_RATE_LIMIT_RESPONSE},
    dependencies=[Depends(limit_requests(10))],
)
def change_password(
    payload: PasswordChange, user: CurrentUser, session: DbSession
) -> TokenResponse:
    return AccountService(session).change_password(user, payload)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir a conta",
    description=(
        "Apaga a conta e tudo o que é dela: tarefas, execuções, acessos, agendas e arquivos. "
        "Não tem volta. Pede o e-mail da conta e, se houver, a senha."
    ),
    responses={**RULE_RESPONSE, **_RATE_LIMIT_RESPONSE},
    dependencies=[Depends(limit_requests(10))],
)
def delete_account(
    payload: Annotated[AccountDeletion, Body()], user: CurrentUser, session: DbSession
) -> None:
    AccountService(session).delete(user, payload)
