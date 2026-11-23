import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AiDraftStatus
from app.schemas.flow import _check_web_url

MAX_PROMPT_CHARS = 2000
MAX_ANSWER_CHARS = 300


class AiDraftCreate(BaseModel):
    """O pedido escrito que a IA transforma em tarefa."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "prompt": "Pesquise o time Boston Bruins e guarde a tabela de resultados.",
                    "start_url": "https://www.scrapethissite.com/pages/forms/",
                    "name": "Hóquei: resultados do time",
                }
            ]
        },
    )

    prompt: str = Field(
        min_length=10,
        max_length=MAX_PROMPT_CHARS,
        description="O que a tarefa deve fazer, escrito como você explicaria para uma pessoa.",
    )
    start_url: str = Field(max_length=2000, description="Endereço onde a tarefa começa.")
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
        description="Nome da tarefa. Vazio: a IA sugere um nome no fim.",
    )

    _check_start_url = field_validator("start_url")(_check_web_url)

    @field_validator("prompt", "name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class AiDraftAnswer(BaseModel):
    """A resposta da pessoa a uma dúvida da IA."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"answer": "Pode clicar"}]}
    )

    answer: str = Field(
        min_length=1,
        max_length=MAX_ANSWER_CHARS,
        description="Uma das opções oferecidas ou um texto livre curto.",
    )


class AiDraftQuestion(BaseModel):
    text: str = Field(description="A dúvida da IA, em português.")
    options: list[str] = Field(description="Respostas sugeridas. Texto livre também vale.")


class AiDraftEvent(BaseModel):
    at: datetime = Field(description="Quando aconteceu.")
    kind: str = Field(description="`step` (passo anotado), `info`, `question` ou `error`.")
    text: str = Field(description="O que aconteceu, em uma frase.")


class AiDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Identificador do rascunho.")
    status: AiDraftStatus = Field(description="Em que ponto a IA está.")
    prompt: str = Field(description="O pedido escrito.")
    start_url: str = Field(description="Onde a tarefa começa.")
    name: str | None = Field(description="Nome da tarefa, quando já existe.")
    step_count: int = Field(description="Quantos passos já foram anotados.")
    events: list[AiDraftEvent] = Field(
        description="O que a IA já fez, do mais antigo ao mais novo."
    )
    question: AiDraftQuestion | None = Field(description="A dúvida aberta, quando há uma.")
    error: str | None = Field(description="Por que a IA parou, quando falhou.")
    flow_id: uuid.UUID | None = Field(description="A tarefa criada, quando terminou.")
    created_at: datetime = Field(description="Quando o pedido foi feito.")
    updated_at: datetime = Field(description="Última mudança.")
