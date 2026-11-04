"""Tela de conta: perfil, foto, senha, alertas e exclusão."""

import io
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from playwright.sync_api import Browser
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.credential import Credential
from app.models.flow import Flow
from app.models.user import User
from app.services.worker_tasks import process_next_run
from tests.fixtures.portal import Portal

Cabecalho = dict[str, str]
SENHA = "senha-longa-de-teste"


def imagem(formato: str = "PNG", tamanho: tuple[int, int] = (600, 400), **opcoes: Any) -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", tamanho, (75, 55, 160)).save(saida, format=formato, **opcoes)
    return saida.getvalue()


def enviar_foto(api: TestClient, cabecalho: Cabecalho, conteudo: bytes, nome: str = "foto.png"):
    return api.put("/api/v1/account/avatar", files={"file": (nome, conteudo)}, headers=cabecalho)


def test_editar_nome_e_alertas(api: TestClient, autenticado: Cabecalho) -> None:
    resposta = api.patch(
        "/api/v1/account",
        json={"name": "  Carla Souza ", "email_alerts": False},
        headers=autenticado,
    )
    assert resposta.status_code == 200
    assert resposta.json()["name"] == "Carla Souza"
    assert resposta.json()["email_alerts"] is False

    eu = api.get("/api/v1/auth/me", headers=autenticado).json()
    assert eu["name"] == "Carla Souza"
    assert eu["email_alerts"] is False


@pytest.mark.parametrize(
    "corpo", [{"name": ""}, {"name": "x" * 121}, {"email": "a@b.com"}, {"is_admin": True}]
)
def test_editar_recusa_entrada_invalida(
    corpo: dict, api: TestClient, autenticado: Cabecalho
) -> None:
    assert api.patch("/api/v1/account", json=corpo, headers=autenticado).status_code == 422


def test_nome_so_com_espacos_e_recusado(api: TestClient, autenticado: Cabecalho) -> None:
    assert (
        api.patch("/api/v1/account", json={"name": "   "}, headers=autenticado).status_code == 400
    )


# Foto


