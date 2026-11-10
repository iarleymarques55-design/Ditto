import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.enums import (
    ArtifactKind,
    CaptureKind,
    HelpStatus,
    LogLevel,
    RunStatus,
    RunTrigger,
    VariableSource,
)
from app.models.flow import Flow
from app.models.run import Artifact, Run
from app.repositories.flow_repository import FlowRepository
from app.repositories.repair_repository import RepairRepository
from app.repositories.run_repository import RunRepository
from app.schemas.common import Page
from app.schemas.run import RunDetail, RunSummary
from app.services import presenters, run_lifecycle, storage
from app.services.batch import neutralize_cell, parse_rows
from app.services.excel_report import build_workbook
from app.services.pdf_report import ITEM_STATUS_LABELS, build_run_report

_FINISHED = {RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELED}


def ensure_valid_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as error:
        # No Windows, um nome com caracteres inválidos vira erro de arquivo
        raise BusinessRuleError("Fuso horário inválido.") from error
    return name


def read_rows(flow: Flow, file_name: str | None, content: bytes | None) -> list[dict[str, str]]:
    """As colunas que a tarefa pede vêm da planilha. Sem colunas, é uma cópia só."""
    columns = [
        variable.name for variable in flow.variables if variable.source == VariableSource.COLUMN
    ]
    if not columns:
        return [{}]
    if not file_name or not content:
        raise BusinessRuleError(
            f"Envie a planilha com {'a coluna' if len(columns) == 1 else 'as colunas'} {', '.join(columns)}."
        )
    return parse_rows(file_name, content, columns)


class RunService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.runs = RunRepository(session)
        self.flows = FlowRepository(session)
        self.repairs = RepairRepository(session)

    def _get(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> Run:
        run = self.runs.get_owned(run_id, owner_id)
        if run is None:
            raise NotFoundError("Esta execução não foi encontrada.")
        return run

    def _detail(self, run: Run) -> RunDetail:
        counts = self.runs.counts_for([run.id]).get(run.id)
        return presenters.run_detail(run, counts, self.runs.latest_log(run.id))

    def create(
        self,
        owner_id: uuid.UUID,
        flow_id: uuid.UUID,
        timezone: str,
        file_name: str | None,
        content: bytes | None,
    ) -> RunDetail:
        ensure_valid_timezone(timezone)
        flow = self.flows.get_owned(flow_id, owner_id)
        if flow is None:
            raise NotFoundError("Esta tarefa não foi encontrada.")

        run_lifecycle.ensure_can_run(self.session, flow)
        rows = read_rows(flow, file_name, content)
        run = run_lifecycle.create_run(
            self.session, flow, rows, trigger=RunTrigger.MANUAL, timezone=timezone
        )
        self.session.commit()
        return self._detail(self._get(run.id, owner_id))

    def list(
        self,
        owner_id: uuid.UUID,
        limit: int,
        offset: int,
        flow_id: uuid.UUID | None,
        statuses: list[RunStatus] | None,
    ) -> Page[RunSummary]:
        runs, total = self.runs.list_owned(
            owner_id, limit, offset, flow_id=flow_id, statuses=statuses
        )
        counts = self.runs.counts_for([run.id for run in runs])
        items = [presenters.run_summary(run, counts.get(run.id)) for run in runs]
        return Page(items=items, total=total, limit=limit, offset=offset)

    def get(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> RunDetail:
        return self._detail(self._get(run_id, owner_id))

    def cancel(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> RunDetail:
        run = self._get(run_id, owner_id)
        if run.status in _FINISHED:
            raise ConflictError("Esta execução já terminou.")

        # Se estiver rodando, o worker vê a mudança antes do próximo passo e para
        run.status = RunStatus.CANCELED
        run_lifecycle.skip_open_items(self.session, run)
        run.finished_at = datetime.now(UTC)
        for request in self.repairs.list_open_for_run(run.id):
            request.status = HelpStatus.EXPIRED
        run_lifecycle.add_log(self.session, run, LogLevel.INFO, "execução cancelada")
        self.session.commit()
        self.session.refresh(run)
        return self._detail(self._get(run_id, owner_id))

    def report_pdf(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[str, bytes]:
        run = self._get(run_id, owner_id)
        counts = self.runs.counts_for([run.id]).get(run.id)
        return f"relatorio-{run.id}.pdf", build_run_report(run, counts)

    def get_item_output(
        self, run_id: uuid.UUID, item_id: uuid.UUID, owner_id: uuid.UUID
    ) -> dict[str, Any]:
        run = self._get(run_id, owner_id)
        item = next((candidate for candidate in run.items if candidate.id == item_id), None)
        if item is None:
            raise NotFoundError("Esta linha não foi encontrada.")
        return item.output or {}

    def export_xlsx(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[str, bytes]:
        run = self._get(run_id, owner_id)
        return f"execucao-{run.id}.xlsx", build_workbook(run)

    def export_csv(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[str, bytes]:
        run = self._get(run_id, owner_id)
        values = [s for s in run.flow.steps if s.capture_kind == CaptureKind.VALUE]
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            [
                "linha",
                "nome",
                "situacao",
                *(step.capture_label for step in values),
                "duracao_segundos",
                "arquivo",
                "erro",
            ]
        )
        for item in run.items:
            file = next((a.file_name for a in item.artifacts if a.kind == ArtifactKind.FILE), "")
            writer.writerow(
                [
                    item.position,
                    neutralize_cell(item.label),
                    ITEM_STATUS_LABELS[item.status],
                    *(
                        neutralize_cell(str((item.output or {}).get(s.capture_key, "")))
                        for s in values
                    ),
                    round(item.duration_ms / 1000, 1) if item.duration_ms else "",
                    neutralize_cell(file),
                    neutralize_cell(item.error_message or ""),
                ]
            )
        # A marca BOM faz o Excel reconhecer os acentos
        return f"execucao-{run.id}.csv", ("﻿" + buffer.getvalue()).encode("utf-8")

    def get_artifact(self, artifact_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[Artifact, str]:
        artifact = self.runs.get_artifact_owned(artifact_id, owner_id)
        if artifact is None:
            raise NotFoundError("Arquivo não encontrado.")
        return artifact, str(storage.path_for_read(artifact.storage_key))
