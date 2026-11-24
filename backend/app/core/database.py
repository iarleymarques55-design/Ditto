from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# No worker, cada linha de trabalho (até WORKER_MAX_ACCOUNTS) usa uma conexão por vez e o aviso
# de vida dela usa outra por um instante; a API usa uma por requisição. O passo do navegador não
# segura conexão (run_processor devolve a dela antes de cada passo). 10 fixas + 20 de folga
# cabem duas vezes (API e worker) nas 100 conexões padrão do Postgres
engine = create_engine(
    settings.database_url.get_secret_value(),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    # Conexões antigas são trocadas antes que um proxy ou o servidor as derrube calado
    pool_recycle=1800,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Abre uma sessão por requisição e fecha ao terminar."""
    with SessionLocal() as session:
        yield session
