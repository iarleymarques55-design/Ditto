import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.enums import HelpKind, HelpStatus, ItemStatus, LogLevel, RunStatus, VersionSource
from app.models.flow import Step, StepVersion
from app.models.repair import HelpRequest, Repair
from app.models.run import Run
from app.repositories.repair_repository import RepairRepository
from app.repositories.run_repository import RunRepository
from app.schemas.common import Page
from app.schemas.repair import (
    HelpAction,
    HelpAnswer,
    HelpRequestResponse,
    LayerStat,
    RepairResponse,
)
from app.services import presenters, run_lifecycle

_ALLOWED_ACTIONS = {
    HelpKind.CONFIRM: {HelpAction.CONFIRM, HelpAction.DECLINE},
    HelpKind.CHOOSE: {HelpAction.CHOOSE, HelpAction.SKIP},
    HelpKind.CAPTCHA: {HelpAction.RETRY, HelpAction.SKIP},
    HelpKind.UNCERTAIN: {HelpAction.RETRY, HelpAction.SKIP},
}
_LAYERS = (1, 2, 3, 4)


def save_new_version(
    session: Session,
    step: Step,
    target: dict,
    source: VersionSource,
    *,
    owner_id: uuid.UUID,
    run_id: uuid.UUID | None,
    layer: int,
    score: float | None,
    explanation: str,
) -> Repair:
    """Reparo não apaga o passado: o caminho novo vira uma versão e o antigo continua guardado."""
    old = session.scalar(
        select(StepVersion).where(StepVersion.step_id == step.id, StepVersion.is_current.is_(True))
    )
    highest = (
        session.scalar(select(func.max(StepVersion.version)).where(StepVersion.step_id == step.id))
        or 0
    )
    if old is not None:
        old.is_current = False

    new = StepVersion(
        step_id=step.id, version=highest + 1, target=target, source=source, is_current=True
    )
    session.add(new)
    session.flush()

    repair = Repair(
        owner_id=owner_id,
        step_id=step.id,
        run_id=run_id,
        layer=layer,
        old_version_id=old.id if old else None,
        new_version_id=new.id,
        score=score,
        explanation=explanation,
    )
    session.add(repair)
    return repair


class RepairService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repairs = RepairRepository(session)
        self.runs = RunRepository(session)

    def list_repairs(self, owner_id: uuid.UUID, limit: int, offset: int) -> Page[RepairResponse]:
        repairs, total = self.repairs.list_repairs(owner_id, limit, offset)
        return Page(
            items=[presenters.repair_response(r) for r in repairs],
            total=total,
            limit=limit,
            offset=offset,
        )

    def layer_stats(self, owner_id: uuid.UUID, days: int) -> list[LayerStat]:
        since = datetime.now(UTC) - timedelta(days=days)
        counts = self.runs.layer_stats(owner_id, since)
        return [LayerStat(layer=layer, steps=counts.get(layer, 0)) for layer in _LAYERS]

    def list_open_help(
        self, owner_id: uuid.UUID, run_id: uuid.UUID | None
    ) -> list[HelpRequestResponse]:
        return [
            presenters.help_response(request)
            for request in self.repairs.list_open_help(owner_id, run_id)
        ]

    def answer(self, help_id: uuid.UUID, owner_id: uuid.UUID, payload: HelpAnswer) -> None:
        request = self.repairs.get_help_for_update(help_id, owner_id)
        if request is None:
            raise NotFoundError("Este pedido não foi encontrado.")
        if request.status != HelpStatus.OPEN:
            raise ConflictError("Este pedido já foi respondido.")
        if payload.action not in _ALLOWED_ACTIONS[request.kind]:
            raise BusinessRuleError("Esta resposta não serve para este pedido.")

        run = self.session.get(Run, request.run_id)
        item = request.item
        if run.status != RunStatus.WAITING_HUMAN:
            raise ConflictError("Esta execução não está mais esperando uma resposta.")

        if payload.action == HelpAction.CONFIRM:
            run.confirmed_step_ids = [*run.confirmed_step_ids, str(request.step_id)]
            item.status = ItemStatus.PENDING
            run_lifecycle.add_log(
                self.session, run, LogLevel.OK, "você confirmou: seguindo com as cópias"
            )
        elif payload.action == HelpAction.DECLINE:
            # A resposta vale para o lote: nenhuma outra linha toca neste passo
            run_lifecycle.skip_open_items(self.session, run)
            run_lifecycle.add_log(
                self.session, run, LogLevel.INFO, "você não confirmou: nada foi enviado"
            )
        elif payload.action == HelpAction.CHOOSE:
            self._apply_choice(request, run, payload.option_id)
        elif payload.action == HelpAction.SKIP:
            item.status = ItemStatus.SKIPPED
            item.finished_at = datetime.now(UTC)
            run_lifecycle.add_log(
                self.session, run, LogLevel.INFO, f"linha {item.position} pulada a seu pedido"
            )
        else:
            item.status = ItemStatus.PENDING
            run_lifecycle.add_log(
                self.session, run, LogLevel.INFO, f"linha {item.position}: tentando de novo"
            )

        request.status = HelpStatus.ANSWERED
        request.answer = payload.action.value
        request.answered_at = datetime.now(UTC)
        run_lifecycle.resume(self.session, run)
        self.session.commit()

    def _apply_choice(self, request: HelpRequest, run: Run, option_id: str | None) -> None:
        option = next((o for o in request.options if o["id"] == option_id), None)
        if option is None:
            raise BusinessRuleError("Escolha uma das opções do pedido.")

        save_new_version(
            self.session,
            request.step,
            option["target"],
            VersionSource.HUMAN,
            owner_id=request.owner_id,
            run_id=run.id,
            layer=4,
            score=option["score"],
            explanation="Você escolheu o caminho novo, e ele passou a valer para as próximas cópias.",
        )
        request.item.status = ItemStatus.PENDING
        request.item.resolved_layer = 4
        run_lifecycle.add_log(
            self.session, run, LogLevel.OK, f"novo caminho salvo: {option['text']}"
        )
