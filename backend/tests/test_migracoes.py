"""As migrações sobem e descem sem erro, e o banco fica igual aos models."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from alembic import command
from app.core.config import BACKEND_DIR
from app.models import Base


def _config(engine: Engine) -> Config:
    config = Config(str(Path(BACKEND_DIR) / "alembic.ini"))
    config.set_main_option("script_location", str(Path(BACKEND_DIR) / "alembic"))
    config.attributes["database_url"] = engine.url.render_as_string(hide_password=False)
    return config


def test_ultima_migracao_desce_e_sobe_de_novo(engine_de_teste: Engine) -> None:
    config = _config(engine_de_teste)
    try:
        command.downgrade(config, "-1")
        colunas = {coluna["name"] for coluna in inspect(engine_de_teste).get_columns("users")}
        assert "runner_tokens_valid_after" not in colunas
    finally:
        # Os outros testes dependem do banco na última versão
        command.upgrade(config, "head")

    colunas = {coluna["name"] for coluna in inspect(engine_de_teste).get_columns("users")}
    assert "runner_tokens_valid_after" in colunas


def test_banco_igual_aos_models(engine_de_teste: Engine) -> None:
    with engine_de_teste.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    assert diferencas == []
