import os
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Precisa vir antes de importar o app: os testes nunca usam o banco de produção nem chaves reais
os.environ["DATABASE_URL"] = "postgresql+psycopg://teste:senha-de-teste@localhost:1/teste"
os.environ["ENVIRONMENT"] = "development"
os.environ["CORS_ORIGINS"] = '["http://localhost:5173"]'
os.environ["JWT_SECRET"] = "segredo-de-teste-com-mais-de-32-caracteres-aqui"
os.environ["FERNET_KEYS"] = "x8Yp8oCjC8zQ1m1cFvZ7Jq3r0m6l5n9g2w4t7u0a1b8="
os.environ["GOOGLE_CLIENT_ID"] = "cliente-de-teste"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""
os.environ["BREVO_API_KEY"] = ""
os.environ["ALLOW_PRIVATE_NETWORKS"] = "true"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="ditto-testes-")
os.environ["STEP_TIMEOUT_MS"] = "3000"
os.environ["POSTCONDITION_TIMEOUT_MS"] = "1200"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from playwright.sync_api import Browser, Playwright, sync_playwright  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import BACKEND_DIR, settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.rate_limit import rate_limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.flow import Flow  # noqa: E402
from app.services.analyzer import analyze_flow  # noqa: E402
from app.services.engine.browser import launch_browser  # noqa: E402
from tests.fixtures.portal import Portal  # noqa: E402


@pytest.fixture
def session() -> MagicMock:
    """Sessão falsa do banco; cada teste decide como ela responde."""
    return MagicMock()


@pytest.fixture
def client(session: MagicMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: session
    # Em vez de relançar erros inesperados, devolve a resposta 500 que o cliente real veria
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _limpar_limites() -> None:
    rate_limiter.reset()


@pytest.fixture(scope="session")
def engine_de_teste() -> Iterator[Engine]:
    """Banco de teste de verdade, criado pelas próprias migrações."""
    if settings.test_database_url is None:
        pytest.skip("Defina TEST_DATABASE_URL no .env para rodar os testes com banco.")

    url = settings.test_database_url.get_secret_value()
    # Trava de segurança: estes testes apagam tudo no banco que recebem
    assert "test" in url.rsplit("/", 1)[-1], (
        "TEST_DATABASE_URL precisa apontar para um banco de teste"
    )

    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.begin() as conexao:
        Base.metadata.drop_all(conexao)
        conexao.execute(text("DROP TABLE IF EXISTS alembic_version"))

    config = Config(str(Path(BACKEND_DIR) / "alembic.ini"))
    config.set_main_option("script_location", str(Path(BACKEND_DIR) / "alembic"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def fabrica_sessao(engine_de_teste: Engine) -> Iterator[sessionmaker[Session]]:
    fabrica = sessionmaker(bind=engine_de_teste, autoflush=False, expire_on_commit=False)
    yield fabrica
    with engine_de_teste.begin() as conexao:
        tabelas = ", ".join(f'"{tabela.name}"' for tabela in Base.metadata.sorted_tables)
        conexao.execute(text(f"TRUNCATE {tabelas} CASCADE"))


@pytest.fixture
def api(fabrica_sessao: sessionmaker[Session]) -> Iterator[TestClient]:
    def sessao_de_teste() -> Iterator[Session]:
        with fabrica_sessao() as sessao:
            yield sessao

    app.dependency_overrides[get_db] = sessao_de_teste
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def criar_conta(api: TestClient) -> Callable[..., dict[str, str]]:
    """Cria uma conta e devolve o cabeçalho de autenticação dela."""
    contador = {"n": 0}

    def criar(email: str | None = None, senha: str = "senha-longa-de-teste") -> dict[str, str]:
        contador["n"] += 1
        resposta = api.post(
            "/api/v1/auth/register",
            json={
                "name": "Pessoa de Teste",
                "email": email or f"pessoa{contador['n']}@teste.com",
                "password": senha,
            },
        )
        assert resposta.status_code == 201, resposta.text
        return {"Authorization": f"Bearer {resposta.json()['access_token']}"}

    return criar


@pytest.fixture
def autenticado(criar_conta: Callable[..., dict[str, str]]) -> dict[str, str]:
    return criar_conta()


@pytest.fixture(scope="session")
def _portal_compartilhado() -> Iterator[Portal]:
    portal = Portal()
    portal.start()
    yield portal
    portal.stop()


@pytest.fixture
def portal(_portal_compartilhado: Portal) -> Iterator[Portal]:
    _portal_compartilhado.reset()
    yield _portal_compartilhado
    # Requisições do teste que acabou podem ainda estar a caminho: não podem contar no próximo
    time.sleep(0.15)


@pytest.fixture(scope="session")
def playwright_teste() -> Iterator[Playwright]:
    # O Playwright só pode ser iniciado uma vez por processo
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def navegador(playwright_teste: Playwright) -> Iterator[Browser]:
    browser = launch_browser(playwright_teste)
    yield browser
    browser.close()


def alvo_exportar() -> dict[str, Any]:
    return {
        "role": "button",
        "tag": "a",
        "text": "Exportar PDF",
        "css": "#exportar",
        "neighbors": ["Imprimir", "Excel"],
    }


def gravacao_relatorio(url_portal: str, **extras: Any) -> dict[str, Any]:
    """A mesma tarefa do exemplo do README: escolher loja, informar mês, exportar PDF."""
    return {
        "name": "Relatório mensal por loja",
        "start_url": f"{url_portal}/relatorios",
        "steps": [
            {"action": "navigate", "url": f"{url_portal}/relatorios"},
            {
                "action": "select",
                "value": "Loja 01 - Shopping Norte",
                "target": {
                    "role": "combobox",
                    "tag": "select",
                    "label": "Loja",
                    "name": "loja",
                    "css": "#loja",
                },
            },
            {
                "action": "fill",
                "value": "09/2026",
                "target": {
                    "role": "textbox",
                    "tag": "input",
                    "label": "Mês",
                    "name": "mes",
                    "css": "#mes",
                    "input_type": "text",
                },
            },
            {"action": "click", "target": alvo_exportar(), "downloaded_extension": "pdf"},
        ],
        **extras,
    }


@pytest.fixture
def tarefa_ativa(
    api: TestClient,
    autenticado: dict[str, str],
    fabrica_sessao: sessionmaker[Session],
    portal: Portal,
) -> dict[str, Any]:
    """Uma tarefa já analisada e ativa, com loja vinda da planilha e mês fixo."""
    resposta = api.post("/api/v1/flows", json=gravacao_relatorio(portal.url), headers=autenticado)
    assert resposta.status_code == 201, resposta.text
    flow_id = resposta.json()["id"]

    with fabrica_sessao() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id))

    detalhe = api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).json()
    for variavel in detalhe["variables"]:
        corpo = {"is_variable": variavel["name"] == "loja", "source": "column"}
        api.post(
            f"/api/v1/flows/{flow_id}/variables/{variavel['id']}/answer",
            json=corpo,
            headers=autenticado,
        )

    ativada = api.post(f"/api/v1/flows/{flow_id}/confirm", headers=autenticado)
    assert ativada.status_code == 200, ativada.text
    return ativada.json()
