import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.repair_repository import RepairRepository
from app.repositories.run_repository import RunRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.dashboard import DashboardSummary, UpcomingRun
from app.services import presenters
from app.services.run_service import ensure_valid_timezone

_RECENT_RUNS = 5
_UPCOMING_RUNS = 3


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.runs = RunRepository(session)
        self.repairs = RepairRepository(session)
        self.schedules = ScheduleRepository(session)

    def summary(self, owner_id: uuid.UUID, timezone: str) -> DashboardSummary:
        ensure_valid_timezone(timezone)
        start_of_day = datetime.now(ZoneInfo(timezone)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        recent, _ = self.runs.list_owned(owner_id, _RECENT_RUNS, 0)
        counts = self.runs.counts_for([run.id for run in recent])

        highlight = self.runs.find_highlight(owner_id)
        highlight_detail = None
        if highlight is not None:
            highlight_counts = self.runs.counts_for([highlight.id]).get(highlight.id)
            highlight_detail = presenters.run_detail(
                highlight, highlight_counts, self.runs.latest_log(highlight.id)
            )

        return DashboardSummary(
            copies_today=self.runs.count_copies_since(owner_id, start_of_day.astimezone(UTC)),
            help_requests=[
                presenters.help_response(item) for item in self.repairs.list_open_help(owner_id)
            ],
            highlight=highlight_detail,
            recent_runs=[presenters.run_summary(run, counts.get(run.id)) for run in recent],
            upcoming=[
                UpcomingRun(
                    flow_id=schedule.flow_id,
                    flow_name=schedule.flow.name,
                    next_run_at=schedule.next_run_at,
                    cron=schedule.cron,
                    timezone=schedule.timezone,
                )
                for schedule in self.schedules.list_upcoming(owner_id, _UPCOMING_RUNS)
            ],
        )
