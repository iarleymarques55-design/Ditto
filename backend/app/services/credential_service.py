import uuid

from sqlalchemy.orm import Session

from app.core.encryption import encrypt_json
from app.core.exceptions import NotFoundError
from app.models.credential import Credential
from app.repositories.credential_repository import CredentialRepository
from app.schemas.credential import CredentialCreate


class CredentialService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.credentials = CredentialRepository(session)

    def save(self, owner_id: uuid.UUID, payload: CredentialCreate) -> Credential:
        encrypted = encrypt_json({"username": payload.username or "", "password": payload.password})
        credential = self.credentials.get_by_domain(owner_id, payload.domain)
        if credential is None:
            credential = self.credentials.add(
                Credential(owner_id=owner_id, domain=payload.domain, encrypted_payload=encrypted)
            )
        else:
            credential.encrypted_payload = encrypted
        self.session.commit()
        return credential

    def list(self, owner_id: uuid.UUID) -> list[Credential]:
        return self.credentials.list_owned(owner_id)

    def delete(self, credential_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        credential = self.credentials.get_owned(credential_id, owner_id)
        if credential is None:
            raise NotFoundError("Este acesso não foi encontrado.")
        self.credentials.delete(credential)
        self.session.commit()
