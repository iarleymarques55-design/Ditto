import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.repair import HelpRequestResponse
from app.schemas.run import RunDetail, RunSummary


class UpcomingRun(BaseModel):
    flow_id: uuid.UUID = Field(description="Tarefa agendada.")
    flow_name: str = Field(description="Nome da tarefa.")
    next_run_at: datetime = Field(description="Próximo disparo.")
    cron: str = Field(description="Horário em formato cron.")
    timezone: str = Field(description="Fuso do horário.")


class DashboardSummary(BaseModel):
    copies_today: int = Field(description="Linhas concluídas hoje, no fuso informado.")
    help_requests: list[HelpRequestResponse] = Field(description="Pedidos esperando resposta.")
    highlight: RunDetail | None = Field(
        description="A execução rodando agora ou, sem nenhuma, a última que terminou."
    )
    recent_runs: list[RunSummary] = Field(description="Últimas execuções.")
    upcoming: list[UpcomingRun] = Field(description="Próximos disparos agendados.")
