from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"status": "ok"}]}}

    status: str = Field(description="`ok` quando a API está respondendo.")


class DatabaseHealthResponse(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"status": "ok", "database": "connected"}]}}

    status: str = Field(description="`ok` quando o banco respondeu.")
    database: str = Field(description="Estado da conexão com o PostgreSQL.")
