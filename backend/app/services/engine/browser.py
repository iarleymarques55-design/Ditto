"""Navegador do worker. Abre sites a pedido do usuário, então é o ponto mais exposto do sistema."""

from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Dialog, Playwright, Request, Route
from playwright.sync_api import Error as PlaywrightError

from app.core.config import settings
from app.services.engine.egress_proxy import EgressProxy
from app.services.engine.safety import looks_irreversible

_ALLOWED_SCHEMES = {"http", "https"}


def host_matches(host: str, allowed_domains: list[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def is_request_allowed(url: str, *, is_navigation: bool, allowed_domains: list[str]) -> bool:
    """Navegação só nos domínios da tarefa. A rede interna é barrada pelo proxy de saída."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()

    if parts.scheme not in _ALLOWED_SCHEMES or not host:
        return False
    return not is_navigation or host_matches(host, allowed_domains)


def _is_top_level_navigation(request: Request) -> bool:
    if not request.is_navigation_request():
        return False
    try:
        return request.frame.parent_frame is None
    except PlaywrightError:
        # Janela nova: o frame ainda não existe, e abrir uma janela é uma navegação de verdade
        return True


def _answer_dialog(dialog: Dialog) -> None:
    """Sem resposta, o navegador recusaria tudo e o passo travaria. Avisos e confirmações comuns
    seguem; uma confirmação que parece não ter volta é recusada, porque ninguém autorizou."""
    if dialog.type in {"confirm", "prompt"} and looks_irreversible(dialog.message):
        dialog.dismiss()
    else:
        dialog.accept()


def launch_browser(playwright: Playwright, proxy: EgressProxy | None = None) -> Browser:
    """Tudo o que o navegador acessa passa pelo proxy, inclusive endereços locais e redirecionamentos."""
    egress = proxy or EgressProxy()
    return playwright.chromium.launch(
        headless=settings.browser_headless,
        channel=settings.browser_channel,
        proxy={"server": egress.url},
    )


def new_guarded_context(browser: Browser, allowed_domains: list[str]) -> BrowserContext:
    """Contexto limpo por item, sem sessão compartilhada e com a navegação filtrada."""
    # Service worker responderia direto à página, sem passar pelo filtro
    context = browser.new_context(accept_downloads=True, service_workers="block", locale="pt-BR")
    context.set_default_timeout(settings.step_timeout_ms)

    def guard(route: Route) -> None:
        request = route.request
        allowed = is_request_allowed(
            request.url,
            is_navigation=_is_top_level_navigation(request),
            allowed_domains=allowed_domains,
        )
        if allowed:
            route.continue_()
        else:
            route.abort("blockedbyclient")

    context.route("**/*", guard)
    context.on("page", lambda page: page.on("dialog", _answer_dialog))
    return context
