from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url.get_secret_value(),
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Abre uma sessão por requisição e fecha ao terminar."""
    with SessionLocal() as session:
        yield session
