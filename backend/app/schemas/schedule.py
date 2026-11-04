import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"enabled": False}]})

    enabled: bool | None = Field(default=None, description="`false` pausa a agenda.")
    cron: str | None = Field(
        default=None, max_length=64, description="Novo horário, em formato cron."
    )
    timezone: str | None = Field(
        default=None, max_length=64, description="Novo fuso, como `America/Fortaleza`."
    )


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "7b1f3c52-1111-4a55-9c0e-2f6f7b1f3c52",
                    "flow_id": "2f6f7b1f-2222-4a55-9c0e-7b1f3c527b1f",
                    "cron": "10 7 5 * *",
                    "timezone": "America/Fortaleza",
                    "enabled": True,
                    "next_run_at": "2026-12-05T10:10:00Z",
                    "row_count": 25,
                }
            ]
        }
    )

    id: uuid.UUID = Field(description="Identificador da agenda.")
    flow_id: uuid.UUID = Field(description="Tarefa agendada.")
    cron: str = Field(description="Horário em formato cron.")
    timezone: str = Field(description="Fuso em que o horário é contado.")
    enabled: bool = Field(description="`false` quando a agenda está pausada.")
    next_run_at: datetime = Field(description="Próximo disparo.")
    row_count: int = Field(description="Linhas que cada disparo vai processar.")
