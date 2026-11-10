import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Erro de regra de negócio. Os services lançam; o handler converte em HTTP."""

    status_code = 400
    code = "DOMAIN_ERROR"
    detail = "Não foi possível concluir a operação."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.detail
        super().__init__(self.detail)


class BusinessRuleError(DomainError):
    code = "BUSINESS_RULE_ERROR"


class UnauthorizedError(DomainError):
    status_code = 401
    code = "UNAUTHORIZED"
    detail = "Entre na sua conta para continuar."


class InvalidCredentialsError(DomainError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    detail = "E-mail ou senha incorretos."


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"
    detail = "Recurso não encontrado."


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"
    detail = "O recurso entra em conflito com um já existente."


class PayloadTooLargeError(DomainError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"
    detail = "O envio passa do tamanho permitido."


class RateLimitedError(DomainError):
    status_code = 429
    code = "RATE_LIMITED"
    detail = "Muitas tentativas. Espere um pouco e tente de novo."


class ServiceNotConfiguredError(DomainError):
    status_code = 503
    code = "SERVICE_NOT_CONFIGURED"
    detail = "Este serviço não está configurado no servidor."


class DatabaseUnavailableError(DomainError):
    status_code = 503
    code = "DATABASE_UNAVAILABLE"
    detail = "Banco de dados indisponível."


def _error_response(status_code: int, detail: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code})


async def _handle_domain_error(_: Request, error: DomainError) -> JSONResponse:
    return _error_response(error.status_code, error.detail, error.code)


async def _handle_http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
    return _error_response(error.status_code, str(error.detail), f"HTTP_{error.status_code}")


async def _handle_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    # Só o campo e o motivo: a resposta padrão devolveria o valor enviado, inclusive senhas
    problems = [
        f"{'.'.join(str(part) for part in item['loc'] if part != 'body')}: {item['msg']}"
        for item in error.errors()
    ]
    return _error_response(422, "; ".join(problems[:5]) or "Dados inválidos.", "VALIDATION_ERROR")


async def _handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    # O detalhe fica só no log: o cliente nunca recebe stack trace nem mensagem do banco
    logger.error("Erro inesperado em %s", request.url.path, exc_info=error)
    return _error_response(500, "Erro interno do servidor.", "INTERNAL_ERROR")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
