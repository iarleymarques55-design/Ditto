import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings, settings
from app.main import create_app

SEGREDO = "senha-super-secreta"


def test_erro_do_banco_nao_vaza_para_o_cliente(client: TestClient, session: MagicMock) -> None:
    session.execute.side_effect = OperationalError(
        "SELECT 1", {}, Exception(f"falha em postgresql://postgres:{SEGREDO}@servidor-interno")
    )

    resposta = client.get("/api/v1/health/db")

    assert resposta.status_code == 503
    assert SEGREDO not in resposta.text
    assert "servidor-interno" not in resposta.text


def test_erro_inesperado_nao_devolve_stack_trace(client: TestClient, session: MagicMock) -> None:
    session.execute.side_effect = RuntimeError(f"detalhe interno {SEGREDO}")

    resposta = client.get("/api/v1/health/db")

    assert resposta.status_code == 500
    assert resposta.json() == {"detail": "Erro interno do servidor.", "code": "INTERNAL_ERROR"}
    assert SEGREDO not in resposta.text
    assert "Traceback" not in resposta.text


def test_log_de_falha_nao_contem_a_url_de_conexao(
    client: TestClient, session: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("conexão recusada"))

    with caplog.at_level(logging.ERROR):
        client.get("/api/v1/health/db")

    assert "conexão recusada" in caplog.text
    assert settings.database_url.get_secret_value() not in caplog.text


def test_url_do_banco_nao_aparece_ao_imprimir_a_configuracao() -> None:
    assert "senha-de-teste" not in repr(settings)
    assert "senha-de-teste" not in str(settings.database_url)


def test_api_nao_inicia_sem_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_recusa_origem_desconhecida(client: TestClient) -> None:
    resposta = client.get("/api/v1/health", headers={"Origin": "https://site-malicioso.example"})

    assert "access-control-allow-origin" not in resposta.headers


def test_cors_aceita_o_frontend(client: TestClient) -> None:
    resposta = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})

    assert resposta.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_documentacao_desligada_em_producao() -> None:
    producao = settings.model_copy(update={"environment": "production"})
    cliente = TestClient(create_app(producao))

    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/redoc").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404


@pytest.mark.parametrize("carga", ["' OR 1=1 --", "'; DROP TABLE users; --", "../../etc/passwd"])
def test_tentativa_de_injecao_na_url_nao_quebra(client: TestClient, carga: str) -> None:
    resposta = client.get(f"/api/v1/health/{carga}", params={"q": carga})

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "HTTP_404"
