from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def test_api_responde_ok(client: TestClient) -> None:
    resposta = client.get("/api/v1/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_api_responde_sem_consultar_o_banco(client: TestClient, session: MagicMock) -> None:
    client.get("/api/v1/health")

    session.execute.assert_not_called()


def test_banco_conectado(client: TestClient, session: MagicMock) -> None:
    resposta = client.get("/api/v1/health/db")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "database": "connected"}
    session.execute.assert_called_once()


def test_banco_fora_do_ar_responde_503(client: TestClient, session: MagicMock) -> None:
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("conexão recusada"))

    resposta = client.get("/api/v1/health/db")

    assert resposta.status_code == 503
    assert resposta.json() == {
        "detail": "Banco de dados indisponível.",
        "code": "DATABASE_UNAVAILABLE",
    }


def test_rota_inexistente_usa_o_formato_de_erro(client: TestClient) -> None:
    resposta = client.get("/api/v1/nao-existe")

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Not Found", "code": "HTTP_404"}


def test_swagger_documenta_os_endpoints(client: TestClient) -> None:
    documento = client.get("/openapi.json").json()

    assert documento["info"]["title"] == "Ditto API"
    for caminho in ("/api/v1/health", "/api/v1/health/db"):
        operacao = documento["paths"][caminho]["get"]
        assert operacao["summary"]
        assert operacao["description"]
        assert operacao["tags"] == ["Saúde"]
    assert "503" in documento["paths"]["/api/v1/health/db"]["get"]["responses"]
