import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

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
from app.core.config import settings
from app.core.exceptions import PayloadTooLargeError
from app.core.rate_limit import limit_requests
from app.models.enums import RunStatus
from app.schemas.common import Page
from app.schemas.error import ErrorResponse
from app.schemas.run import RunDetail, RunSummary
from app.services.run_service import RunService

router = APIRouter(tags=["Execuções"], responses=UNAUTHORIZED_RESPONSE)

RunId = Annotated[uuid.UUID, Path(description="Identificador da execução.")]


def read_upload(file: UploadFile | None) -> tuple[str | None, bytes | None]:
    """Lê no máximo um byte além do limite: arquivo grande não chega à memória inteiro."""
    if file is None:
        return None, None
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLargeError("A planilha passa de 5 MB. Divida em partes menores.")
    return file.filename, content


def _attachment(file_name: str, content: bytes, media_type: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{file_name}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@router.post(
    "/runs",
    response_model=RunDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Disparar uma execução",
    description=(
        "Lê a planilha (.csv ou .xlsx), confere as colunas e coloca na fila. A execução acontece no worker: "
        "esta rota responde na hora."
    ),
    responses={
        **NOT_FOUND_RESPONSE,
        **RULE_RESPONSE,
        413: {"model": ErrorResponse, "description": "Planilha acima do limite."},
        429: {"model": ErrorResponse, "description": "Muitas execuções em pouco tempo."},
    },
    dependencies=[Depends(limit_requests(30))],
)
def create_run(
    user: CurrentUser,
    session: DbSession,
    flow_id: Annotated[uuid.UUID, Form(description="Tarefa a executar.")],
    timezone: Annotated[
        str, Form(max_length=64, description="Fuso de quem disparou.")
    ] = "America/Fortaleza",
    file: Annotated[
        UploadFile | None, File(description="Planilha com uma linha por cópia.")
    ] = None,
) -> RunDetail:
    file_name, content = read_upload(file)
    return RunService(session).create(user.id, flow_id, timezone, file_name, content)


@router.get(
    "/runs",
    response_model=Page[RunSummary],
    summary="Listar execuções",
    description="Lista as execuções da conta, da mais recente para a mais antiga.",
)
def list_runs(
    user: CurrentUser,
    session: DbSession,
    limit: Limit = 20,
    offset: Offset = 0,
    flow_id: Annotated[uuid.UUID | None, Query(description="Só desta tarefa.")] = None,
    status_in: Annotated[
        list[RunStatus] | None, Query(alias="status", description="Só nestas situações.")
    ] = None,
) -> Page[RunSummary]:
    return RunService(session).list(user.id, limit, offset, flow_id, status_in)


@router.get(
    "/runs/{run_id}",
    response_model=RunDetail,
    summary="Ver uma execução",
    description="Devolve o progresso, o resultado de cada linha e o registro. O painel consulta esta rota periodicamente.",
    responses=NOT_FOUND_RESPONSE,
)
def get_run(run_id: RunId, user: CurrentUser, session: DbSession) -> RunDetail:
    return RunService(session).get(run_id, user.id)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunDetail,
    summary="Cancelar uma execução",
    description="Para antes do próximo passo. As linhas que faltavam ficam como puladas.",
    responses={**NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def cancel_run(run_id: RunId, user: CurrentUser, session: DbSession) -> RunDetail:
    return RunService(session).cancel(run_id, user.id)


@router.get(
    "/runs/{run_id}/report",
    response_class=Response,
    summary="Baixar o relatório em PDF",
    description="Gera um PDF com o resultado de cada linha.",
    responses={
        **NOT_FOUND_RESPONSE,
        200: {"content": {"application/pdf": {}}, "description": "O relatório."},
    },
)
def download_report(run_id: RunId, user: CurrentUser, session: DbSession) -> Response:
    file_name, content = RunService(session).report_pdf(run_id, user.id)
    return _attachment(file_name, content, "application/pdf")


@router.get(
    "/runs/{run_id}/export",
    response_class=Response,
    summary="Baixar o resultado em CSV",
    description="Exporta uma linha por cópia. Células que virariam fórmula no Excel saem neutralizadas.",
    responses={
        **NOT_FOUND_RESPONSE,
        200: {"content": {"text/csv": {}}, "description": "A planilha."},
    },
)
def export_run(run_id: RunId, user: CurrentUser, session: DbSession) -> Response:
    file_name, content = RunService(session).export_csv(run_id, user.id)
    return _attachment(file_name, content, "text/csv; charset=utf-8")


@router.get(
    "/artifacts/{artifact_id}",
    response_class=FileResponse,
    summary="Baixar um arquivo gerado",
    description="Baixa um PDF, XML ou screenshot gerado por uma execução. Sempre como anexo.",
    responses={
        **NOT_FOUND_RESPONSE,
        200: {"content": {"application/octet-stream": {}}, "description": "O arquivo."},
    },
)
def download_artifact(
    artifact_id: Annotated[uuid.UUID, Path(description="Identificador do arquivo.")],
    user: CurrentUser,
    session: DbSession,
) -> FileResponse:
    artifact, path = RunService(session).get_artifact(artifact_id, user.id)
    return FileResponse(path, media_type=artifact.content_type, filename=artifact.file_name)
