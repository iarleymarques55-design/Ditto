"""Confirmação de e-mail por código: só entra quem prova que recebe os e-mails do endereço."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token
from app.models.email_verification import EmailVerification
from app.models.user import User
from app.services import email_verification_service

EMAIL = "carla@teste.com"
SENHA = "senha-longa-de-teste"


def _cadastrar(api: TestClient, senha: str = SENHA, email: str = EMAIL) -> Any:
    return api.post(
        "/api/v1/auth/register", json={"name": "Carla", "email": email, "password": senha}
    )


def _confirmar(api: TestClient, codigo: str, email: str = EMAIL) -> Any:
    return api.post("/api/v1/auth/verify-email", json={"email": email, "code": codigo})


def _entrar(api: TestClient, senha: str = SENHA) -> Any:
    return api.post("/api/v1/auth/login", json={"email": EMAIL, "password": senha})


def _codigo_errado(certo: str) -> str:
    return f"{(int(certo) + 1) % 1_000_000:06d}"


def _envelhecer(fabrica: sessionmaker[Session], **campos: timedelta) -> None:
    """Move os horários do código para trás, como se o tempo tivesse passado."""
    with fabrica() as sessao:
        registro = sessao.scalar(select(EmailVerification))
        for campo, recuo in campos.items():
            setattr(registro, campo, getattr(registro, campo) - recuo)
        sessao.commit()


# Cadastro


def test_cadastro_nao_entrega_acesso_antes_do_codigo(
    api: TestClient, codigos_enviados: dict[str, str]
) -> None:
    resposta = _cadastrar(api)

    assert resposta.status_code == 201
    assert resposta.json()["email"] == EMAIL
    assert "access_token" not in resposta.text
    assert len(codigos_enviados[EMAIL]) == 6 and codigos_enviados[EMAIL].isdigit()


def test_codigo_certo_entrega_o_acesso(api: TestClient, codigos_enviados: dict[str, str]) -> None:
    _cadastrar(api)

    resposta = _confirmar(api, codigos_enviados[EMAIL])

    assert resposta.status_code == 200
    token = resposta.json()["access_token"]
    eu = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert eu.status_code == 200
    # Depois de confirmado, o login comum funciona
    assert _entrar(api).status_code == 200


def test_codigo_nao_fica_no_banco(
    api: TestClient, codigos_enviados: dict[str, str], fabrica_sessao: sessionmaker[Session]
) -> None:
    _cadastrar(api)

    with fabrica_sessao() as sessao:
        registro = sessao.scalar(select(EmailVerification))
    assert registro.code_hash != codigos_enviados[EMAIL]
    assert codigos_enviados[EMAIL] not in registro.code_hash


def test_login_sem_confirmar_pede_o_codigo(
    api: TestClient, codigos_enviados: dict[str, str]
) -> None:
    _cadastrar(api)

    resposta = _entrar(api)

    assert resposta.status_code == 403
    assert resposta.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert "access_token" not in resposta.text
    # O código de antes continua valendo (o novo só sai depois de 1 minuto)
    assert _confirmar(api, codigos_enviados[EMAIL]).status_code == 200


def test_login_com_senha_errada_nao_revela_que_falta_confirmar(api: TestClient) -> None:
    _cadastrar(api)

    resposta = _entrar(api, senha="senha-errada-123")

    assert resposta.status_code == 401
    assert resposta.json()["code"] == "INVALID_CREDENTIALS"


def test_login_depois_de_1_minuto_manda_codigo_novo(
    api: TestClient, codigos_enviados: dict[str, str], fabrica_sessao: sessionmaker[Session]
) -> None:
    _cadastrar(api)
    primeiro = codigos_enviados[EMAIL]
    _envelhecer(fabrica_sessao, sent_at=timedelta(minutes=2))

    assert _entrar(api).status_code == 403

    novo = codigos_enviados[EMAIL]
    # O código antigo deixou de valer: só o último vale. (Os dois podem coincidir por acaso,
    # uma chance em um milhão; aí não há o que comparar)
    if novo != primeiro:
        assert _confirmar(api, primeiro).status_code == 400
    assert _confirmar(api, novo).status_code == 200


# Código errado e vencido


def test_codigo_errado_conta_as_tentativas_e_trava_na_quinta(
    api: TestClient, codigos_enviados: dict[str, str]
) -> None:
    _cadastrar(api)
    certo = codigos_enviados[EMAIL]
    errado = _codigo_errado(certo)

    mensagens = [_confirmar(api, errado).json()["detail"] for _ in range(5)]

    assert mensagens[0] == "Código incorreto. Restam 4 tentativas."
    assert mensagens[3] == "Código incorreto. Restam 1 tentativa."
    assert "muitas vezes" in mensagens[4]
    # Nem o código certo vale mais: é preciso pedir outro
    assert _confirmar(api, certo).status_code == 400


def test_codigo_vencido_nao_vale(
    api: TestClient, codigos_enviados: dict[str, str], fabrica_sessao: sessionmaker[Session]
) -> None:
    _cadastrar(api)
    _envelhecer(fabrica_sessao, expires_at=timedelta(minutes=16))

    resposta = _confirmar(api, codigos_enviados[EMAIL])

    assert resposta.status_code == 400
    assert "venceu" in resposta.json()["detail"]


@pytest.mark.parametrize("email", ["ninguem@teste.com", EMAIL])
def test_email_sem_codigo_pendente_responde_como_codigo_errado(
    email: str, api: TestClient, criar_conta: Any
) -> None:
    # Conta inexistente e conta já confirmada: a mesma resposta, sem revelar quem tem cadastro
    criar_conta(email=EMAIL)

    resposta = _confirmar(api, "123456", email=email)

    assert resposta.status_code == 400
    assert resposta.json() == {
        "detail": "Código incorreto ou vencido. Peça um novo código.",
        "code": "INVALID_CODE",
    }


@pytest.mark.parametrize("codigo", ["12345", "1234567", "abcdef", "12 345", ""])
def test_codigo_fora_do_formato_e_recusado(codigo: str, api: TestClient) -> None:
    assert _confirmar(api, codigo).status_code == 422


# Reenvio


def test_reenvio_responde_igual_exista_a_conta_ou_nao(
    api: TestClient, fabrica_sessao: sessionmaker[Session]
) -> None:
    _cadastrar(api)
    _envelhecer(fabrica_sessao, sent_at=timedelta(minutes=2))

    existe = api.post("/api/v1/auth/resend-code", json={"email": EMAIL})
    nao_existe = api.post("/api/v1/auth/resend-code", json={"email": "ninguem@teste.com"})

    assert existe.status_code == nao_existe.status_code == 202
    assert existe.json() == nao_existe.json()


def test_reenvio_respeita_1_por_minuto_e_5_por_hora(
    api: TestClient, codigos_enviados: dict[str, str], fabrica_sessao: sessionmaker[Session]
) -> None:
    enviados: list[str] = []

    def contar(user: Any, code: str) -> bool:
        enviados.append(code)
        codigos_enviados[user.email] = code
        return True

    with patch.object(email_verification_service, "deliver_code", contar):
        _cadastrar(api)
        # Logo em seguida: nada sai
        api.post("/api/v1/auth/resend-code", json={"email": EMAIL})
        assert len(enviados) == 1

        for _ in range(10):
            _envelhecer(fabrica_sessao, sent_at=timedelta(minutes=2))
            # O limite por IP da rota (5 por minuto) é outro: aqui conta só o limite da conta
            rate_limiter.reset()
            api.post("/api/v1/auth/resend-code", json={"email": EMAIL})
        # 5 por hora, contando o do cadastro
        assert len(enviados) == 5

        # Uma hora depois, volta a enviar
        _envelhecer(
            fabrica_sessao, sent_at=timedelta(hours=2), window_started_at=timedelta(hours=2)
        )
        rate_limiter.reset()
        api.post("/api/v1/auth/resend-code", json={"email": EMAIL})
        assert len(enviados) == 6


# Quem "reservou" o e-mail de outra pessoa


def test_cadastro_de_novo_assume_conta_nunca_confirmada(
    api: TestClient, codigos_enviados: dict[str, str]
) -> None:
    # Alguém cadastrou o e-mail da Carla, mas nunca recebeu o código
    _cadastrar(api, senha="senha-da-intrusa")

    resposta = _cadastrar(api, senha=SENHA)

    assert resposta.status_code == 201
    assert _confirmar(api, codigos_enviados[EMAIL]).status_code == 200
    # A senha que vale é a da dona; a da intrusa não entra mais
    assert _entrar(api).status_code == 200
    assert _entrar(api, senha="senha-da-intrusa").status_code == 401


def test_email_confirmado_nao_aceita_cadastro_de_novo(api: TestClient, criar_conta: Any) -> None:
    criar_conta(email=EMAIL)

    resposta = _cadastrar(api, senha="outra-senha-longa")

    assert resposta.status_code == 409


def test_token_de_conta_nunca_confirmada_nao_vale(
    api: TestClient, fabrica_sessao: sessionmaker[Session]
) -> None:
    # Contas de antes da confirmação por código: um token antigo não abre o painel
    _cadastrar(api)
    with fabrica_sessao() as sessao:
        conta = sessao.scalar(select(User).where(User.email == EMAIL))
    token = create_access_token(conta.id)

    resposta = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resposta.status_code == 401


# Google


def test_conta_nova_pelo_google_ja_vem_confirmada(
    api: TestClient, fabrica_sessao: sessionmaker[Session]
) -> None:
    claims = {
        "iss": "accounts.google.com",
        "sub": "google-carla",
        "email": EMAIL,
        "email_verified": True,
        "name": "Carla",
    }
    with patch("app.services.auth_service._verify_google_token", return_value=claims):
        resposta = api.post("/api/v1/auth/google", json={"credential": "t"})

    assert resposta.status_code == 200
    with fabrica_sessao() as sessao:
        assert sessao.scalar(select(User)).email_verified_at is not None


# Falha de envio


def test_sem_conseguir_enviar_o_email_a_conta_nao_e_criada(
    api: TestClient, fabrica_sessao: sessionmaker[Session]
) -> None:
    with patch.object(email_verification_service, "deliver_code", return_value=False):
        resposta = _cadastrar(api)

    assert resposta.status_code == 503
    assert resposta.json()["code"] == "EMAIL_NOT_SENT"
    with fabrica_sessao() as sessao:
        assert sessao.scalar(select(User)) is None
        assert sessao.scalar(select(EmailVerification)) is None


def test_em_producao_falha_do_brevo_nao_vira_codigo_no_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.undo()  # tira a caixa de entrada falsa dos testes
    monkeypatch.setattr(email_verification_service, "send_email", lambda *_: False)
    monkeypatch.setattr(settings, "environment", "production")
    conta = User(email=EMAIL, name="Carla")

    with caplog.at_level(logging.WARNING):
        assert email_verification_service.deliver_code(conta, "482913") is False
    assert "482913" not in caplog.text


def test_em_desenvolvimento_o_codigo_vai_para_o_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # No computador de quem desenvolve, o Brevo pode recusar o IP: o código aparece no terminal
    monkeypatch.undo()
    monkeypatch.setattr(email_verification_service, "send_email", lambda *_: False)
    monkeypatch.setattr(settings, "environment", "development")
    conta = User(email=EMAIL, name="Carla")

    with caplog.at_level(logging.WARNING):
        assert email_verification_service.deliver_code(conta, "482913") is True
    assert "482913" in caplog.text


def test_email_tem_o_codigo_e_o_prazo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    enviados: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        email_verification_service,
        "send_email",
        lambda para, assunto, texto: enviados.append((para, assunto, texto)) or True,
    )

    email_verification_service.deliver_code(User(email=EMAIL, name="Carla"), "482913")

    para, assunto, texto = enviados[0]
    assert para == EMAIL
    assert "482913" in assunto and "482913" in texto
    assert "15 minutos" in texto


def test_horario_do_codigo_e_de_agora(
    api: TestClient, fabrica_sessao: sessionmaker[Session]
) -> None:
    _cadastrar(api)
    with fabrica_sessao() as sessao:
        registro = sessao.scalar(select(EmailVerification))
    restante = registro.expires_at - datetime.now(UTC)
    assert timedelta(minutes=14) < restante <= timedelta(minutes=15)
