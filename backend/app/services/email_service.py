import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT_SECONDS = 10
_MAX_REASON_CHARS = 300


def _brevo_reason(response: httpx.Response) -> str:
    """O motivo que o Brevo deu para recusar ("unauthorized: Unrecognised IP address ...").
    Só a resposta dele: a chave e o texto do e-mail (que pode ter o código) nunca vão para o log."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:_MAX_REASON_CHARS]
    if isinstance(body, dict):
        return f"{body.get('code', '')}: {body.get('message', '')}"[:_MAX_REASON_CHARS]
    return str(body)[:_MAX_REASON_CHARS]


def send_email(to: str, subject: str, text: str) -> bool:
    """Um e-mail que falha nunca interrompe uma execução: o aviso continua no painel."""
    if (
        not settings.brevo_api_key
        or not settings.brevo_api_key.get_secret_value()
        or not settings.email_from
    ):
        # Aviso, e não informação: com a confirmação de e-mail, sem Brevo ninguém cria conta
        logger.warning("E-mail não enviado: preencha BREVO_API_KEY e EMAIL_FROM neste serviço.")
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
    except httpx.HTTPStatusError as error:
        # 401 com "Unrecognised IP address": o Brevo bloqueia IPs fora da lista autorizada.
        # 400 com "sender": o EMAIL_FROM não é um remetente verificado no Brevo
        logger.warning(
            "O Brevo recusou o e-mail (HTTP %s) %s",
            error.response.status_code,
            _brevo_reason(error.response),
        )
        return False
    except httpx.HTTPError as error:
        logger.warning("Não consegui falar com o Brevo: %s", type(error).__name__)
        return False
    return True
