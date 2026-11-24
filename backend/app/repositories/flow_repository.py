import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import FlowStatus
from app.models.flow import Flow, Step, StepVersion, Variable


class FlowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, flow: Flow) -> Flow:
        self.session.add(flow)
        return flow

    def get_owned(self, flow_id: uuid.UUID, owner_id: uuid.UUID) -> Flow | None:
        return self.session.scalar(
            select(Flow)
            .where(
                Flow.id == flow_id, Flow.owner_id == owner_id, Flow.status != FlowStatus.ARCHIVED
            )
            .options(
                selectinload(Flow.steps).selectinload(Step.versions), selectinload(Flow.variables)
            )
        )

    def list_owned(self, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Flow], int]:
        condition = (Flow.owner_id == owner_id, Flow.status != FlowStatus.ARCHIVED)
        total = self.session.scalar(select(func.count()).select_from(Flow).where(*condition)) or 0
        flows = self.session.scalars(
            select(Flow)
            .where(*condition)
            .options(selectinload(Flow.steps))
            .order_by(Flow.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(flows), total

    def get_step(self, step_id: uuid.UUID, flow_id: uuid.UUID) -> Step | None:
        return self.session.scalar(select(Step).where(Step.id == step_id, Step.flow_id == flow_id))

    def get_variable(self, variable_id: uuid.UUID, flow_id: uuid.UUID) -> Variable | None:
        return self.session.scalar(
            select(Variable).where(Variable.id == variable_id, Variable.flow_id == flow_id)
        )

    def claim_for_analysis(self) -> Flow | None:
        """Pega uma gravação para analisar. SKIP LOCKED: dois workers nunca pegam a mesma."""
        return self.session.scalar(
            select(Flow)
            .where(Flow.status == FlowStatus.ANALYZING)
            .order_by(Flow.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    def lock_for_analysis(self, flow_id: uuid.UUID) -> Flow | None:
        """A mesma gravação de novo, travada, para a segunda tentativa da análise."""
        return self.session.scalar(
            select(Flow)
            .where(Flow.id == flow_id, Flow.status == FlowStatus.ANALYZING)
            .with_for_update(skip_locked=True)
        )

    def current_version(self, step_id: uuid.UUID) -> StepVersion | None:
        return self.session.scalar(
            select(StepVersion).where(
                StepVersion.step_id == step_id, StepVersion.is_current.is_(True)
            )
        )

    def highest_version_number(self, step_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                select(func.max(StepVersion.version)).where(StepVersion.step_id == step_id)
            )
            or 0
        )
