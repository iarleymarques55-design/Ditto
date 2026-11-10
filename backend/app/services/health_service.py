import logging

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.core.exceptions import DatabaseUnavailableError
from app.repositories.health_repository import HealthRepository

logger = logging.getLogger(__name__)


class HealthService:
    def __init__(self, repository: HealthRepository) -> None:
        self.repository = repository

    def check_database(self) -> None:
        try:
            self.repository.ping()
        except SQLAlchemyError as error:
            # Só o motivo do driver vai para o log; a URL de conexão não aparece
            motivo = error.orig if isinstance(error, DBAPIError) else type(error).__name__
            logger.error("Falha ao conectar ao banco: %s", motivo)
            raise DatabaseUnavailableError from error
