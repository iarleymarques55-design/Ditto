import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.controllers.dependencies import (
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    RULE_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    CurrentUser,
    DbSession,
)
from app.schemas.ai_draft import AiDraftAnswer, AiDraftCreate, AiDraftResponse
from app.schemas.error import ErrorResponse
from app.services.ai_draft_service import AiDraftService

router = APIRouter(prefix="/ai-drafts", tags=["Criar com IA"], responses=UNAUTHORIZED_RESPONSE)

DraftId = Annotated[uuid.UUID, Path(description="Identificador do pedido.")]


@router.post(
    "",
    response_model=AiDraftResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pedir para a IA criar uma tarefa",
    description=(
        "Coloca o pedido na fila. O worker abre uma aba no Chrome ligado à conta e a IA monta "
        "a tarefa passo a passo. Quando termina, a tarefa aparece para revisão."
    ),
    responses={
        **RULE_RESPONSE,
        **CONFLICT_RESPONSE,
        503: {"model": ErrorResponse, "description": "A IA não está configurada no servidor."},
    },
)
def create_draft(payload: AiDraftCreate, user: CurrentUser, session: DbSession) -> AiDraftResponse:
    return AiDraftService(session).create(user.id, payload)


@router.get(
    "",
    response_model=list[AiDraftResponse],
    summary="Listar pedidos recentes",
    description="Os 20 pedidos mais novos da conta, do mais novo para o mais antigo.",
)
def list_drafts(user: CurrentUser, session: DbSession) -> list[AiDraftResponse]:
    return AiDraftService(session).list(user.id)


@router.get(
    "/{draft_id}",
    response_model=AiDraftResponse,
    summary="Acompanhar um pedido",
    description="Mostra o que a IA já fez, a dúvida aberta e, no fim, a tarefa criada.",
    responses=NOT_FOUND_RESPONSE,
)
def get_draft(draft_id: DraftId, user: CurrentUser, session: DbSession) -> AiDraftResponse:
    return AiDraftService(session).get(draft_id, user.id)


@router.post(
    "/{draft_id}/answer",
    response_model=AiDraftResponse,
    summary="Responder uma dúvida da IA",
    description="A IA continua de onde parou assim que recebe a resposta.",
    responses={**NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def answer_draft(
    draft_id: DraftId, payload: AiDraftAnswer, user: CurrentUser, session: DbSession
) -> AiDraftResponse:
    return AiDraftService(session).answer(draft_id, user.id, payload)


@router.post(
    "/{draft_id}/cancel",
    response_model=AiDraftResponse,
    summary="Cancelar um pedido",
    description="A IA para no próximo passo e fecha a aba que abriu. Nada vira tarefa.",
    responses={**NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def cancel_draft(draft_id: DraftId, user: CurrentUser, session: DbSession) -> AiDraftResponse:
    return AiDraftService(session).cancel(draft_id, user.id)
