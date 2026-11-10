import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import ArtifactKind, EventStatus, ItemStatus, RunStatus
from app.models.flow import Flow, Step
from app.models.run import Artifact, Run, RunItem, RunLogEntry, StepEvent

MAX_LOG_LINES = 60


@dataclass
class RunCounts:
    total: int = 0
    done: int = 0
    repaired: int = 0
    failed: int = 0


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: Run) -> Run:
        self.session.add(run)
        return run

    def get_owned(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> Run | None:
        return self.session.scalar(
            select(Run)
            .where(Run.id == run_id, Run.owner_id == owner_id)
            .options(
                joinedload(Run.flow).selectinload(Flow.steps),
                selectinload(Run.items).selectinload(RunItem.artifacts),
            )
        )

    def list_owned(
        self,
        owner_id: uuid.UUID,
        limit: int,
        offset: int,
        *,
        flow_id: uuid.UUID | None = None,
        statuses: list[RunStatus] | None = None,
    ) -> tuple[list[Run], int]:
        conditions = [Run.owner_id == owner_id]
        if flow_id:
            conditions.append(Run.flow_id == flow_id)
        if statuses:
            conditions.append(Run.status.in_(statuses))

        total = self.session.scalar(select(func.count()).select_from(Run).where(*conditions)) or 0
        runs = self.session.scalars(
            select(Run)
            .where(*conditions)
            .options(joinedload(Run.flow))
            .order_by(Run.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(runs), total

    def counts_for(self, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, RunCounts]:
        if not run_ids:
            return {}
        rows = self.session.execute(
            select(
                RunItem.run_id,
                func.count(),
                func.sum(
                    case(
                        (RunItem.status.in_([ItemStatus.SUCCEEDED, ItemStatus.REPAIRED]), 1),
                        else_=0,
                    )
                ),
                func.sum(case((RunItem.status == ItemStatus.REPAIRED, 1), else_=0)),
                func.sum(case((RunItem.status == ItemStatus.FAILED, 1), else_=0)),
            )
            .where(RunItem.run_id.in_(run_ids))
            .group_by(RunItem.run_id)
        )
        return {row[0]: RunCounts(row[1], row[2] or 0, row[3] or 0, row[4] or 0) for row in rows}

    def latest_for_flows(self, flow_ids: list[uuid.UUID]) -> dict[uuid.UUID, Run]:
        if not flow_ids:
            return {}
        runs = self.session.scalars(
            select(Run)
            .where(Run.flow_id.in_(flow_ids))
            .options(joinedload(Run.flow))
            .ext(distinct_on(Run.flow_id))
            .order_by(Run.flow_id, Run.created_at.desc())
        ).all()
        return {run.flow_id: run for run in runs}

    def latest_log(self, run_id: uuid.UUID) -> list[RunLogEntry]:
        entries = self.session.scalars(
            select(RunLogEntry)
            .where(RunLogEntry.run_id == run_id)
            .order_by(RunLogEntry.created_at.desc(), RunLogEntry.id)
            .limit(MAX_LOG_LINES)
        ).all()
        return list(reversed(entries))

    def find_highlight(self, owner_id: uuid.UUID) -> Run | None:
        """A execução rodando agora ou, sem nenhuma, a mais recente que terminou."""
        running = self.session.scalar(
            select(Run.id)
            .where(Run.owner_id == owner_id, Run.status == RunStatus.RUNNING)
            .order_by(Run.created_at.desc())
            .limit(1)
        )
        run_id = running or self.session.scalar(
            select(Run.id)
            .where(Run.owner_id == owner_id, Run.finished_at.is_not(None))
            .order_by(Run.finished_at.desc())
            .limit(1)
        )
        return self.get_owned(run_id, owner_id) if run_id else None

    def count_copies_since(self, owner_id: uuid.UUID, since: datetime) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(RunItem)
                .join(Run)
                .where(
                    Run.owner_id == owner_id,
                    RunItem.status.in_([ItemStatus.SUCCEEDED, ItemStatus.REPAIRED]),
                    RunItem.finished_at >= since,
                )
            )
            or 0
        )

    def get_artifact_owned(self, artifact_id: uuid.UUID, owner_id: uuid.UUID) -> Artifact | None:
        return self.session.scalar(
            select(Artifact).where(Artifact.id == artifact_id, Artifact.owner_id == owner_id)
        )

    def layer_stats(self, owner_id: uuid.UUID, since: datetime) -> dict[int, int]:
        rows = self.session.execute(
            select(StepEvent.layer, func.count())
            .join(Step, StepEvent.step_id == Step.id)
            .join(Flow, Step.flow_id == Flow.id)
            .where(
                Flow.owner_id == owner_id,
                StepEvent.status == EventStatus.OK,
                StepEvent.layer.is_not(None),
                StepEvent.created_at >= since,
            )
            .group_by(StepEvent.layer)
        )
        return {row[0]: row[1] for row in rows}

    # Daqui para baixo, só o worker usa

    def claim_queued(self) -> Run | None:
        """SKIP LOCKED: dois workers nunca pegam a mesma execução."""
        return self.session.scalar(
            select(Run)
            .where(Run.status == RunStatus.QUEUED)
            .order_by(Run.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    def list_stale(self, older_than: datetime) -> list[Run]:
        return list(
            self.session.scalars(
                select(Run)
                .where(Run.status == RunStatus.RUNNING, Run.heartbeat_at < older_than)
                .with_for_update(skip_locked=True)
            )
        )

    def touch_heartbeat(self, run_id: uuid.UUID, now: datetime) -> None:
        self.session.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == RunStatus.RUNNING)
            .values(heartbeat_at=now)
        )

    def list_expired_artifacts(self, older_than: datetime, limit: int = 200) -> list[Artifact]:
        return list(
            self.session.scalars(
                select(Artifact)
                .where(Artifact.created_at < older_than)
                .order_by(Artifact.created_at)
                .limit(limit)
            )
        )

    def delete_artifacts(self, artifact_ids: list[uuid.UUID]) -> None:
        self.session.execute(delete(Artifact).where(Artifact.id.in_(artifact_ids)))

    def replace_screenshot(self, item_id: uuid.UUID) -> list[str]:
        keys = self.session.scalars(
            select(Artifact.storage_key).where(
                Artifact.run_item_id == item_id, Artifact.kind == ArtifactKind.SCREENSHOT
            )
        ).all()
        self.session.execute(
            delete(Artifact).where(
                Artifact.run_item_id == item_id, Artifact.kind == ArtifactKind.SCREENSHOT
            )
        )
        return list(keys)
