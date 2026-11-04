import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import FlowStatus, StepAction, VariableSource, VariableStatus
from app.schemas.run import RunSummary
from app.schemas.schedule import ScheduleResponse

MAX_STEPS = 200
_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$"
)


def normalize_host(value: str) -> str:
    host = value.strip().lower()
    if not _HOSTNAME.match(host):
        raise ValueError("domínio inválido")
    return host


def _check_web_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("o endereço precisa começar com http:// ou https://")
    return value


class RecordedTarget(BaseModel):
    """A impressão digital do elemento, como a extensão captura."""

    model_config = ConfigDict(extra="forbid")

    role: str | None = Field(
        default=None, max_length=40, description="Papel do elemento, como `button`."
    )
    tag: str | None = Field(default=None, max_length=40, description="Tag HTML do elemento.")
    text: str | None = Field(default=None, max_length=300, description="Texto visível do elemento.")
    label: str | None = Field(
        default=None, max_length=300, description="Rótulo associado ao campo."
    )
    placeholder: str | None = Field(
        default=None, max_length=300, description="Texto de dica do campo."
    )
    name: str | None = Field(default=None, max_length=200, description="Atributo `name` do campo.")
    test_id: str | None = Field(default=None, max_length=200, description="Atributo `data-testid`.")
    css: str | None = Field(
        default=None, max_length=1000, description="Seletor CSS no momento da gravação."
    )
    input_type: str | None = Field(
        default=None, max_length=40, description="Atributo `type` do campo."
    )
    autocomplete: str | None = Field(
        default=None, max_length=80, description="Atributo `autocomplete` do campo."
    )
    neighbors: list[str] = Field(
        default_factory=list, max_length=10, description="Textos dos elementos vizinhos."
    )
    relative_position: str | None = Field(
        default=None, max_length=200, description="Posição descrita em palavras."
    )

    @field_validator("neighbors")
    @classmethod
    def _limit_neighbors(cls, value: list[str]) -> list[str]:
        return [item[:200] for item in value]


class RecordedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: StepAction = Field(description="O que a pessoa fez neste passo.")
    url: str | None = Field(
        default=None, max_length=2000, description="Endereço aberto, em `navigate`."
    )
    target: RecordedTarget | None = Field(
        default=None, description="Elemento usado. Obrigatório fora de `navigate`."
    )
    value: str | None = Field(
        default=None, max_length=5000, description="Valor digitado ou escolhido."
    )
    sensitive: bool = Field(
        default=False, description="`true` quando o campo guarda senha ou outro dado sigiloso."
    )
    downloaded_extension: str | None = Field(
        default=None,
        max_length=12,
        pattern=r"^[A-Za-z0-9]+$",
        description="Extensão do arquivo baixado por este passo.",
    )

    @model_validator(mode="after")
    def _check_consistency(self) -> "RecordedStep":
        if self.action == StepAction.NAVIGATE:
            if not self.url:
                raise ValueError("um passo navigate precisa de url")
            _check_web_url(self.url)
        elif self.target is None:
            raise ValueError("este passo precisa de target")
        return self


