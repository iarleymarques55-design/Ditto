import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Path, UploadFile, status

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
from app.controllers.run_controller import read_upload
from app.schemas.schedule import ScheduleResponse, ScheduleUpdate
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedules", tags=["Agendas"], responses=UNAUTHORIZED_RESPONSE)

ScheduleId = Annotated[uuid.UUID, Path(description="Identificador da agenda.")]


@router.post(
    "",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agendar uma tarefa",
    description="Cada tarefa tem uma agenda. A planilha enviada aqui é repetida em todos os disparos.",
    responses={**NOT_FOUND_RESPONSE, **RULE_RESPONSE, **CONFLICT_RESPONSE},
)
def create_schedule(
    user: CurrentUser,
    session: DbSession,
    flow_id: Annotated[uuid.UUID, Form(description="Tarefa a agendar.")],
    cron: Annotated[
        str, Form(max_length=64, description="Horário em formato cron, como `10 7 5 * *`.")
    ],
    timezone: Annotated[
        str, Form(max_length=64, description="Fuso do horário.")
    ] = "America/Fortaleza",
    file: Annotated[
        UploadFile | None, File(description="Planilha com uma linha por cópia.")
    ] = None,
) -> ScheduleResponse:
    file_name, content = read_upload(file)
    return ScheduleService(session).create(user.id, flow_id, cron, timezone, file_name, content)


@router.get(
    "",
    response_model=list[ScheduleResponse],
    summary="Listar agendas",
    description="Lista as agendas da conta, da próxima a disparar para a última.",
)
def list_schedules(
    user: CurrentUser, session: DbSession, limit: Limit = 20, offset: Offset = 0
) -> list[ScheduleResponse]:
    return ScheduleService(session).list(user.id, limit, offset)


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Editar uma agenda",
    description="Pausa, retoma ou muda o horário. Horários perdidos durante uma pausa não disparam depois.",
    responses={**NOT_FOUND_RESPONSE, **RULE_RESPONSE},
)
def update_schedule(
    schedule_id: ScheduleId, payload: ScheduleUpdate, user: CurrentUser, session: DbSession
) -> ScheduleResponse:
    return ScheduleService(session).update(schedule_id, user.id, payload)


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Apagar uma agenda",
    description="A tarefa continua existindo e pode rodar à mão.",
    responses=NOT_FOUND_RESPONSE,
)
def delete_schedule(schedule_id: ScheduleId, user: CurrentUser, session: DbSession) -> None:
    ScheduleService(session).delete(schedule_id, user.id)
