from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ping(self) -> None:
        """Faz a consulta mais simples possível; lança SQLAlchemyError se o banco não responder."""
        self.session.execute(text("SELECT 1"))
