"""Navegador do worker. Abre sites a pedido do usuário, então é o ponto mais exposto do sistema."""

from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Playwright, Route

from app.core.config import settings
from app.services.engine.egress_proxy import EgressProxy

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
            is_navigation=request.is_navigation_request() and request.frame.parent_frame is None,
            allowed_domains=allowed_domains,
        )
        if allowed:
            route.continue_()
        else:
            route.abort("blockedbyclient")

    context.route("**/*", guard)
    return context
