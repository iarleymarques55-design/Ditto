import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.credential import Credential


class CredentialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, credential: Credential) -> Credential:
        self.session.add(credential)
        return credential

    def get_owned(self, credential_id: uuid.UUID, owner_id: uuid.UUID) -> Credential | None:
        return self.session.scalar(
            select(Credential).where(
                Credential.id == credential_id, Credential.owner_id == owner_id
            )
        )

    def get_by_domain(self, owner_id: uuid.UUID, domain: str) -> Credential | None:
        return self.session.scalar(
            select(Credential).where(Credential.owner_id == owner_id, Credential.domain == domain)
        )

    def list_owned(self, owner_id: uuid.UUID) -> list[Credential]:
        return list(
            self.session.scalars(
                select(Credential)
                .where(Credential.owner_id == owner_id)
                .order_by(Credential.domain)
            )
        )

    def list_for_domains(self, owner_id: uuid.UUID, domains: list[str]) -> list[Credential]:
        return list(
            self.session.scalars(
                select(Credential).where(
                    Credential.owner_id == owner_id, Credential.domain.in_(domains)
                )
            )
        )

    def delete(self, credential: Credential) -> None:
        self.session.delete(credential)
