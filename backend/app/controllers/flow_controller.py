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
    Limit,
    Offset,
    RecordingUser,
)
from app.schemas.common import Page
from app.schemas.flow import (
    FlowDetail,
    FlowSummary,
    FlowUpdate,
    RecordingCreate,
    StepUpdate,
    VariableAnswer,
)
from app.services.flow_service import FlowService

router = APIRouter(prefix="/flows", tags=["Tarefas"], responses=UNAUTHORIZED_RESPONSE)

FlowId = Annotated[uuid.UUID, Path(description="Identificador da tarefa.")]


@router.post(
    "",
    response_model=FlowDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Receber uma gravação",
    description=(
        "Guarda a gravação e coloca na fila de análise. Campos de senha têm o valor descartado, "
        "mesmo que a extensão tenha enviado."
    ),
)
def create_flow(payload: RecordingCreate, user: RecordingUser, session: DbSession) -> FlowDetail:
    return FlowService(session).create_from_recording(user.id, payload)


@router.get(
    "",
    response_model=Page[FlowSummary],
    summary="Listar tarefas",
    description="Lista as tarefas da conta, da mais nova para a mais antiga. Tarefas arquivadas não aparecem.",
)
def list_flows(
    user: CurrentUser, session: DbSession, limit: Limit = 20, offset: Offset = 0
) -> Page[FlowSummary]:
    return FlowService(session).list(user.id, limit, offset)


@router.get(
    "/{flow_id}",
    response_model=FlowDetail,
    summary="Ver uma tarefa",
    description="Devolve a tarefa com passos, variáveis e agenda.",
    responses=NOT_FOUND_RESPONSE,
)
def get_flow(flow_id: FlowId, user: CurrentUser, session: DbSession) -> FlowDetail:
    return FlowService(session).get(flow_id, user.id)


@router.patch(
    "/{flow_id}",
    response_model=FlowDetail,
    summary="Editar uma tarefa",
    description="Muda o nome ou os domínios em que a tarefa pode navegar.",
    responses=NOT_FOUND_RESPONSE,
)
def update_flow(
    flow_id: FlowId, payload: FlowUpdate, user: CurrentUser, session: DbSession
) -> FlowDetail:
    return FlowService(session).update(flow_id, user.id, payload)


@router.delete(
    "/{flow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Arquivar uma tarefa",
    description="Tira a tarefa da lista e pausa a agenda. O histórico de execuções continua guardado.",
    responses=NOT_FOUND_RESPONSE,
)
def archive_flow(flow_id: FlowId, user: CurrentUser, session: DbSession) -> None:
    FlowService(session).archive(flow_id, user.id)


@router.patch(
    "/{flow_id}/steps/{step_id}",
    response_model=FlowDetail,
    summary="Editar um passo",
    description="Ajusta a intenção, se o passo tem volta, a confirmação automática e onde salvar o arquivo.",
    responses={**NOT_FOUND_RESPONSE, **RULE_RESPONSE},
)
def update_step(
    flow_id: FlowId,
    step_id: Annotated[uuid.UUID, Path(description="Identificador do passo.")],
    payload: StepUpdate,
    user: CurrentUser,
    session: DbSession,
) -> FlowDetail:
    return FlowService(session).update_step(flow_id, step_id, user.id, payload)


@router.post(
    "/{flow_id}/variables/{variable_id}/answer",
    response_model=FlowDetail,
    summary="Responder se um valor muda",
    description='Responde à pergunta "este valor muda a cada vez?". Se não mudar, ele fica fixo no passo.',
    responses=NOT_FOUND_RESPONSE,
)
def answer_variable(
    flow_id: FlowId,
    variable_id: Annotated[uuid.UUID, Path(description="Identificador da variável.")],
    payload: VariableAnswer,
    user: CurrentUser,
    session: DbSession,
) -> FlowDetail:
    return FlowService(session).answer_variable(flow_id, variable_id, user.id, payload)


@router.post(
    "/{flow_id}/confirm",
    response_model=FlowDetail,
    summary="Ativar uma tarefa",
    description="Libera a tarefa para rodar. Todas as perguntas precisam estar respondidas.",
    responses={**NOT_FOUND_RESPONSE, **RULE_RESPONSE, **CONFLICT_RESPONSE},
)
def confirm_flow(flow_id: FlowId, user: CurrentUser, session: DbSession) -> FlowDetail:
    return FlowService(session).confirm(flow_id, user.id)
