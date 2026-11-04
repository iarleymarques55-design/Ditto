import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ItemStatus, LogLevel, RunStatus, RunTrigger


class RunSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "7b1f3c52-1111-4a55-9c0e-2f6f7b1f3c52",
                    "flow_id": "2f6f7b1f-2222-4a55-9c0e-7b1f3c527b1f",
                    "flow_name": "Relatório mensal por loja",
                    "status": "running",
                    "trigger": "manual",
                    "total": 25,
                    "done": 9,
                    "repaired": 1,
                    "failed": 0,
                    "created_at": "2026-11-04T10:10:00Z",
                    "finished_at": None,
                    "duration_seconds": 120,
                }
            ]
        }
    )

    id: uuid.UUID = Field(description="Identificador da execução.")
    flow_id: uuid.UUID = Field(description="Tarefa executada.")
    flow_name: str = Field(description="Nome da tarefa.")
    status: RunStatus = Field(description="Situação da execução.")
    trigger: RunTrigger = Field(description="`manual` ou `schedule`.")
    total: int = Field(description="Total de linhas.")
    done: int = Field(description="Linhas concluídas, com ou sem reparo.")
    repaired: int = Field(description="Linhas concluídas com reparo.")
    failed: int = Field(description="Linhas que falharam.")
    created_at: datetime = Field(description="Quando a execução foi criada.")
    finished_at: datetime | None = Field(description="Quando a execução terminou.")
    duration_seconds: float = Field(
        description="Tempo desde o início, ou a duração total depois de terminar."
    )


class RunItemResponse(BaseModel):
    id: uuid.UUID = Field(description="Identificador da linha.")
    position: int = Field(description="Posição da linha na planilha.")
    label: str = Field(description="Nome da linha, vindo da primeira coluna.")
    status: ItemStatus = Field(description="Situação da linha.")
    duration_ms: int | None = Field(description="Quanto a linha levou.")
    error_message: str | None = Field(description="O que deu errado, em palavras.")
    problem_step_position: int | None = Field(description="Passo em que houve problema ou reparo.")
    resolved_layer: int | None = Field(description="Camada que resolveu o problema, de 2 a 4.")
    file_artifact_id: uuid.UUID | None = Field(description="Arquivo gerado por esta linha.")
    file_name: str | None = Field(description="Nome do arquivo gerado.")
    screenshot_artifact_id: uuid.UUID | None = Field(
        description="Imagem da tela no momento do problema."
    )


class RunLogLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Identificador da linha.")
    level: LogLevel = Field(description="Tipo da linha.")
    message: str = Field(description="Texto da linha.")


class RunStep(BaseModel):
    position: int = Field(description="Ordem do passo.")
    intent: str = Field(description="O que o passo quer fazer.")


class RunDetail(RunSummary):
    portal: str = Field(description="Domínio principal da tarefa.")
    items: list[RunItemResponse] = Field(description="Linhas, em ordem.")
    log: list[RunLogLine] = Field(description="Últimas linhas do registro.")
    steps: list[RunStep] = Field(description="Passos da tarefa.")
