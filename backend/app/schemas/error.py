from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Formato único de erro da API."""

    model_config = {
        "json_schema_extra": {
            "examples": [{"detail": "Banco de dados indisponível.", "code": "DATABASE_UNAVAILABLE"}]
        }
    }

    detail: str = Field(description="Mensagem do erro em português.")
    code: str = Field(description="Código estável do erro, para o frontend tratar.")
