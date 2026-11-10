import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import HelpKind


class HelpAction(StrEnum):
    CONFIRM = "confirm"
    DECLINE = "decline"
    CHOOSE = "choose"
    RETRY = "retry"
    SKIP = "skip"


class HelpOption(BaseModel):
    id: str = Field(description="Identificador da opção.")
    text: str = Field(description="Texto do elemento na página.")
    score: float = Field(description="O quanto o elemento parece o gravado, de 0 a 1.")


class HelpRequestResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "7b1f3c52-1111-4a55-9c0e-2f6f7b1f3c52",
                    "kind": "confirm",
                    "run_id": "2f6f7b1f-2222-4a55-9c0e-7b1f3c527b1f",
                    "flow_name": "Guia de ISS da prefeitura",
                    "item_position": 1,
                    "title": 'Posso seguir com "Enviar a declaração"?',
                    "message": "O passo 6 não tem volta.",
                    "options": [],
                    "expires_at": "2026-11-07T10:10:00Z",
                }
            ]
        }
    )

    id: uuid.UUID = Field(description="Identificador do pedido.")
    kind: HelpKind = Field(description="Tipo de decisão que o pedido precisa.")
    run_id: uuid.UUID = Field(description="Execução parada por este pedido.")
    flow_name: str = Field(description="Nome da tarefa.")
    item_position: int = Field(description="Linha da planilha em que parou.")
    title: str = Field(description="A pergunta.")
    message: str = Field(description="O contexto da pergunta.")
    options: list[HelpOption] = Field(description="Opções para escolher, quando houver.")
    expires_at: datetime = Field(description="Até quando o pedido espera uma resposta.")


class HelpAnswer(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"action": "confirm"}]}
    )

    action: HelpAction = Field(description="A decisão tomada.")
    option_id: str | None = Field(
        default=None, max_length=32, description="Opção escolhida, com a ação `choose`."
    )


class RepairResponse(BaseModel):
    id: uuid.UUID = Field(description="Identificador do reparo.")
    flow_id: uuid.UUID = Field(description="Tarefa reparada.")
    flow_name: str = Field(description="Nome da tarefa.")
    run_id: uuid.UUID | None = Field(description="Execução em que o reparo aconteceu.")
    step_position: int = Field(description="Passo reparado.")
    intent: str = Field(description="O que o passo quer fazer.")
    layer: int = Field(description="Quem resolveu: 2 semelhança, 3 IA, 4 pessoa.")
    score: float | None = Field(description="Nota de semelhança, na camada 2.")
    old_path: str = Field(description="Caminho antigo, em palavras.")
    new_path: str = Field(description="Caminho novo, em palavras.")
    explanation: str = Field(description="O que mudou no site.")
    created_at: datetime = Field(description="Quando o reparo aconteceu.")


class LayerStat(BaseModel):
    layer: int = Field(description="Camada: 1 caminho gravado, 2 semelhança, 3 IA, 4 pessoa.")
    steps: int = Field(description="Passos concluídos por esta camada no período.")
