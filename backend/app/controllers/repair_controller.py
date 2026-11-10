import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.controllers.dependencies import (
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    RULE_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    CurrentUser,
    DbSession,
    Limit,
    Offset,
)
from app.schemas.common import Page
from app.schemas.repair import HelpAnswer, HelpRequestResponse, LayerStat, RepairResponse
from app.services.repair_service import RepairService

router = APIRouter(tags=["Reparos"], responses=UNAUTHORIZED_RESPONSE)


@router.get(
    "/repairs",
    response_model=Page[RepairResponse],
    summary="Listar reparos",
    description="Mostra os caminhos que mudaram, do mais recente para o mais antigo.",
)
def list_repairs(
    user: CurrentUser, session: DbSession, limit: Limit = 20, offset: Offset = 0
) -> Page[RepairResponse]:
    return RepairService(session).list_repairs(user.id, limit, offset)


@router.get(
    "/repairs/stats",
    response_model=list[LayerStat],
    summary="Ver quem resolveu cada passo",
    description="Conta os passos concluídos no período por camada da escada de reparo.",
)
def repair_stats(
    user: CurrentUser,
    session: DbSession,
    days: Annotated[int, Query(ge=1, le=365, description="Tamanho do período, em dias.")] = 30,
) -> list[LayerStat]:
    return RepairService(session).layer_stats(user.id, days)


@router.get(
    "/help-requests",
    response_model=list[HelpRequestResponse],
    summary="Listar pedidos de ajuda abertos",
    description="Mostra as decisões que estão paradas esperando uma pessoa.",
)
def list_help_requests(
    user: CurrentUser,
    session: DbSession,
    run_id: Annotated[uuid.UUID | None, Query(description="Só desta execução.")] = None,
) -> list[HelpRequestResponse]:
    return RepairService(session).list_open_help(user.id, run_id)


@router.post(
    "/help-requests/{help_id}/answer",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Responder a um pedido de ajuda",
    description="Registra a decisão e devolve a execução para a fila quando não há mais nada pendente.",
    responses={**NOT_FOUND_RESPONSE, **RULE_RESPONSE, **CONFLICT_RESPONSE},
)
def answer_help_request(
    help_id: Annotated[uuid.UUID, Path(description="Identificador do pedido.")],
    payload: HelpAnswer,
    user: CurrentUser,
    session: DbSession,
) -> None:
    RepairService(session).answer(help_id, user.id, payload)
