import uuid
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.enums import CaptureKind, FlowStatus, StepAction, VariableStatus, VersionSource
from app.models.flow import Flow, Step, StepVersion, Variable
from app.repositories.credential_repository import CredentialRepository
from app.repositories.flow_repository import FlowRepository
from app.repositories.run_repository import RunRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.common import Page
from app.schemas.flow import (
    FlowDetail,
    FlowSummary,
    FlowUpdate,
    RecordedStep,
    RecordingCreate,
    StepUpdate,
    VariableAnswer,
    VariableResponse,
)
from app.services import presenters, storage
from app.services.engine import postcondition
from app.services.templating import safe_relative_path, slugify

_SENSITIVE_AUTOCOMPLETE = ("password", "cc-", "one-time-code")
_USERNAME_TYPES = {"text", "email", "tel", None, ""}


def _is_sensitive(step: RecordedStep) -> bool:
    """O backend não confia no envio: mascara de novo, mesmo que a extensão tenha falhado."""
    target = step.target
    if step.sensitive or target is None:
        return step.sensitive
    if (target.input_type or "").lower() == "password":
        return True
    return any(mark in (target.autocomplete or "").lower() for mark in _SENSITIVE_AUTOCOMPLETE)


def _is_username_field(steps: list[RecordedStep], index: int) -> bool:
    """O campo de texto logo antes da senha é o usuário do login."""
    step = steps[index]
    if step.action != StepAction.FILL or step.target is None or _is_sensitive(step):
        return False
    if (step.target.input_type or "").lower() not in _USERNAME_TYPES:
        return False
    following = next((s for s in steps[index + 1 :] if s.action == StepAction.FILL), None)
    return following is not None and _is_sensitive(following)


def _recorded_postcondition(recorded: RecordedStep) -> dict[str, Any]:
    """O que a gravação já sabe sobre o resultado. Vazio deixa a análise escolher."""
    if recorded.downloaded_extension:
        return {"type": postcondition.DOWNLOAD, "extension": recorded.downloaded_extension}
    if recorded.optional and recorded.action == StepAction.CAPTURE:
        # Dado guardado sozinho da tela final: se faltar, fica vazio em vez de parar a tarefa
        return {"type": postcondition.NONE, "optional": True}
    return {}


def _build_step(steps: list[RecordedStep], index: int) -> Step:
    recorded = steps[index]
    credential_field = None
    if _is_sensitive(recorded):
        credential_field = "password"
    elif _is_username_field(steps, index):
        credential_field = "username"

    value = None if credential_field else recorded.value
    if recorded.value_from_capture and not credential_field:
        value = f"{{{slugify(recorded.value_from_capture)}}}"

    is_capture = recorded.action == StepAction.CAPTURE
    step = Step(
        position=index + 1,
        action=recorded.action,
        # O valor de campo sensível nunca é gravado
        value_template=None if is_capture else value,
        capture_key=slugify(recorded.capture_name) if is_capture else None,
        capture_label=recorded.capture_name.strip() if is_capture else None,
        capture_kind=(recorded.capture_kind or CaptureKind.VALUE) if is_capture else None,
        url_template=recorded.url,
        credential_field=credential_field,
        postcondition=_recorded_postcondition(recorded),
    )
    if recorded.target:
        target = recorded.target.model_dump(exclude_none=True, exclude_defaults=True)
        if recorded.spreadsheet_part:
            # Marca para a análise: célula de planilha não vira pergunta nem ganha nome da IA
            target["spreadsheet"] = recorded.spreadsheet_part
        step.versions.append(StepVersion(version=1, target=target, source=VersionSource.RECORDING))
    if recorded.spreadsheet_cell:
        _describe_spreadsheet_step(step, recorded)
    return step


def _describe_spreadsheet_step(step: Step, recorded: RecordedStep) -> None:
    cell = recorded.spreadsheet_cell
    if recorded.spreadsheet_part == "address":
        step.intent = f"Ir para a célula {cell}"
    else:
        shown = (step.value_template or "").rstrip("\n")
        step.intent = f'{cell}: escrever "{shown}"'[:300]
    # Depois do Enter a Caixa de Nome e a Barra de fórmulas mudam: conferir o campo falharia
    step.postcondition = {"type": postcondition.NONE}


def _allowed_domains(payload: RecordingCreate) -> list[str]:
    urls = [payload.start_url, *(step.url for step in payload.steps if step.url)]
    hosts = {(urlsplit(url).hostname or "").lower() for url in urls}
    return sorted((hosts | set(payload.allowed_hosts)) - {""})


