from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseSettings):
    """Configuração lida do ambiente ou do .env. Sem os segredos obrigatórios, a API não inicia."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # SecretStr evita que segredos apareçam em logs e mensagens de erro
    database_url: SecretStr
    test_database_url: SecretStr | None = None
    # Sem ENVIRONMENT, vale o modo mais seguro: /docs fechado e rede interna bloqueada
    environment: Literal["development", "production"] = "production"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Quantos proxies confiáveis ficam na frente da API. 0 no seu computador; 1 no Railway.
    # Com 0, o cabeçalho X-Forwarded-For é ignorado: ninguém escolhe o próprio IP
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_expires_minutes: int = 480
    recording_token_minutes: int = 120
    runner_token_days: int = 30
    # Separadas por vírgula, da mais nova para a mais antiga
    fernet_keys: SecretStr

    google_client_id: str | None = None

    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str | None = None
    llm_max_calls_per_run: int = 5
    llm_timeout_seconds: float = 30.0
    # Teto da resposta da IA (uma decisão em JSON). Sem ele, o Groq conta o máximo do modelo
    # no limite de tokens do plano e recusa a página inteira com "413 Payload Too Large"
    llm_max_output_tokens: int = Field(default=2048, ge=256, le=32768)
    # Teto do pacote que descreve a tela no Criar com IA. Em sites grandes (Google Agenda), os
    # elementos menos úteis ficam de fora. Num plano pago da IA, pode subir
    llm_max_payload_chars: int = Field(default=14000, ge=4000, le=400000)
    # Criar tarefa com IA: limite de passos e quanto esperar a pessoa responder uma dúvida
    ai_draft_max_steps: int = 40
    ai_draft_answer_timeout_seconds: int = 600

    brevo_api_key: SecretStr | None = None
    email_from: str | None = None
    panel_url: str = "http://localhost:5173"

    storage_dir: Path = BACKEND_DIR / "storage"
    # Com S3_BUCKET, os arquivos vão para um bucket compatível com S3 em vez de STORAGE_DIR.
    # Necessário quando a API e o worker ficam em máquinas separadas (Railway)
    s3_bucket: str | None = None
    # Vazio usa a AWS; para Railway, Cloudflare R2 ou MinIO, o endereço que eles informam
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
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
    # Porta em que o worker espera a extensão para rodar as tarefas no Chrome da pessoa.
    # Vazio: o worker abre um navegador próprio
    extension_runner_port: int | None = None
    # Onde a porta da extensão escuta. 127.0.0.1 no seu computador; 0.0.0.0 em container ou
    # no Ditto publicado. O lado do Playwright sempre fica só em 127.0.0.1
    extension_relay_host: str = "127.0.0.1"
    # Extensões aceitas, como ["chrome-extension://<id>"]. Vazio aceita qualquer extensão do
    # Chrome (o token ainda é exigido); fora do computador local, é obrigatório preencher
    extension_origins: list[str] = []
    # Só para os testes com o portal local: em produção o worker nunca acessa a rede interna
    allow_private_networks: bool = False

    worker_poll_seconds: float = 2.0
    # Sem a extensão: quantas execuções rodam ao mesmo tempo, cada uma com o seu Chromium
    worker_concurrency: int = Field(default=1, ge=1, le=16)
    # Com a extensão: quantas contas são atendidas ao mesmo tempo (uma linha de trabalho cada)
    worker_max_accounts: int = Field(default=20, ge=1, le=200)

    @field_validator(
        "extension_runner_port",
        "s3_bucket",
        "s3_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        mode="before",
    )
    @classmethod
    def _empty_is_off(cls, value: object) -> object:
        # No .env, "EXTENSION_RUNNER_PORT=" ou "S3_BUCKET=" vazio quer dizer desligado
        return None if value == "" else value

    @model_validator(mode="after")
    def _block_unsafe_production(self) -> Self:
        if self.environment == "production" and self.allow_private_networks:
            raise ValueError("ALLOW_PRIVATE_NETWORKS não pode ficar ligado em produção.")
        if self.s3_bucket and not (self.s3_access_key_id and self.s3_secret_access_key):
            raise ValueError(
                "Com S3_BUCKET, preencha também S3_ACCESS_KEY_ID e S3_SECRET_ACCESS_KEY."
            )
        if self.relay_is_public and not self.extension_origins:
            raise ValueError(
                "Com a porta da extensão aberta para a rede, preencha EXTENSION_ORIGINS com o "
                "endereço da extensão do Ditto (chrome-extension://<id>)."
            )
        return self

    @property
    def relay_is_public(self) -> bool:
        """A porta da extensão aceita conexões de fora desta máquina."""
        return bool(self.extension_runner_port) and self.extension_relay_host not in _LOOPBACK

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_key.get_secret_value() and self.llm_model)


settings = Settings()