class RecordingCreate(BaseModel):
    """A gravação enviada pela extensão ou importada no painel."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "Relatório mensal por loja",
                    "start_url": "https://portal.fornecedor.exemplo/relatorios",
                    "steps": [
                        {
                            "action": "navigate",
                            "url": "https://portal.fornecedor.exemplo/relatorios",
                        },
                        {
                            "action": "select",
                            "value": "Loja 07 - Centro",
                            "target": {"role": "combobox", "label": "Loja", "name": "loja"},
                        },
                        {
                            "action": "click",
                            "target": {
                                "role": "button",
                                "text": "Exportar PDF",
                                "neighbors": ["Imprimir"],
                            },
                            "downloaded_extension": "pdf",
                        },
                    ],
                }
            ]
        },
    )

    name: str = Field(min_length=1, max_length=160, description="Nome da tarefa.")
    start_url: str = Field(max_length=2000, description="Endereço onde a gravação começou.")
    steps: list[RecordedStep] = Field(
        min_length=1, max_length=MAX_STEPS, description="Passos na ordem em que aconteceram."
    )

    _check_start_url = field_validator("start_url")(_check_web_url)


class FlowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None, min_length=1, max_length=160, description="Novo nome da tarefa."
    )
    allowed_domains: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Domínios em que esta tarefa pode navegar.",
    )

    @field_validator("allowed_domains")
    @classmethod
    def _normalize_domains(cls, value: list[str] | None) -> list[str] | None:
        return [normalize_host(item) for item in value] if value is not None else None


class StepUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str | None = Field(
        default=None, min_length=1, max_length=300, description="O que este passo quer fazer."
    )
    irreversible: bool | None = Field(
        default=None, description="`true` quando o passo não tem volta."
    )
    auto_confirm: bool | None = Field(
        default=None, description="`true` para seguir sem pedir confirmação."
    )
    save_as: str | None = Field(
        default=None, max_length=500, description="Caminho do arquivo, como `{mes}/{loja}.pdf`."
    )


class VariableAnswer(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"is_variable": True, "source": "column"}]}
    )

    is_variable: bool = Field(
        description="`true` se o valor muda a cada cópia; `false` se fica sempre igual."
    )
    source: VariableSource | None = Field(
        default=None, description="De onde vem o valor, quando ele muda."
    )


class VariableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Identificador da variável.")
    name: str = Field(description="Nome da variável; também é o nome da coluna da planilha.")
    label: str = Field(description="Nome para mostrar na tela.")
    example: str = Field(description="Valor visto na gravação.")
    source: VariableSource = Field(description="De onde vem o valor.")
    status: VariableStatus = Field(description="`pending` enquanto a pessoa não respondeu.")


class StepResponse(BaseModel):
    id: uuid.UUID = Field(description="Identificador do passo.")
    position: int = Field(description="Ordem do passo, a partir de 1.")
    action: StepAction = Field(description="O que o passo faz.")
    intent: str = Field(description="O que o passo quer fazer, em palavras.")
    postcondition: dict[str, Any] = Field(
        description="O que precisa ser verdade para o passo contar como feito."
    )
    uses_credential: bool = Field(description="`true` quando o valor vem de uma credencial salva.")
    irreversible: bool = Field(description="`true` quando o passo não tem volta.")
    auto_confirm: bool = Field(description="`true` quando segue sem pedir confirmação.")
    save_as: str | None = Field(description="Caminho do arquivo gerado, quando houver.")
    repaired_at: datetime | None = Field(
        description="Quando o caminho atual foi encontrado por um reparo."
    )
    current_path: str = Field(description="O caminho atual até o elemento, em palavras.")


class FlowSummary(BaseModel):
    id: uuid.UUID = Field(description="Identificador da tarefa.")
    name: str = Field(description="Nome da tarefa.")
    status: FlowStatus = Field(description="Situação da tarefa.")
    portal: str = Field(description="Domínio principal da tarefa.")
    step_count: int = Field(description="Quantidade de passos.")
    created_at: datetime = Field(description="Quando a tarefa foi gravada.")
    schedule: ScheduleResponse | None = Field(description="Agenda da tarefa, se houver.")
    last_run: RunSummary | None = Field(description="Execução mais recente, se houver.")


class FlowDetail(FlowSummary):
    start_url: str = Field(description="Endereço onde a gravação começou.")
    allowed_domains: list[str] = Field(description="Domínios em que a tarefa pode navegar.")
    needs_credential: bool = Field(
        description="`true` quando a tarefa pede login e ainda falta salvar o acesso."
    )
    uses_credential: bool = Field(description="`true` quando algum passo usa login.")
    steps: list[StepResponse] = Field(description="Passos, em ordem.")
    variables: list[VariableResponse] = Field(description="O que muda a cada cópia.")
