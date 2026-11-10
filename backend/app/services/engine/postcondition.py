"""Um passo só conta como feito quando a pós-condição é verdadeira: o clique funcionar não basta."""

import re
import time
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


@dataclass
class PageState:
    fingerprint: str


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
