import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.controllers.dependencies import (
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    CurrentUser,
    DbSession,
)
from app.models.credential import Credential
from app.schemas.credential import CredentialCreate, CredentialResponse
from app.services.credential_service import CredentialService

router = APIRouter(prefix="/credentials", tags=["Acessos"], responses=UNAUTHORIZED_RESPONSE)


@router.post(
    "",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Salvar o acesso a um portal",
    description="Guarda usuário e senha cifrados. Salvar de novo o mesmo domínio substitui o acesso anterior.",
)
def save_credential(payload: CredentialCreate, user: CurrentUser, session: DbSession) -> Credential:
    return CredentialService(session).save(user.id, payload)


@router.get(
    "",
    response_model=list[CredentialResponse],
    summary="Listar acessos",
    description="Mostra só os domínios. Usuário e senha nunca saem da API.",
)
def list_credentials(user: CurrentUser, session: DbSession) -> list[Credential]:
    return CredentialService(session).list(user.id)


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Apagar um acesso",
    description="Apaga o acesso. Tarefas que dependem dele deixam de rodar até ele ser salvo de novo.",
    responses=NOT_FOUND_RESPONSE,
)
def delete_credential(
    credential_id: Annotated[uuid.UUID, Path(description="Identificador do acesso.")],
    user: CurrentUser,
    session: DbSession,
) -> None:
    CredentialService(session).delete(credential_id, user.id)