class FlowService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.flows = FlowRepository(session)
        self.runs = RunRepository(session)
        self.schedules = ScheduleRepository(session)
        self.credentials = CredentialRepository(session)

    def _get(self, flow_id: uuid.UUID, owner_id: uuid.UUID) -> Flow:
        flow = self.flows.get_owned(flow_id, owner_id)
        if flow is None:
            raise NotFoundError("Esta tarefa não foi encontrada.")
        return flow

    def _summary_fields(self, flow: Flow) -> dict:
        schedule = self.schedules.get_for_flow(flow.id)
        latest = self.runs.latest_for_flows([flow.id]).get(flow.id)
        counts = self.runs.counts_for([latest.id]) if latest else {}
        return {
            "id": flow.id,
            "name": flow.name,
            "status": flow.status,
            "portal": presenters.portal_of(flow),
            "step_count": len(flow.steps),
            "created_at": flow.created_at,
            "schedule": presenters.schedule_response(schedule) if schedule else None,
            "last_run": presenters.run_summary(latest, counts.get(latest.id)) if latest else None,
        }

    def _detail(self, flow: Flow) -> FlowDetail:
        uses_credential = any(step.credential_field for step in flow.steps)
        has_credential = bool(
            self.credentials.list_for_domains(flow.owner_id, flow.allowed_domains)
        )
        return FlowDetail(
            **self._summary_fields(flow),
            start_url=flow.start_url,
            allowed_domains=flow.allowed_domains,
            uses_credential=uses_credential,
            needs_credential=uses_credential and not has_credential,
            steps=[presenters.step_response(step) for step in flow.steps],
            variables=[VariableResponse.model_validate(variable) for variable in flow.variables],
        )

    def create_from_recording(self, owner_id: uuid.UUID, payload: RecordingCreate) -> FlowDetail:
        flow = Flow(
            owner_id=owner_id,
            name=payload.name.strip(),
            start_url=payload.start_url,
            allowed_domains=_allowed_domains(payload),
            status=FlowStatus.ANALYZING,
        )
        flow.steps = [_build_step(payload.steps, index) for index in range(len(payload.steps))]
        self.flows.add(flow)
        self.session.commit()
        return self._detail(flow)

    def list(self, owner_id: uuid.UUID, limit: int, offset: int) -> Page[FlowSummary]:
        flows, total = self.flows.list_owned(owner_id, limit, offset)
        ids = [flow.id for flow in flows]
        schedules = {schedule.flow_id: schedule for schedule in self.schedules.list_for_flows(ids)}
        latest = self.runs.latest_for_flows(ids)
        counts = self.runs.counts_for([run.id for run in latest.values()])

        items = []
        for flow in flows:
            schedule = schedules.get(flow.id)
            run = latest.get(flow.id)
            items.append(
                FlowSummary(
                    id=flow.id,
                    name=flow.name,
                    status=flow.status,
                    portal=presenters.portal_of(flow),
                    step_count=len(flow.steps),
                    created_at=flow.created_at,
                    schedule=presenters.schedule_response(schedule) if schedule else None,
                    last_run=presenters.run_summary(run, counts.get(run.id)) if run else None,
                )
            )
        return Page(items=items, total=total, limit=limit, offset=offset)

    def get(self, flow_id: uuid.UUID, owner_id: uuid.UUID) -> FlowDetail:
        return self._detail(self._get(flow_id, owner_id))

    def update(self, flow_id: uuid.UUID, owner_id: uuid.UUID, payload: FlowUpdate) -> FlowDetail:
        flow = self._get(flow_id, owner_id)
        if payload.name is not None:
            flow.name = payload.name.strip()
        if payload.allowed_domains is not None:
            flow.allowed_domains = payload.allowed_domains
        self.session.commit()
        return self._detail(flow)

    def update_step(
        self, flow_id: uuid.UUID, step_id: uuid.UUID, owner_id: uuid.UUID, payload: StepUpdate
    ) -> FlowDetail:
        flow = self._get(flow_id, owner_id)
        step = self.flows.get_step(step_id, flow.id)
        if step is None:
            raise NotFoundError("Este passo não foi encontrado.")

        if payload.save_as is not None:
            # Confere o caminho agora, com valores de mentira, para o erro aparecer antes de rodar
            names = {variable.name: "x" for variable in flow.variables}
            safe_relative_path(payload.save_as, names, "arquivo")
            step.save_as = payload.save_as
        if payload.intent is not None:
            step.intent = payload.intent.strip()
        if payload.irreversible is not None:
            step.irreversible = payload.irreversible
        if payload.auto_confirm is not None:
            step.auto_confirm = payload.auto_confirm
        self.session.commit()
        return self._detail(flow)

    def remove_capture(self, flow_id: uuid.UUID, step_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Tira um dado capturado da tarefa. Só capturas: sem um clique, o resto não funcionaria."""
        flow = self._get(flow_id, owner_id)
        step = self.flows.get_step(step_id, flow.id)
        if step is None:
            raise NotFoundError("Este passo não foi encontrado.")
        if step.action != StepAction.CAPTURE:
            raise BusinessRuleError(
                "Só dá para remover dados capturados. Os outros passos fazem a tarefa."
            )
        placeholder = f"{{{step.capture_key}}}"
        if any(
            placeholder in (other.value_template or "") for other in flow.steps if other is not step
        ):
            raise BusinessRuleError(
                "Outro passo digita este dado. Ele precisa continuar sendo capturado."
            )
        # O worker está no meio de uma linha: a lista de passos não pode mudar debaixo dele
        if self.runs.has_running_for_flow(flow.id):
            raise ConflictError(
                "Esta tarefa está rodando agora. Espere terminar para remover o dado."
            )

        removed_position = step.position
        flow.steps.remove(step)
        self.session.flush()
        # Os números continuam em sequência; um de cada vez, porque a posição é única na tarefa
        for later in sorted(flow.steps, key=lambda item: item.position):
            if later.position > removed_position:
                later.position -= 1
                self.session.flush()
        self.session.commit()

    def answer_variable(
        self,
        flow_id: uuid.UUID,
        variable_id: uuid.UUID,
        owner_id: uuid.UUID,
        payload: VariableAnswer,
    ) -> FlowDetail:
        flow = self._get(flow_id, owner_id)
        variable = self.flows.get_variable(variable_id, flow.id)
        if variable is None:
            raise NotFoundError("Esta variável não foi encontrada.")

        if payload.is_variable:
            self._confirm_variable(flow, variable, payload)
        else:
            # O valor gravado continua no passo; só deixa de ser uma pergunta
            flow.variables.remove(variable)

        self.session.commit()
        return self._detail(flow)

    def _confirm_variable(self, flow: Flow, variable: Variable, payload: VariableAnswer) -> None:
        variable.status = VariableStatus.CONFIRMED
        if payload.source is not None:
            variable.source = payload.source
        step = next((item for item in flow.steps if item.id == variable.step_id), None)
        if step is not None:
            step.value_template = f"{{{variable.name}}}"

    def confirm(self, flow_id: uuid.UUID, owner_id: uuid.UUID) -> FlowDetail:
        flow = self._get(flow_id, owner_id)
        if flow.status == FlowStatus.ANALYZING:
            raise BusinessRuleError("A gravação ainda está sendo analisada.")
        if flow.status != FlowStatus.AWAITING_CONFIRMATION:
            raise ConflictError("Esta tarefa já foi confirmada.")
        if any(variable.status == VariableStatus.PENDING for variable in flow.variables):
            raise BusinessRuleError("Responda todas as perguntas antes de ativar a tarefa.")

        flow.status = FlowStatus.ACTIVE
        self.session.commit()
        return self._detail(flow)

    def delete(self, flow_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Apaga a tarefa e tudo o que é dela: passos, agenda, execuções e arquivos baixados."""
        flow = self._get(flow_id, owner_id)
        # O worker está no meio de uma linha: apagar agora derrubaria a execução sem aviso
        if self.runs.has_running_for_flow(flow.id):
            raise ConflictError(
                "Esta tarefa está rodando agora. Cancele a execução antes de excluir."
            )
        run_ids = self.runs.ids_for_flow(flow.id)
        # O banco apaga em cascata passos, versões, agenda, execuções e pedidos de ajuda
        self.session.delete(flow)
        self.session.commit()
        for run_id in run_ids:
            storage.delete_tree(f"{owner_id}/{run_id}")

    def archive(self, flow_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        flow = self._get(flow_id, owner_id)
        flow.status = FlowStatus.ARCHIVED
        schedule = self.schedules.get_for_flow(flow.id)
        if schedule is not None:
            schedule.enabled = False
        self.session.commit()
