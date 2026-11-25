"""Tokens que deveriam deixar de valer, e ações de conta que pedem prova de quem é a pessoa."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import ALGORITHM
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.engine.extension_relay import ExtensionRelay
from tests.test_executor_extensao import (
    ExtensaoFalsa,
    autenticador,
    esperar,
    id_da_conta,
    token_do_executor,
)

Cabecalho = dict[str, str]
EMAIL = "ana@teste.com"


def _claims() -> dict[str, Any]:
    return {
        "iss": "accounts.google.com",
        "sub": "google-ana",
        "email": EMAIL,
        "email_verified": True,
        "name": "Ana",
    }


def _entrar_com_google(api: TestClient) -> Cabecalho:
    with patch("app.services.auth_service._verify_google_token", return_value=_claims()):
        resposta = api.post("/api/v1/auth/google", json={"credential": "t"})
    assert resposta.status_code == 200, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['access_token']}"}


def _runner_vale(fabrica: sessionmaker[Session], token: str) -> bool:
    with fabrica() as sessao:
        try:
            AuthService(sessao).get_runner_user(token)
        except UnauthorizedError:
            return False
        return True


# A1: quem cadastrou o e-mail de outra pessoa antes dela perde o acesso quando ela entra.
# Contas de antes da confirmação por código ficam "não confirmadas": é o caso que sobra


def _desconfirmar(fabrica: sessionmaker[Session], email: str) -> None:
    """Deixa a conta como as que existiam antes da confirmação de e-mail."""
    with fabrica() as sessao:
        sessao.scalar(select(User).where(User.email == email)).email_verified_at = None
        sessao.commit()


def test_vincular_google_derruba_quem_cadastrou_o_email_antes(
    api: TestClient,
    criar_conta: Callable[..., Cabecalho],
    fabrica_sessao: sessionmaker[Session],
) -> None:
    intrusa = criar_conta(email=EMAIL)
    token_executor_da_intrusa = token_do_executor(api, intrusa)
    _desconfirmar(fabrica_sessao, EMAIL)

    dona = _entrar_com_google(api)

    assert api.get("/api/v1/auth/me", headers=intrusa).status_code == 401
    assert not _runner_vale(fabrica_sessao, token_executor_da_intrusa)
    # A senha que a intrusa criou foi apagada
    login = api.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "senha-longa-de-teste"}
    )
    assert login.status_code == 401
    # A dona continua dentro, com o token que acabou de receber
    assert api.get("/api/v1/auth/me", headers=dona).status_code == 200


def test_conta_confirmada_que_entra_pelo_google_mantem_a_senha(
    api: TestClient, criar_conta: Callable[..., Cabecalho]
) -> None:
    # Quem confirmou o e-mail por código é a dona do e-mail: o Google só ganha uma porta nova
    criar_conta(email=EMAIL)

    _entrar_com_google(api)

    login = api.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "senha-longa-de-teste"}
    )
    assert login.status_code == 200


# M4: desligar o executor sem trocar a senha


def test_desligar_o_executor_invalida_o_token_e_mantem_o_login(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    token = token_do_executor(api, autenticado)
    assert _runner_vale(fabrica_sessao, token)

    resposta = api.delete("/api/v1/auth/runner-token", headers=autenticado)

    assert resposta.status_code == 204
    assert not _runner_vale(fabrica_sessao, token)
    assert api.get("/api/v1/auth/me", headers=autenticado).status_code == 200
    # Um token novo, tirado depois, volta a ligar
    assert _runner_vale(fabrica_sessao, token_do_executor(api, autenticado))


def test_desligar_o_executor_derruba_o_chrome_conectado(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    relay = ExtensionRelay(0, autenticador(fabrica_sessao), recheck_seconds=0.2)
    relay.start()
    chrome = None
    try:
        chrome = ExtensaoFalsa(relay.port, token_do_executor(api, autenticado))
        dono = id_da_conta(api, autenticado)
        esperar(lambda: relay.connected_users() == [dono])

        assert api.delete("/api/v1/auth/runner-token", headers=autenticado).status_code == 204

        esperar(lambda: relay.connected_users() == [])
        esperar(lambda: chrome.conexao.close_code == 4401)
    finally:
        if chrome is not None:
            chrome.fechar()
        relay.stop()


def test_desligar_o_executor_exige_login(api: TestClient) -> None:
    assert api.delete("/api/v1/auth/runner-token").status_code == 401


# Precisão da revogação: antes, um token do mesmo segundo da troca de senha continuava valendo


def test_token_emitido_no_mesmo_segundo_da_revogacao_nao_vale(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    with fabrica_sessao() as sessao:
        sessao.scalar(select(User)).tokens_valid_after = datetime.now(UTC)
        sessao.commit()

    assert api.get("/api/v1/auth/me", headers=autenticado).status_code == 401


# M10: conta do Google (sem senha) só define senha ou se apaga com login recente


def _token_antigo(api: TestClient, cabecalho: Cabecalho, minutos: int) -> Cabecalho:
    dono = id_da_conta(api, cabecalho)
    emitido = datetime.now(UTC) - timedelta(minutes=minutos)
    token = jwt.encode(
        {
            "sub": str(dono),
            "iat": emitido,
            "iat_ms": int(emitido.timestamp() * 1000),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


def test_token_roubado_e_antigo_nao_define_senha_em_conta_do_google(api: TestClient) -> None:
    antigo = _token_antigo(api, _entrar_com_google(api), minutos=30)

    resposta = api.post(
        "/api/v1/account/password", json={"new_password": "senha-da-intrusa"}, headers=antigo
    )

    assert resposta.status_code == 400
    assert "entre de novo" in resposta.json()["detail"]
    login = api.post("/api/v1/auth/login", json={"email": EMAIL, "password": "senha-da-intrusa"})
    assert login.status_code == 401


def test_token_antigo_nao_apaga_conta_do_google(api: TestClient) -> None:
    antigo = _token_antigo(api, _entrar_com_google(api), minutos=30)

    resposta = api.request(
        "DELETE", "/api/v1/account", json={"confirmation": EMAIL}, headers=antigo
    )

    assert resposta.status_code == 400
    assert api.get("/api/v1/auth/me", headers=antigo).status_code == 200


def test_login_recente_define_a_primeira_senha(api: TestClient) -> None:
    recente = _token_antigo(api, _entrar_com_google(api), minutos=2)

    resposta = api.post(
        "/api/v1/account/password", json={"new_password": "primeira-senha-longa"}, headers=recente
    )

    assert resposta.status_code == 200


@pytest.mark.parametrize("minutos", [11, 60])
def test_conta_com_senha_continua_trocando_com_a_senha_atual(
    api: TestClient, criar_conta: Callable[..., Cabecalho], minutos: int
) -> None:
    # Quem tem senha prova quem é com ela: a idade do token não importa
    antigo = _token_antigo(api, criar_conta(email=f"{uuid.uuid4().hex}@teste.com"), minutos)

    resposta = api.post(
        "/api/v1/account/password",
        json={"current_password": "senha-longa-de-teste", "new_password": "outra-senha-longa"},
        headers=antigo,
    )

    assert resposta.status_code == 200


# A3: o e-mail que a extensão mostra antes de ligar vem do token assinado, não da página


def test_token_do_executor_leva_o_email_da_conta(api: TestClient) -> None:
    dona = _entrar_com_google(api)
    token = token_do_executor(api, dona)

    dados = jwt.decode(token, options={"verify_signature": False})

    assert dados["email"] == EMAIL
    assert dados["scope"] == "runner"


def test_rele_confirma_o_email_ao_ligar(
    api: TestClient, fabrica_sessao: sessionmaker[Session]
) -> None:
    from websockets.sync.client import connect

    relay = ExtensionRelay(0, autenticador(fabrica_sessao))
    relay.start()
    try:
        token = token_do_executor(api, _entrar_com_google(api))
        with connect(
            f"ws://127.0.0.1:{relay.port}/extension", origin="chrome-extension://ditto"
        ) as conexao:
            conexao.send(json.dumps({"type": "hello", "token": token}))
            boas_vindas = json.loads(conexao.recv(timeout=5))
        assert boas_vindas == {"type": "welcome", "email": EMAIL}
    finally:
        relay.stop()
