"""Confirmação de e-mail por código de 6 dígitos.

Sem isso, qualquer pessoa criava uma conta com o e-mail de outra. O código vai pelo Brevo, vale
15 minutos e aceita 5 tentativas. Só o resumo dele fica no banco.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EmailNotSentError, InvalidVerificationCodeError
from app.models.email_verification import EmailVerification
from app.models.user import User
from app.repositories.email_verification_repository import EmailVerificationRepository
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

CODE_LIFETIME = timedelta(minutes=15)
MAX_ATTEMPTS = 5
# Reenvio: um e-mail por minuto e no máximo 5 por hora para a mesma conta
RESEND_INTERVAL = timedelta(seconds=60)
SEND_WINDOW = timedelta(hours=1)
MAX_SENDS_PER_WINDOW = 5


@dataclass(frozen=True)
class SendResult:
    sent: bool
    # Motivo de não ter enviado: "too_soon" ou "too_many". O controller não revela isso a quem
    # pede reenvio sem estar logado, para não confirmar quais e-mails têm conta
    reason: str | None = None


def _hash(user: User, code: str) -> str:
    # HMAC com o segredo do servidor e o id da conta: o mesmo código em duas contas gera
    # resumos diferentes, e sem o segredo não dá para testar os 1 milhão de códigos offline
    key = settings.jwt_secret.get_secret_value().encode()
    return hmac.new(key, f"{user.id}:{code}".encode(), hashlib.sha256).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _message(code: str) -> tuple[str, str]:
    minutes = int(CODE_LIFETIME.total_seconds() // 60)
    subject = f"Seu código do Ditto: {code}"
    text = (
        f"Seu código para confirmar o e-mail no Ditto é {code}.\n\n"
        f"Ele vale por {minutes} minutos. Digite-o na tela em que você criou a conta.\n\n"
        "Se não foi você que criou uma conta no Ditto, ignore este e-mail: sem o código, "
        "ninguém entra com o seu endereço."
    )
    return subject, text


def deliver_code(user: User, code: str) -> bool:
    """Manda o código. Em desenvolvimento, sem Brevo funcionando, o código vai para o log."""
    subject, text = _message(code)
    if send_email(user.email, subject, text):
        return True
    if settings.environment == "development":
        # Só no computador de quem desenvolve: o Brevo pode recusar o IP de casa
        logger.warning("Código de confirmação de %s (só em desenvolvimento): %s", user.email, code)
        return True
    return False


class EmailVerificationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.verifications = EmailVerificationRepository(session)

    def send_code(self, user: User, *, now: datetime | None = None) -> SendResult:
        """Gera um código novo e manda por e-mail, respeitando o limite de envios.

        Não faz commit: quem chama decide (no cadastro, a conta só é gravada se o e-mail sair).
        Se o envio falhar, levanta EmailNotSentError.
        """
        now = now or datetime.now(UTC)
        current = self.verifications.get_for_user(user.id)

        if current is not None:
            if now - current.sent_at < RESEND_INTERVAL:
                return SendResult(sent=False, reason="too_soon")
            if now - current.window_started_at >= SEND_WINDOW:
                current.window_started_at = now
                current.sends_in_window = 0
            if current.sends_in_window >= MAX_SENDS_PER_WINDOW:
                return SendResult(sent=False, reason="too_many")

        code = _new_code()
        if current is None:
            current = self.verifications.add(
                EmailVerification(
                    user_id=user.id,
                    code_hash=_hash(user, code),
                    expires_at=now + CODE_LIFETIME,
                    attempts=0,
                    sent_at=now,
                    window_started_at=now,
                    sends_in_window=1,
                )
            )
        else:
            # Código novo derruba o antigo e zera as tentativas
            current.code_hash = _hash(user, code)
            current.expires_at = now + CODE_LIFETIME
            current.attempts = 0
            current.sent_at = now
            current.sends_in_window += 1
        self.session.flush()

        if not deliver_code(user, code):
            raise EmailNotSentError
        return SendResult(sent=True)

    def confirm(self, user: User | None, code: str, *, now: datetime | None = None) -> User:
        """Confere o código e marca o e-mail como confirmado. Faz commit nos dois casos: uma
        tentativa errada precisa ficar contada mesmo que a resposta seja um erro."""
        now = now or datetime.now(UTC)
        current = self.verifications.get_for_user(user.id) if user is not None else None
        # Conta inexistente, já confirmada ou sem código pendente: a mesma resposta de código
        # errado, para ninguém descobrir quais e-mails têm conta
        if user is None or user.email_verified or current is None:
            raise InvalidVerificationCodeError

        if now >= current.expires_at:
            self.verifications.delete(current)
            self.session.commit()
            raise InvalidVerificationCodeError("O código venceu. Peça um novo código.")

        if not hmac.compare_digest(current.code_hash, _hash(user, code)):
            current.attempts += 1
            left = MAX_ATTEMPTS - current.attempts
            if left <= 0:
                self.verifications.delete(current)
                self.session.commit()
                raise InvalidVerificationCodeError(
                    "Código errado muitas vezes. Peça um novo código."
                )
            self.session.commit()
            plural = "tentativa" if left == 1 else "tentativas"
            raise InvalidVerificationCodeError(f"Código incorreto. Restam {left} {plural}.")

        user.email_verified_at = now
        self.verifications.delete(current)
        self.session.commit()
        return user
