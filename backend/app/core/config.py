from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configuração lida do ambiente ou do .env. Sem os segredos obrigatórios, a API não inicia."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # SecretStr evita que segredos apareçam em logs e mensagens de erro
    database_url: SecretStr
    test_database_url: SecretStr | None = None
    environment: Literal["development", "production"] = "development"
    cors_origins: list[str] = ["http://localhost:5173"]

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_expires_minutes: int = 480
    recording_token_minutes: int = 120
    # Separadas por vírgula, da mais nova para a mais antiga
    fernet_keys: SecretStr

    google_client_id: str | None = None

    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str | None = None
    llm_max_calls_per_run: int = 5
    llm_timeout_seconds: float = 30.0

    brevo_api_key: SecretStr | None = None
    email_from: str | None = None
    panel_url: str = "http://localhost:5173"

    storage_dir: Path = BACKEND_DIR / "storage"
    artifact_retention_days: int = 30

    max_upload_bytes: int = 5 * 1024 * 1024
    max_body_bytes: int = 10 * 1024 * 1024
    max_batch_rows: int = 500

    # Limiares da escada de reparo
    similarity_threshold: float = 0.75
    similarity_margin: float = 0.05
    candidate_floor: float = 0.45
    circuit_breaker_failures: int = 3
    help_timeout_hours: int = 72
    stale_run_minutes: int = 5

    step_timeout_ms: int = 15000
    # Quanto esperar um elemento aparecer antes de achar que o site mudou
    element_wait_ms: int = 10000
    postcondition_timeout_ms: int = 8000
    browser_channel: str | None = None
    browser_headless: bool = True
    # Só para os testes com o portal local: em produção o worker nunca acessa a rede interna
    allow_private_networks: bool = False

    worker_poll_seconds: float = 2.0

    @model_validator(mode="after")
    def _block_unsafe_production(self) -> Self:
        if self.environment == "production" and self.allow_private_networks:
            raise ValueError("ALLOW_PRIVATE_NETWORKS não pode ficar ligado em produção.")
        return self

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_key.get_secret_value() and self.llm_model)


settings = Settings()
