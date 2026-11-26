import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

MAX_BCRYPT_BYTES = 72


def _fits_bcrypt(password: str) -> str:
    if len(password.encode()) > MAX_BCRYPT_BYTES:
        raise ValueError(f"a senha pode ter no máximo {MAX_BCRYPT_BYTES} bytes")
    return password


Password = Annotated[
    str, StringConstraints(min_length=8, max_length=128), AfterValidator(_fits_bcrypt)
]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "Carla Souza",
                    "email": "carla@empresa.com.br",
                    "password": "uma-senha-longa",  # nosec B105: exemplo do Swagger
                }
            ]
        },
    )

    name: str = Field(min_length=1, max_length=120, description="Nome de quem usa a conta.")
    email: EmailStr = Field(description="E-mail de acesso. Precisa ser único.")
    password: Password = Field(description="Senha, com no mínimo 8 caracteres.")


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            # Exemplo do Swagger, não é uma senha de verdade
            "examples": [
                {"email": "carla@empresa.com.br", "password": "uma-senha-longa"}  # nosec B105
            ]
        },
    )

    email: EmailStr = Field(description="E-mail da conta.")
    password: str = Field(min_length=1, max_length=128, description="Senha da conta.")


class VerificationPendingResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "carla@empresa.com.br",
                    "message": "Enviamos um código de 6 dígitos para o seu e-mail.",
                }
            ]
        }
    )

    email: EmailStr = Field(description="E-mail para onde o código foi enviado.")
    message: str = Field(
        default="Enviamos um código de 6 dígitos para o seu e-mail.",
        description="Texto para mostrar a quem acabou de criar a conta.",
    )


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"email": "carla@empresa.com.br", "code": "482913"}]},
    )

    email: EmailStr = Field(description="E-mail da conta que está sendo confirmada.")
    code: str = Field(pattern=r"^\d{6}$", description="Código de 6 dígitos recebido por e-mail.")


class ResendCodeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"email": "carla@empresa.com.br"}]}
    )

    email: EmailStr = Field(description="E-mail da conta que ainda não foi confirmada.")


class MessageResponse(BaseModel):
    message: str = Field(description="Texto para mostrar a quem fez o pedido.")


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field(
        min_length=1, max_length=4096, description="Token de identidade emitido pelo Google."
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "7b1f3c52-1111-4a55-9c0e-2f6f7b1f3c52",
                    "name": "Carla Souza",
                    "email": "carla@empresa.com.br",
                    "has_password": True,  # nosec B105: diz se a conta tem senha, não é uma senha
                    "avatar_id": None,
                    "email_alerts": True,
                }
            ]
        },
    )

    id: uuid.UUID = Field(description="Identificador da conta.")
    name: str = Field(description="Nome de quem usa a conta.")
    email: EmailStr = Field(description="E-mail de acesso.")
    has_password: bool = Field(description="`false` em conta que só entra pelo Google.")
    avatar_id: str | None = Field(description="Muda a cada foto nova. Nulo quando não há foto.")
    email_alerts: bool = Field(description="`true` para receber alertas por e-mail.")


class RecordingTokenResponse(BaseModel):
    token: str = Field(description="Token da extensão. Só serve para enviar uma gravação.")
    expires_at: datetime = Field(description="Quando o token deixa de valer.")


class RunnerTokenResponse(BaseModel):
    token: str = Field(
        description="Token que liga a extensão ao worker. Não vale em nenhuma rota da API."
    )
    expires_at: datetime = Field(description="Quando o token deixa de valer.")


class TokenResponse(BaseModel):
    access_token: str = Field(description="Token JWT, enviado depois no cabeçalho Authorization.")
    token_type: str = Field(default="bearer", description="Sempre `bearer`.")
    user: UserResponse = Field(description="Conta que entrou.")
