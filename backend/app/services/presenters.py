"""Converte registros do banco nas respostas da API."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.models.enums import ArtifactKind, CaptureKind, VersionSource
from app.models.flow import Flow, Step, StepVersion
from app.models.repair import HelpRequest, Repair
from app.models.run import Run, RunItem, RunLogEntry
from app.models.schedule import Schedule
from app.repositories.run_repository import RunCounts
from app.schemas.flow import StepResponse
from app.schemas.repair import HelpOption, HelpRequestResponse, RepairResponse
from app.schemas.run import RunCapture, RunDetail, RunItemResponse, RunLogLine, RunStep, RunSummary
from app.schemas.schedule import ScheduleResponse
from app.services.templating import is_placeholder

_PATH_SEPARATOR = " › "


def current_version(step: Step) -> StepVersion | None:
    return next((version for version in step.versions if version.is_current), None)


def current_target(step: Step) -> dict[str, Any]:
    version = current_version(step)
    return version.target if version else {}


def _target_name(target: dict[str, Any]) -> str:
    for key in ("text", "label", "anchor", "placeholder", "name", "css"):
        if target.get(key):
            return str(target[key])
    return ""


def describe_target(target: dict[str, Any] | None) -> str:
    """O caminho em palavras, como "Ações › Baixar como PDF"."""
    if not target:
        return ""
    parts = [_target_name(item) for item in target.get("prelude", [])] + [_target_name(target)]
    return _PATH_SEPARATOR.join(part for part in parts if part)


def portal_of(flow: Flow) -> str:
    return urlsplit(flow.start_url).hostname or ""


def step_response(step: Step) -> StepResponse:
    version = current_version(step)
    repaired = version is not None and version.source != VersionSource.RECORDING
    return StepResponse(
        id=step.id,
        position=step.position,
        action=step.action,
        intent=step.intent,
        postcondition=step.postcondition,
        uses_credential=step.credential_field is not None,
        irreversible=step.irreversible,
        auto_confirm=step.auto_confirm,
        save_as=step.save_as,
        filled_from_capture=(
            step.value_template.strip("{}")
            if step.value_template and is_placeholder(step.value_template)
            else None
        ),
        capture_key=step.capture_key,
        capture_label=step.capture_label,
        capture_kind=step.capture_kind,
        repaired_at=version.created_at if repaired else None,
        current_path=describe_target(version.target) if version else (step.url_template or ""),
    )


def schedule_response(schedule: Schedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=schedule.id,
        flow_id=schedule.flow_id,
        cron=schedule.cron,
        timezone=schedule.timezone,
        enabled=schedule.enabled,
        next_run_at=schedule.next_run_at,
        row_count=len(schedule.rows),
    )


def _duration_seconds(run: Run) -> float:
    start = run.started_at or run.created_at
    end = run.finished_at or datetime.now(UTC)
    return max(0.0, (end - start).total_seconds())


def run_summary(run: Run, counts: RunCounts | None) -> RunSummary:
    counts = counts or RunCounts()
    return RunSummary(
        id=run.id,
        flow_id=run.flow_id,
        flow_name=run.flow.name,
        status=run.status,
        trigger=run.trigger,
        total=counts.total,
        done=counts.done,
        repaired=counts.repaired,
        failed=counts.failed,
        created_at=run.created_at,
        finished_at=run.finished_at,
        duration_seconds=_duration_seconds(run),
    )


def _item_response(item: RunItem) -> RunItemResponse:
    # Tabelas podem ser grandes e a tela consulta esta resposta o tempo todo: aqui só a contagem
    values = {k: v for k, v in (item.output or {}).items() if isinstance(v, str)}
    tables = {k: len(v) for k, v in (item.output or {}).items() if isinstance(v, list)}
    file = next((a for a in reversed(item.artifacts) if a.kind == ArtifactKind.FILE), None)
    screenshot = next(
        (a for a in reversed(item.artifacts) if a.kind == ArtifactKind.SCREENSHOT), None
    )
    return RunItemResponse(
        id=item.id,
        output=values,
        table_rows=tables,
        position=item.position,
        label=item.label,
        status=item.status,
        duration_ms=item.duration_ms,
        error_message=item.error_message,
        problem_step_position=item.problem_step_position,
        resolved_layer=item.resolved_layer,
        file_artifact_id=file.id if file else None,
        file_name=file.file_name if file else None,
        screenshot_artifact_id=screenshot.id if screenshot else None,
    )


def run_detail(run: Run, counts: RunCounts | None, log: list[RunLogEntry]) -> RunDetail:
    return RunDetail(
        **run_summary(run, counts).model_dump(),
        portal=portal_of(run.flow),
        captures=[
            RunCapture(
                key=step.capture_key,
                label=step.capture_label,
                kind=step.capture_kind,
                columns=(
                    current_target(step).get("neighbors", [])
                    if step.capture_kind == CaptureKind.TABLE
                    else []
                ),
            )
            for step in run.flow.steps
            if step.capture_key
        ],
        items=[_item_response(item) for item in run.items],
        log=[RunLogLine.model_validate(entry) for entry in log],
        steps=[RunStep(position=step.position, intent=step.intent) for step in run.flow.steps],
    )


def help_response(request: HelpRequest) -> HelpRequestResponse:
    return HelpRequestResponse(
        id=request.id,
        kind=request.kind,
        run_id=request.run_id,
        flow_name=request.run.flow.name,
        item_position=request.item.position,
        title=request.title,
        message=request.message,
        options=[HelpOption(id=o["id"], text=o["text"], score=o["score"]) for o in request.options],
        expires_at=request.expires_at,
    )


def repair_response(repair: Repair) -> RepairResponse:
    return RepairResponse(
        id=repair.id,
        flow_id=repair.step.flow_id,
        flow_name=repair.step.flow.name,
        run_id=repair.run_id,
        step_position=repair.step.position,
        intent=repair.step.intent,
        layer=repair.layer,
        score=repair.score,
        old_path=describe_target(repair.old_version.target) if repair.old_version else "",
        new_path=describe_target(repair.new_version.target) if repair.new_version else "",
        explanation=repair.explanation,
        created_at=repair.created_at,
    )
