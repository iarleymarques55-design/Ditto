from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.controllers.account_controller import router as account_router
from app.controllers.ai_draft_controller import router as ai_draft_router
from app.controllers.auth_controller import router as auth_router
from app.controllers.credential_controller import router as credential_router
from app.controllers.dashboard_controller import router as dashboard_router
from app.controllers.flow_controller import router as flow_router
from app.controllers.health_controller import router as health_router
from app.controllers.repair_controller import router as repair_router
from app.controllers.run_controller import router as run_router
from app.controllers.schedule_controller import router as schedule_router
from app.core.config import Settings, settings
from app.core.exceptions import register_exception_handlers

API_PREFIX = "/api/v1"

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
# Só em produção, que roda em HTTPS: o navegador passa a recusar a versão sem cadeado
_HSTS = "max-age=31536000; includeSubDomains"
_TOO_LARGE = {"detail": "O envio passa do tamanho permitido.", "code": "PAYLOAD_TOO_LARGE"}


class BodySizeLimit:
    """Corta o pedido assim que o corpo passa do limite, mesmo sem Content-Length.

    Conferir só o cabeçalho deixava passar envios em partes (Transfer-Encoding: chunked), que
    eram lidos inteiros na memória antes de qualquer validação.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await JSONResponse(status_code=413, content=_TOO_LARGE)(scope, receive, send)
            return

        received = 0
        started = False
        cut = False

        async def limited_receive() -> Message:
            nonlocal received, cut
            if cut:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # O FastAPI transforma qualquer erro na leitura do corpo em "400". Por isso a
                    # resposta 413 sai daqui mesmo, e a rota recebe "cliente desconectou"
                    cut = True
                    if not started:
                        await _send_too_large(send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if cut:
                # Já respondemos 413: o que a rota tentar mandar depois é descartado
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not cut:
                raise


async def _send_too_large(send: Send) -> None:
    response = JSONResponse(status_code=413, content=_TOO_LARGE)
    await send({"type": "http.response.start", "status": 413, "headers": response.raw_headers})
    await send({"type": "http.response.body", "body": response.body})


_OPENAPI_TAGS = [
    {"name": "Saúde", "description": "Verifica se a API e o banco respondem."},
    {"name": "Autenticação", "description": "Criar conta, entrar e ver a conta logada."},
    {"name": "Conta", "description": "Perfil, foto, senha, alertas e exclusão da conta."},
    {"name": "Mesa", "description": "O resumo do dia, mostrado na primeira tela do painel."},
    {"name": "Tarefas", "description": "Gravações, passos, variáveis e ativação."},
    {"name": "Execuções", "description": "Disparar, acompanhar e baixar o resultado das cópias."},
    {"name": "Reparos", "description": "Caminhos que mudaram e decisões que esperam uma pessoa."},
    {
        "name": "Criar com IA",
        "description": "Escreva o que a tarefa faz e a IA monta os passos no seu Chrome.",
    },
    {"name": "Acessos", "description": "Senhas dos portais, guardadas com criptografia."},
    {"name": "Agendas", "description": "Tarefas que rodam sozinhas no horário certo."},
]


def create_app(app_settings: Settings = settings) -> FastAPI:
    # A documentação só fica aberta em desenvolvimento
    is_development = app_settings.environment == "development"

    app = FastAPI(
        title="Ditto API",
        description="API do Ditto: grave uma tarefa do navegador uma vez e deixe o Ditto repetir.",
        version="1.0.0",
        openapi_tags=_OPENAPI_TAGS,
        docs_url="/docs" if is_development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if is_development else None,
    )

    @app.middleware("http")
    async def protect_responses(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        # Respostas da API trazem dados da conta: nada de ficar guardado em cache do navegador
        # ou de um proxy no caminho
        response.headers.setdefault("Cache-Control", "no-store")
        if not is_development:
            response.headers["Strict-Transport-Security"] = _HSTS
        return response

    # Por fora de tudo: corta o envio grande antes de qualquer leitura do corpo
    app.add_middleware(BodySizeLimit, max_bytes=app_settings.max_body_bytes)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    register_exception_handlers(app)
    for router in (
        health_router,
        auth_router,
        account_router,
        dashboard_router,
        flow_router,
        ai_draft_router,
        run_router,
        repair_router,
        credential_router,
        schedule_router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    return app


app = create_app()
