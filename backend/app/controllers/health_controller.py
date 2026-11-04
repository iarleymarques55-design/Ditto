from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.health_repository import HealthRepository
from app.schemas.error import ErrorResponse
from app.schemas.health import DatabaseHealthResponse, HealthResponse
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["Saúde"])


def get_health_service(session: Session = Depends(get_db)) -> HealthService:
    return HealthService(HealthRepository(session))


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Verificar a API",
    description="Responde `ok` se a API está no ar. Não consulta o banco.",
)
def check_api() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/db",
    response_model=DatabaseHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Verificar o banco de dados",
    description="Faz uma consulta simples no PostgreSQL para confirmar a conexão.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "O banco de dados não respondeu.",
        }
    },
)
def check_database(service: HealthService = Depends(get_health_service)) -> DatabaseHealthResponse:
    service.check_database()
    return DatabaseHealthResponse(status="ok", database="connected")
