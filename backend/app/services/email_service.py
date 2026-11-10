import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT_SECONDS = 10


def send_email(to: str, subject: str, text: str) -> bool:
    """Um e-mail que falha nunca interrompe uma execução: o aviso continua no painel."""
    if (
        not settings.brevo_api_key
        or not settings.brevo_api_key.get_secret_value()
        or not settings.email_from
    ):
        logger.info("E-mail não enviado: Brevo não configurado.")
        return False

    try:
        response = httpx.post(
            _BREVO_URL,
            headers={"api-key": settings.brevo_api_key.get_secret_value()},
            json={
                "sender": {"email": settings.email_from, "name": "Ditto"},
                "to": [{"email": to}],
                "subject": subject,
                "textContent": text,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("Falha ao enviar e-mail: %s", type(error).__name__)
        return False
    return True
