"""Navegador do worker. Abre sites a pedido do usuário, então é o ponto mais exposto do sistema."""

import weakref
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Dialog, Page, Playwright, Request, Route
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


# Navegadores que são o Chrome da pessoa: neles o Ditto só abre e fecha as próprias abas
_user_browsers: "weakref.WeakSet[Browser]" = weakref.WeakSet()


def connect_user_browser(playwright: Playwright, cdp_url: str) -> Browser:
    """Usa o Chrome da pessoa, com as contas logadas nele, pelo relé da extensão
    (extension_relay.py). Fica sem o proxy de saída: serve para rodar no próprio computador,
    nunca em produção."""
    browser = playwright.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        browser.close()
        raise RuntimeError("O Chrome conectado não tem nenhuma janela aberta.")
    _user_browsers.add(browser)
    return browser


def is_user_browser(browser: Browser) -> bool:
    return browser in _user_browsers


def _guard(route: Route, allowed_domains: list[str]) -> None:
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


def new_guarded_context(browser: Browser, allowed_domains: list[str]) -> BrowserContext:
    """Contexto limpo por item, sem sessão compartilhada e com a navegação filtrada."""
    # Service worker responderia direto à página, sem passar pelo filtro
    context = browser.new_context(accept_downloads=True, service_workers="block", locale="pt-BR")
    context.set_default_timeout(settings.step_timeout_ms)
    context.route("**/*", lambda route: _guard(route, allowed_domains))
    context.on("page", lambda page: page.on("dialog", _answer_dialog))
    return context


class ItemTabs:
    """Onde uma linha roda. No navegador do worker, um contexto limpo só dela. No Chrome da
    pessoa, uma aba nova ao lado das outras, com as contas dela; no fim, só as abas do Ditto
    fecham."""

    def __init__(self, browser: Browser, allowed_domains: list[str]) -> None:
        self._allowed_domains = allowed_domains
        self._pages: list[Page] = []
        self._context: BrowserContext | None = None
        if is_user_browser(browser):
            self._adopt(browser.contexts[0].new_page())
        else:
            self._context = new_guarded_context(browser, allowed_domains)
            self._context.on("page", lambda page: self._pages.append(page))
            self._context.new_page()

    @property
    def current(self) -> Page:
        """Um clique pode ter aberto outra aba: o próximo passo acontece na mais recente."""
        open_pages = [page for page in self._pages if not page.is_closed()]
        return open_pages[-1] if open_pages else self._pages[0]

    def _adopt(self, page: Page) -> None:
        # O filtro fica na aba, e não no Chrome inteiro, para não tocar nas abas da pessoa
        page.set_default_timeout(settings.step_timeout_ms)
        page.route("**/*", lambda route: _guard(route, self._allowed_domains))
        page.on("dialog", _answer_dialog)
        page.on("popup", self._adopt)
        self._pages.append(page)
        # A primeira página de uma aba aberta pelo site carrega antes de o filtro existir
        url = page.url
        if url not in {"", "about:blank"} and not is_request_allowed(
            url, is_navigation=True, allowed_domains=self._allowed_domains
        ):
            page.close()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            return
        for page in self._pages:
            try:
                if not page.is_closed():
                    page.close()
            except PlaywrightError:
                # A pessoa pode ter fechado a aba ou o Chrome no meio da linha
                pass