@pytest.mark.parametrize(("formato", "opcoes"), [("PNG", {}), ("JPEG", {}), ("WEBP", {})])
def test_foto_e_regravada_quadrada(
    formato: str, opcoes: dict, api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = enviar_foto(api, autenticado, imagem(formato, **opcoes))
    assert resposta.status_code == 200
    assert resposta.json()["avatar_id"]

    foto = api.get("/api/v1/account/avatar", headers=autenticado)
    assert foto.status_code == 200
    assert foto.headers["content-type"] == "image/webp"
    assert Image.open(io.BytesIO(foto.content)).size == (256, 256)


def test_foto_nao_guarda_metadados(api: TestClient, autenticado: Cabecalho) -> None:
    exif = Image.Exif()
    exif[0x010E] = "localizacao-marcada-da-foto"
    enviar_foto(api, autenticado, imagem("JPEG", exif=exif))
    foto = api.get("/api/v1/account/avatar", headers=autenticado)
    assert b"localizacao-marcada-da-foto" not in foto.content


@pytest.mark.parametrize(
    ("nome", "conteudo"),
    [
        ("foto.png", b"isto nao e uma imagem"),
        ("foto.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
        ("foto.html", b"<html><script>alert(1)</script></html>"),
        ("foto.png", b""),
    ],
)
def test_arquivo_que_nao_e_imagem_e_recusado(
    nome: str, conteudo: bytes, api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = enviar_foto(api, autenticado, conteudo, nome)
    assert resposta.status_code == 400
    assert "imagem" in resposta.json()["detail"]


def test_formato_fora_da_lista_e_recusado_mesmo_sendo_imagem(
    api: TestClient, autenticado: Cabecalho
) -> None:
    assert enviar_foto(api, autenticado, imagem("GIF"), "foto.gif").status_code == 400


def test_imagem_com_pixels_demais_e_recusada(api: TestClient, autenticado: Cabecalho) -> None:
    assert enviar_foto(api, autenticado, imagem("PNG", (7000, 7000))).status_code == 400


def test_foto_acima_do_limite(api: TestClient, autenticado: Cabecalho) -> None:
    assert enviar_foto(api, autenticado, b"x" * (3 * 1024 * 1024 + 1)).status_code == 413


def test_trocar_foto_apaga_a_antiga(api: TestClient, autenticado: Cabecalho) -> None:
    primeira = enviar_foto(api, autenticado, imagem()).json()["avatar_id"]
    segunda = enviar_foto(api, autenticado, imagem("JPEG")).json()["avatar_id"]
    assert primeira != segunda
    arquivos = [p.name for p in settings.storage_dir.rglob("foto-*.webp")]
    assert f"foto-{primeira}.webp" not in arquivos
    assert f"foto-{segunda}.webp" in arquivos


def test_remover_foto(api: TestClient, autenticado: Cabecalho) -> None:
    enviar_foto(api, autenticado, imagem())
    resposta = api.delete("/api/v1/account/avatar", headers=autenticado)
    assert resposta.json()["avatar_id"] is None
    assert api.get("/api/v1/account/avatar", headers=autenticado).status_code == 404


def test_foto_e_da_propria_conta(api: TestClient, criar_conta: Callable[..., Cabecalho]) -> None:
    a, b = criar_conta(), criar_conta()
    enviar_foto(api, a, imagem())
    assert api.get("/api/v1/account/avatar", headers=b).status_code == 404


# Senha


def test_trocar_senha_encerra_as_outras_sessoes(
    api: TestClient, criar_conta: Callable[..., Cabecalho]
) -> None:
    sessao_antiga = criar_conta(email="a@teste.com")

    resposta = api.post(
        "/api/v1/account/password",
        json={"current_password": SENHA, "new_password": "senha-nova-bem-longa"},
        headers=sessao_antiga,
    )
    assert resposta.status_code == 200

    # A sessão atual segue com o token novo, e o token antigo morre
    novo = {"Authorization": f"Bearer {resposta.json()['access_token']}"}
    assert api.get("/api/v1/auth/me", headers=novo).status_code == 200

    velho = api.post("/api/v1/auth/login", json={"email": "a@teste.com", "password": SENHA})
    assert velho.status_code == 401
    novo_login = api.post(
        "/api/v1/auth/login", json={"email": "a@teste.com", "password": "senha-nova-bem-longa"}
    )
    assert novo_login.status_code == 200


def test_token_de_antes_da_troca_nao_vale_mais(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    from datetime import UTC, datetime, timedelta

    # Marca a troca no futuro próximo: o token atual foi emitido antes dela
    with fabrica_sessao() as sessao:
        sessao.scalar(select(User)).tokens_valid_after = datetime.now(UTC) + timedelta(minutes=5)
        sessao.commit()
    assert api.get("/api/v1/auth/me", headers=autenticado).status_code == 401


def test_senha_atual_errada_nao_troca_nem_derruba_a_sessao(
    api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = api.post(
        "/api/v1/account/password",
        json={"current_password": "errada", "new_password": "senha-nova-bem-longa"},
        headers=autenticado,
    )
    assert resposta.status_code == 400
    assert api.get("/api/v1/auth/me", headers=autenticado).status_code == 200


def test_senha_atual_ausente_e_recusada_em_conta_com_senha(
    api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = api.post(
        "/api/v1/account/password",
        json={"new_password": "senha-nova-bem-longa"},
        headers=autenticado,
    )
    assert resposta.status_code == 400


@pytest.mark.parametrize("nova", ["curta", "x" * 73])
def test_senha_nova_invalida(nova: str, api: TestClient, autenticado: Cabecalho) -> None:
    resposta = api.post(
        "/api/v1/account/password",
        json={"current_password": SENHA, "new_password": nova},
        headers=autenticado,
    )
    assert resposta.status_code == 422
    assert nova not in resposta.text


def _claims() -> dict[str, Any]:
    return {
        "iss": "accounts.google.com",
        "sub": "google-1",
        "email": "ana@teste.com",
        "email_verified": True,
        "name": "Ana",
    }


def test_conta_do_google_define_a_primeira_senha(api: TestClient) -> None:
    with patch("app.services.auth_service._verify_google_token", return_value=_claims()):
        entrada = api.post("/api/v1/auth/google", json={"credential": "t"}).json()
    assert entrada["user"]["has_password"] is False

    cabecalho = {"Authorization": f"Bearer {entrada['access_token']}"}
    resposta = api.post(
        "/api/v1/account/password", json={"new_password": "primeira-senha-longa"}, headers=cabecalho
    )
    assert resposta.status_code == 200
    assert resposta.json()["user"]["has_password"] is True

    login = api.post(
        "/api/v1/auth/login", json={"email": "ana@teste.com", "password": "primeira-senha-longa"}
    )
    assert login.status_code == 200


# Alertas


def _disparar_com_pedido(
    api: TestClient,
    cabecalho: Cabecalho,
    tarefa: dict[str, Any],
    fabrica: sessionmaker[Session],
    navegador: Browser,
    portal: Portal,
) -> list[str]:
    portal.layout = "captcha"
    api.post(
        "/api/v1/runs",
        data={"flow_id": tarefa["id"]},
        files={"file": ("a.csv", b"loja\nLoja 01 - Shopping Norte\n")},
        headers=cabecalho,
    )
    enviados: list[str] = []
    with patch(
        "app.services.run_processor.send_email", side_effect=lambda to, *_: enviados.append(to)
    ):
        process_next_run(fabrica, navegador)
    return enviados


def test_alerta_por_email_ligado_avisa(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    portal: Portal,
) -> None:
    email = api.get("/api/v1/auth/me", headers=autenticado).json()["email"]
    assert _disparar_com_pedido(
        api, autenticado, tarefa_ativa, fabrica_sessao, navegador, portal
    ) == [email]


def test_alerta_por_email_desligado_nao_avisa(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    portal: Portal,
) -> None:
    api.patch("/api/v1/account", json={"email_alerts": False}, headers=autenticado)
    assert (
        _disparar_com_pedido(api, autenticado, tarefa_ativa, fabrica_sessao, navegador, portal)
        == []
    )
    # O pedido continua no painel
    assert len(api.get("/api/v1/help-requests", headers=autenticado).json()) == 1


# Excluir


def test_excluir_conta_apaga_tudo(
    api: TestClient,
    criar_conta: Callable[..., Cabecalho],
    tarefa_ativa: dict[str, Any],
    autenticado: Cabecalho,
    fabrica_sessao: sessionmaker[Session],
) -> None:
    outra = criar_conta(email="fica@teste.com")
    api.post(
        "/api/v1/credentials",
        json={"domain": "portal.exemplo", "password": "x"},
        headers=autenticado,
    )
    api.post(
        "/api/v1/credentials", json={"domain": "portal.exemplo", "password": "y"}, headers=outra
    )
    enviar_foto(api, autenticado, imagem())
    eu = api.get("/api/v1/auth/me", headers=autenticado).json()
    pasta = settings.storage_dir / eu["id"]
    assert pasta.exists()

    resposta = api.request(
        "DELETE",
        "/api/v1/account",
        json={"confirmation": eu["email"].upper(), "password": SENHA},
        headers=autenticado,
    )
    assert resposta.status_code == 204

    assert api.get("/api/v1/auth/me", headers=autenticado).status_code == 401
    assert not pasta.exists()
    with fabrica_sessao() as sessao:
        assert sessao.scalar(select(User).where(User.email == eu["email"])) is None
        assert sessao.scalars(select(Flow)).all() == []
        # A outra conta não perde nada
        assert len(sessao.scalars(select(Credential)).all()) == 1
    assert api.get("/api/v1/auth/me", headers=outra).status_code == 200


@pytest.mark.parametrize(
    "corpo",
    [
        {"confirmation": "outro@teste.com", "password": SENHA},
        {"confirmation": "{email}", "password": "errada"},
        {"confirmation": "{email}"},
    ],
)
def test_excluir_exige_confirmacao_e_senha(
    corpo: dict, api: TestClient, autenticado: Cabecalho
) -> None:
    email = api.get("/api/v1/auth/me", headers=autenticado).json()["email"]
    corpo = {**corpo, "confirmation": corpo["confirmation"].replace("{email}", email)}
    assert (
        api.request("DELETE", "/api/v1/account", json=corpo, headers=autenticado).status_code == 400
    )
    assert api.get("/api/v1/auth/me", headers=autenticado).status_code == 200


def test_excluir_sem_corpo_e_recusado(api: TestClient, autenticado: Cabecalho) -> None:
    assert api.request("DELETE", "/api/v1/account", headers=autenticado).status_code == 422
