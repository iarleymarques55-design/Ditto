import json
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
_DEFAULT_RETRY_SECONDS = 2.0
# O worker fica parado durante a espera: um limite maior que isto vira pedido de ajuda
_MAX_RETRY_SECONDS = 20.0


class LlmUnavailableError(Exception):
    """A IA não respondeu ou respondeu fora do formato. Quem chama segue sem ela."""


def _retry_wait(response: httpx.Response) -> float:
    try:
        wait = float(response.headers.get("retry-after", _DEFAULT_RETRY_SECONDS))
    except ValueError:
        wait = _DEFAULT_RETRY_SECONDS
    return min(max(wait, 0), _MAX_RETRY_SECONDS)


class LlmClient:
    """Cliente de uma API compatível com OpenAI. Quem monta o conteúdo é sempre o sanitizador."""

    def _post(self, system: str, user: str) -> httpx.Response:
        return httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"},
            json={
                "model": settings.llm_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=settings.llm_timeout_seconds,
        )

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        if not settings.llm_enabled:
            raise LlmUnavailableError("IA não configurada.")

        try:
            response = self._post(system, user)
            if response.status_code == HTTP_TOO_MANY_REQUESTS:
                # Limite passageiro do plano: vale esperar antes de incomodar uma pessoa
                time.sleep(_retry_wait(response))
                response = self._post(system, user)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except httpx.HTTPStatusError as error:
            # Só o status: o corpo do erro pode trazer parte do conteúdo enviado
            logger.warning("A IA recusou o pedido: HTTP %s", error.response.status_code)
            raise LlmUnavailableError("A IA não respondeu.") from error
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as error:
            # Só o tipo do erro: a mensagem pode trazer cabeçalhos ou parte do conteúdo enviado
            logger.warning("Falha ao consultar a IA: %s", type(error).__name__)
            raise LlmUnavailableError("A IA não respondeu.") from error

        if not isinstance(parsed, dict):
            raise LlmUnavailableError("A IA respondeu fora do formato.")
        return parsed
