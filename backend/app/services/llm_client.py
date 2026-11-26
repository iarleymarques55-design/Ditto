import json
import logging
import re
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
_DEFAULT_RETRY_SECONDS = 2.0
# O worker fica parado durante a espera: um limite maior que isto vira pedido de ajuda
_MAX_RETRY_SECONDS = 20.0
# O limite por minuto do plano gratuito costuma voltar em segundos: vale tentar mais de uma vez,
# mas sem prender o worker por mais que isto somando todas as esperas
_MAX_ATTEMPTS = 3
_MAX_TOTAL_WAIT_SECONDS = 30.0
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}


class LlmUnavailableError(Exception):
    """A IA não respondeu ou respondeu fora do formato. Quem chama segue sem ela."""


def _error_kind(response: httpx.Response) -> str:
    """O tipo e o código do erro que a IA devolveu ("invalid_request_error / model_not_found").
    A mensagem fica de fora: ela pode repetir parte do conteúdo da página que foi enviado."""
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        return "sem detalhes"
    if not isinstance(error, dict):
        return "sem detalhes"
    kind = " / ".join(str(error[key]) for key in ("type", "code") if error.get(key))
    return kind[:120] or "sem detalhes"


def _duration_seconds(text: str) -> float | None:
    """ "7.66s", "1m2.5s", "120ms": o formato do Groq para quando o limite volta."""
    parts = _DURATION_PART.findall(text.strip())
    if not parts or "".join(number + unit for number, unit in parts) != text.strip():
        return None
    return sum(float(number) * _UNIT_SECONDS[unit] for number, unit in parts)


def _retry_wait(response: httpx.Response) -> float:
    """Quanto o próprio serviço manda esperar: "retry-after" ou, no Groq, quando o limite de
    tokens (ou de pedidos) volta."""
    wait: float | None = None
    try:
        wait = float(response.headers["retry-after"])
    except (KeyError, ValueError):
        resets = [
            _duration_seconds(response.headers.get(name, ""))
            for name in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests")
        ]
        known = [reset for reset in resets if reset is not None]
        wait = max(known) if known else None
    if wait is None:
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
                "max_tokens": settings.llm_max_output_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=settings.llm_timeout_seconds,
        )

    def _post_within_rate_limit(self, system: str, user: str) -> httpx.Response:
        """Limite passageiro do plano (429): espera o que o serviço pedir e tenta de novo, antes
        de incomodar uma pessoa."""
        waited = 0.0
        response = self._post(system, user)
        for _ in range(_MAX_ATTEMPTS - 1):
            if response.status_code != HTTP_TOO_MANY_REQUESTS:
                break
            wait = min(_retry_wait(response), _MAX_TOTAL_WAIT_SECONDS - waited)
            if wait <= 0:
                break
            logger.info("A IA pediu para esperar %.1fs (limite do plano). Tentando de novo.", wait)
            time.sleep(wait)
            waited += wait
            response = self._post(system, user)
        return response

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        if not settings.llm_enabled:
            # Aviso no log: sem isto, o painel dizia "a IA não respondeu" e o log ficava vazio
            logger.warning("IA não configurada neste serviço: preencha LLM_API_KEY e LLM_MODEL.")
            raise LlmUnavailableError("IA não configurada.")

        try:
            response = self._post_within_rate_limit(system, user)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except httpx.HTTPStatusError as error:
            # 401: chave errada. 404 ou "model_not_found": LLM_MODEL errado. 413 ou
            # "context_length_exceeded": página grande demais. 429: limite do plano
            logger.warning(
                "A IA recusou o pedido: HTTP %s (%s)",
                error.response.status_code,
                _error_kind(error.response),
            )
            raise LlmUnavailableError("A IA não respondeu.") from error
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as error:
            # Só o tipo do erro: a mensagem pode trazer cabeçalhos ou parte do conteúdo enviado
            logger.warning("Falha ao consultar a IA: %s", type(error).__name__)
            raise LlmUnavailableError("A IA não respondeu.") from error

        if not isinstance(parsed, dict):
            raise LlmUnavailableError("A IA respondeu fora do formato.")
        return parsed
