from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    # Sem isso, rodar a migração dentro de um processo desliga os loggers da aplicação
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# A URL vem do .env, nunca do alembic.ini. Os testes passam a do banco de teste por aqui.
database_url = config.attributes.get("database_url") or settings.database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Gera o SQL das migrações sem conectar ao banco."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica as migrações direto no banco."""
    engine = create_engine(database_url, poolclass=pool.NullPool)

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
