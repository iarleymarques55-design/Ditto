from typing import Annotated

from fastapi import APIRouter, Query

from app.controllers.dependencies import (
    RULE_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    CurrentUser,
    DbSession,
)
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Mesa"], responses=UNAUTHORIZED_RESPONSE)


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Ver o resumo do dia",
    description="Reúne cópias de hoje, pedidos abertos, execução em destaque, últimas execuções e próxima agenda.",
    responses=RULE_RESPONSE,
)
def get_summary(
    user: CurrentUser,
    session: DbSession,
    timezone: Annotated[
        str, Query(max_length=64, description="Fuso usado para saber o que é hoje.")
    ] = "America/Fortaleza",
) -> DashboardSummary:
    return DashboardService(session).summary(user.id, timezone)
