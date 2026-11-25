"""Um passo só conta como feito quando a pós-condição é verdadeira: o clique funcionar não basta."""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import ElementHandle, Locator, Page
from playwright.sync_api import Error as PlaywrightError

from app.core.config import settings
from app.models.enums import StepAction

NONE = "none"
DOWNLOAD = "download"
URL_CONTAINS = "url_contains"
TEXT_VISIBLE = "text_visible"
FIELD_VALUE = "field_value"
PAGE_CHANGED = "page_changed"
# Em captura: só lê quando o texto parar de mudar, como a resposta de um chat sendo escrita
TEXT_STABLE = "text_stable"

VERIFIABLE_TYPES = {DOWNLOAD, URL_CONTAINS, TEXT_VISIBLE, FIELD_VALUE, PAGE_CHANGED}

# Um clique pode só trocar uma aba ou abrir um menu: conta o texto e o estado dos elementos, não só o tamanho
_PAGE_FINGERPRINT = """() => {
  const hash = (seed, text) => {
    let value = seed;
    for (let i = 0; i < text.length; i++) value = (value * 31 + text.charCodeAt(i)) | 0;
    return value;
  };
  const elements = document.querySelectorAll('*');
  let state = 0;
  for (const el of elements) {
    state = hash(state, el.getAttribute('class') || '');
    for (const name of ['aria-expanded', 'aria-selected', 'aria-checked', 'aria-pressed', 'open', 'hidden']) {
      if (el.hasAttribute(name)) state = hash(state, name + el.getAttribute(name));
    }
    if (el.checked) state = hash(state, 'checked');
  }
  const text = document.body ? document.body.innerText : '';
  return [location.href, hash(0, text), elements.length, state].join('|');
}"""
_POLL_SECONDS = 0.1

# Fica no quadro anotando a hora da última mudança (estrutura, texto, abrir e fechar, marcar):
# conferir depois é uma pergunta só, sem ler o texto da página. Mudança de estilo, como uma
# animação, não conta, senão um carrossel faria todo passo esperar o tempo máximo
_QUIET_PROBE = """() => {
  let state = window.__dittoQuiet;
  if (!state) {
    state = { last: performance.now() };
    try {
      new MutationObserver(() => { state.last = performance.now(); }).observe(document, {
        subtree: true, childList: true, characterData: true, attributes: true,
        attributeFilter: ['class', 'aria-expanded', 'aria-selected', 'aria-checked',
          'aria-pressed', 'aria-busy', 'open', 'hidden', 'disabled'],
      });
    } catch (error) {
      return 1e9;
    }
    Object.defineProperty(window, '__dittoQuiet', { value: state });
  }
  return performance.now() - state.last;
}"""
_LOAD_WAIT_MS = 3000
_MIN_WAIT_SECONDS = 0.15


@dataclass
class PageState:
    fingerprint: str


def _quiet_for(page: Page, limit: float) -> float:
    """Há quanto tempo nenhum quadro muda. Quadro que não responde fica de fora, menos o
    principal: sem resposta dele, a página está trocando de endereço."""
    quiet = limit
    for frame in page.frames:
        try:
            quiet = min(quiet, frame.evaluate(_QUIET_PROBE) / 1000)
        except PlaywrightError:
            if frame == page.main_frame:
                return 0.0
    return quiet


def wait_until_quiet(
    page: Page,
    *,
    busy: Callable[[], bool] = lambda: False,
    quiet_seconds: float,
    max_seconds: float,
) -> None:
    """Espera a página ficar parada por um tempo. Uma animação sem fim só custa o máximo.

    Cada pergunta ao Chrome atravessa a rede quando ele está no computador da pessoa: em vez de
    fotografar a página várias vezes, pergunta uma vez por quadro há quanto tempo ele está parado
    e dorme só o que falta."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=_LOAD_WAIT_MS)
    except PlaywrightError:
        return
    started = time.monotonic()
    deadline = started + max_seconds
    while True:
        if busy():
            missing = _MIN_WAIT_SECONDS
        else:
            # Parada de antes da ação não vale: o site pode responder um instante depois
            quiet = min(_quiet_for(page, max_seconds), time.monotonic() - started)
            missing = quiet_seconds - quiet
        left = deadline - time.monotonic()
        if missing <= 0 or left <= 0:
            return
        try:
            page.wait_for_timeout(max(min(missing, left), _MIN_WAIT_SECONDS) * 1000)
        except PlaywrightError:
            return


def capture_state(page: Page) -> PageState:
    """Soma os iframes: um clique dentro de um deles também muda a página."""
    # Abrir uma janela nova também é a página respondendo ao clique
    parts = [str(len(page.context.pages))]
    for frame in page.frames:
        try:
            parts.append(frame.evaluate(_PAGE_FINGERPRINT))
        except PlaywrightError:
            parts.append("")
    return PageState("#".join(parts))


def _wait_until(condition) -> bool:
    deadline = time.monotonic() + settings.postcondition_timeout_ms / 1000
    while True:
        try:
            if condition():
                return True
        except PlaywrightError:
            # A página pode estar no meio de uma navegação; a próxima tentativa decide
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_SECONDS)


def _comparable(text: str) -> str:
    # Campos com máscara mostram "11.222.333/0001-81" para quem digitou só os números
    return re.sub(r"\W+", "", text).casefold()


def _field_matches(
    locator: Locator | ElementHandle, action: StepAction, expected: str | None
) -> bool:
    if action == StepAction.CHECK:
        return locator.is_checked()
    if action == StepAction.SELECT:
        selected = locator.evaluate(
            "el => [el.value, el.selectedOptions[0] ? el.selectedOptions[0].text.trim() : '']"
        )
        return expected in selected
    current = locator.evaluate("el => el.isContentEditable ? el.innerText : el.value")
    wanted = expected or ""
    return current == wanted or _comparable(current) == _comparable(wanted)


def _filled_field_matches(
    filled: ElementHandle | None, locator: Locator, action: StepAction, expected: str | None
) -> bool:
    """Confere o próprio elemento preenchido: procurar de novo pode achar mais de um, como a lista
    de sugestões que abre com o mesmo nome. Se o site trocou o campo, vale o primeiro encontrado."""
    for field in (filled, locator.first):
        if field is None:
            continue
        try:
            if _field_matches(field, action, expected):
                return True
        except PlaywrightError:
            continue
    return False


def check(
    page: Page,
    postcondition: dict[str, Any],
    *,
    action: StepAction,
    locator: Locator | None,
    value: str | None,
    before: PageState,
    filled: ElementHandle | None = None,
) -> bool:
    """Downloads são conferidos por quem executa a ação, porque precisam começar antes do clique."""
    kind = postcondition.get("type", NONE)

    if kind == NONE:
        return True
    if kind == URL_CONTAINS:
        return _wait_until(lambda: postcondition.get("value", "") in page.url)
    if kind == TEXT_VISIBLE:
        return _wait_until(
            lambda: page.get_by_text(postcondition.get("value", "")).first.is_visible()
        )
    if kind == FIELD_VALUE:
        return locator is not None and _wait_until(
            lambda: _filled_field_matches(filled, locator, action, value)
        )
    if kind == PAGE_CHANGED:
        return _wait_until(lambda: capture_state(page).fingerprint != before.fingerprint)
    return False
