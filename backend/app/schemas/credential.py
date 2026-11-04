import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.flow import normalize_host


class CredentialCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "domain": "portal.fornecedor.exemplo",
                    "username": "financeiro",
                    "password": "senha-do-portal",
                }
            ]
        },
    )

    domain: str = Field(
        max_length=255, description="Domínio do portal. Salvar de novo substitui o acesso anterior."
    )
    username: str | None = Field(default=None, max_length=320, description="Usuário no portal.")
    password: str = Field(
        min_length=1,
        max_length=1024,
        description="Senha no portal. Fica cifrada e nunca volta na resposta.",
    )

    @field_validator("domain")
    @classmethod
    def _normalize_domain(cls, value: str) -> str:
        return normalize_host(value)


class CredentialResponse(BaseModel):
    """Só o que identifica o acesso: usuário e senha nunca saem da API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Identificador do acesso.")
    domain: str = Field(description="Domínio do portal.")
    updated_at: datetime = Field(description="Quando o acesso foi salvo pela última vez.")
