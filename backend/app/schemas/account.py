from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import Password


class AccountUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"name": "Carla Souza", "email_alerts": False}]},
    )

    name: str | None = Field(default=None, min_length=1, max_length=120, description="Novo nome.")
    email_alerts: bool | None = Field(
        default=None, description="`false` para não receber alertas por e-mail."
    )


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str | None = Field(
        default=None,
        max_length=128,
        description="Senha atual. Só fica de fora em conta criada pelo Google, que ainda não tem senha.",
    )
    new_password: Password = Field(description="Nova senha, com no mínimo 8 caracteres.")


class AccountDeletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(
        max_length=320, description="O e-mail da conta, digitado para confirmar."
    )
    password: str | None = Field(
        default=None, max_length=128, description="Senha da conta, quando ela tem uma."
    )
