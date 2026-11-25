import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_verification import EmailVerification


class EmailVerificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user(self, user_id: uuid.UUID) -> EmailVerification | None:
        return self.session.scalar(
            select(EmailVerification).where(EmailVerification.user_id == user_id)
        )

    def add(self, verification: EmailVerification) -> EmailVerification:
        self.session.add(verification)
        return verification

    def delete(self, verification: EmailVerification) -> None:
        self.session.delete(verification)
