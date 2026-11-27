"""Navegador do worker. Abre sites a pedido do usuário, então é o ponto mais exposto do sistema."""

import weakref
from collections.abc import Callable
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Dialog, Page, Playwright, Request, Route
from playwright.sync_api import Error as PlaywrightError

from app.core.config import settings
from app.services.engine.egress_proxy import EgressProxy
from app.services.engine.safety import looks_irreversible

_ALLOWED_SCHEMES = {"http", "https"}
# O maior arquivo que uma tarefa pode baixar. É o mesmo limite da extensão (DOWNLOAD_MAXIMO_BYTES
# em extension/runner.js), que entrega o arquivo pela conexão quando a tarefa roda no Chrome
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024


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
    try:
        browser = playwright.chromium.launch(
            headless=settings.browser_headless,
            channel=settings.browser_channel,
            proxy={"server": egress.url},
        )
    except Exception:
        if proxy is None:
            egress.stop()
        raise
    if proxy is None:
        # O proxy é deste navegador: fecha junto com ele, inclusive quando ele cai e a linha de
        # trabalho abre outro. Sem isso, cada reabertura deixava uma porta e uma thread para trás
        browser.on("disconnected", lambda _browser: egress.stop())
    return browser


# Navegadores que são o Chrome da pessoa: neles o Ditto só abre e fecha as próprias abas
_user_browsers: "weakref.WeakSet[Browser]" = weakref.WeakSet()

# Recebe os domínios da tarefa e diz se a extensão passou a barrar a navegação para fora deles
DomainFilter = Callable[[list[str]], bool]
_domain_filters: "weakref.WeakKeyDictionary[Browser, DomainFilter]" = weakref.WeakKeyDictionary()


def set_domain_filter(browser: Browser, domain_filter: DomainFilter) -> None:
    """No Chrome da pessoa, a extensão pode filtrar a navegação sozinha (veja ItemTabs)."""
    _domain_filters[browser] = domain_filter


def _rule_domains(domains: list[str]) -> list[str] | None:
    """Os domínios no formato que o Chrome aceita numa regra (minúsculas, acentos em punycode).
    None se algum não puder ser convertido: aí o filtro fica com o worker."""
    converted = []
    for domain in domains:
        try:
            converted.append(domain.strip().lower().encode("idna").decode("ascii"))
        except UnicodeError:
            return None
    return converted


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


_UNBLOCK_ATTEMPTS = 3


def goto_after_unblock(page: Page, url: str) -> None:
    """Abre um endereço que acabou de ser liberado. A navegação barrada antes deixa a página de
    erro do Chrome chegando um instante depois, e ela pode atropelar esta (ou a tentativa
    anterior chega depois da seguinte): espera assentar e só tenta de novo se não chegou lá."""
    for attempt in range(_UNBLOCK_ATTEMPTS):
        try:
            page.goto(url, wait_until="domcontentloaded")
            return
        except PlaywrightError as error:
            if "interrupted by another navigation" not in str(error):
                raise
            if attempt == _UNBLOCK_ATTEMPTS - 1:
                raise
        try:
            page.wait_for_load_state("domcontentloaded")
        except PlaywrightError:
            pass
        if page.url == url:
            return


def _guard(
    route: Route,
    allowed_domains: list[str],
    on_blocked: Callable[[str], None] | None = None,
) -> None:
    request = route.request
    is_navigation = _is_top_level_navigation(request)
    allowed = is_request_allowed(
        request.url, is_navigation=is_navigation, allowed_domains=allowed_domains
    )
    if allowed:
        route.continue_()
        return
    route.abort("blockedbyclient")
    if is_navigation and on_blocked is not None:
        on_blocked(request.url)


def new_guarded_context(
    browser: Browser,
    allowed_domains: list[str],
    on_blocked: Callable[[str], None] | None = None,
) -> BrowserContext:
    """Contexto limpo por item, sem sessão compartilhada e com a navegação filtrada."""
    # Service worker responderia direto à página, sem passar pelo filtro
    context = browser.new_context(accept_downloads=True, service_workers="block", locale="pt-BR")
    context.set_default_timeout(settings.step_timeout_ms)
    context.route("**/*", lambda route: _guard(route, allowed_domains, on_blocked))
    context.on("page", lambda page: page.on("dialog", _answer_dialog))
    return context


class ItemTabs:
    """Onde uma linha roda. No navegador do worker, um contexto limpo só dela. No Chrome da
    pessoa, uma aba nova ao lado das outras, com as contas dela; no fim, só as abas do Ditto
    fecham."""

    def __init__(
        self,
        browser: Browser,
        allowed_domains: list[str],
        on_blocked: Callable[[str], None] | None = None,
    ) -> None:
        # A lista é lida a cada pedido: quem criou pode liberar um domínio novo no meio
        self._allowed_domains = allowed_domains
        self._on_blocked = on_blocked
        self._pages: list[Page] = []
        self._context: BrowserContext | None = None
        self._domain_filter = _domain_filters.get(browser)
        self._filtered_by_extension = False
        if is_user_browser(browser):
            # Antes de abrir a aba: a regra já vale para a primeira navegação
            self._filtered_by_extension = self._send_domains()
            self._adopt(browser.contexts[0].new_page())
        else:
            self._context = new_guarded_context(browser, allowed_domains, on_blocked)
            self._context.on("page", lambda page: self._pages.append(page))
            self._context.new_page()

    @property
    def current(self) -> Page:
        """Um clique pode ter aberto outra aba: o próximo passo acontece na mais recente."""
        open_pages = [page for page in self._pages if not page.is_closed()]
        return open_pages[-1] if open_pages else self._pages[0]

    def _send_domains(self) -> bool:
        if self._domain_filter is None:
            return False
        domains = _rule_domains(self._allowed_domains)
        return domains is not None and self._domain_filter(domains)

    def allowed_domains_changed(self) -> None:
        """Quem criou liberou um domínio novo no meio: a regra da extensão precisa saber."""
        if self._filtered_by_extension and not self._send_domains():
            # A extensão parou de aceitar: o worker volta a filtrar nas abas abertas
            self._filtered_by_extension = False
            for page in self._pages:
                if not page.is_closed():
                    self._route_through_worker(page)

    def _route_through_worker(self, page: Page) -> None:
        page.route("**/*", lambda route: _guard(route, self._allowed_domains, self._on_blocked))

    def _on_failed_request(self, request: Request) -> None:
        """Com o filtro na extensão, a navegação barrada chega aqui como pedido recusado."""
        if (
            self._on_blocked is not None
            and _is_top_level_navigation(request)
            and "ERR_BLOCKED_BY_CLIENT" in (request.failure or "")
        ):
            self._on_blocked(request.url)

    def _adopt(self, page: Page) -> None:
        # O filtro fica na aba, e não no Chrome inteiro, para não tocar nas abas da pessoa
        page.set_default_timeout(settings.step_timeout_ms)
        if self._filtered_by_extension:
            page.on("requestfailed", self._on_failed_request)
        else:
            self._route_through_worker(page)
        page.on("dialog", _answer_dialog)
        page.on("popup", self._adopt)
        self._pages.append(page)
        # A primeira página de uma aba aberta pelo site carrega antes de o filtro existir
        url = page.url
        if url not in {"", "about:blank"} and not is_request_allowed(
            url, is_navigation=True, allowed_domains=self._allowed_domains
        ):
            page.close()
            if self._on_blocked is not None:
                self._on_blocked(url)

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
