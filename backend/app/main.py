from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.controllers.account_controller import router as account_router
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

_OPENAPI_TAGS = [
    {"name": "Saúde", "description": "Verifica se a API e o banco respondem."},
    {"name": "Autenticação", "description": "Criar conta, entrar e ver a conta logada."},
    {"name": "Conta", "description": "Perfil, foto, senha, alertas e exclusão da conta."},
    {"name": "Mesa", "description": "O resumo do dia, mostrado na primeira tela do painel."},
    {"name": "Tarefas", "description": "Gravações, passos, variáveis e ativação."},
    {"name": "Execuções", "description": "Disparar, acompanhar e baixar o resultado das cópias."},
    {"name": "Reparos", "description": "Caminhos que mudaram e decisões que esperam uma pessoa."},
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
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > app_settings.max_body_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": "O envio passa do tamanho permitido.",
                    "code": "PAYLOAD_TOO_LARGE",
                },
            )
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response

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
        run_router,
        repair_router,
        credential_router,
        schedule_router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    return app


app = create_app()
