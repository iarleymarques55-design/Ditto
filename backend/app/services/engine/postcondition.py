"""Um passo só conta como feito quando a pós-condição é verdadeira: o clique funcionar não basta."""

import time
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

from app.core.config import settings
from app.models.enums import StepAction

NONE = "none"
DOWNLOAD = "download"
URL_CONTAINS = "url_contains"
TEXT_VISIBLE = "text_visible"
FIELD_VALUE = "field_value"
PAGE_CHANGED = "page_changed"

VERIFIABLE_TYPES = {DOWNLOAD, URL_CONTAINS, TEXT_VISIBLE, FIELD_VALUE, PAGE_CHANGED}

_PAGE_FINGERPRINT = "() => [location.href, document.body ? document.body.innerText.length : 0, document.querySelectorAll('*').length].join('|')"
_POLL_SECONDS = 0.1


@dataclass
class PageState:
    fingerprint: str


def capture_state(page: Page) -> PageState:
    try:
        return PageState(page.evaluate(_PAGE_FINGERPRINT))
    except PlaywrightError:
        return PageState("")


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


def _field_matches(locator: Locator, action: StepAction, expected: str | None) -> bool:
    if action == StepAction.CHECK:
        return locator.is_checked()
    if action == StepAction.SELECT:
        selected = locator.evaluate(
            "el => [el.value, el.selectedOptions[0] ? el.selectedOptions[0].text.trim() : '']"
        )
        return expected in selected
    return locator.input_value() == (expected or "")


def check(
    page: Page,
    postcondition: dict[str, Any],
    *,
    action: StepAction,
    locator: Locator | None,
    value: str | None,
    before: PageState,
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
        return locator is not None and _wait_until(lambda: _field_matches(locator, action, value))
    if kind == PAGE_CHANGED:
        return _wait_until(lambda: capture_state(page).fingerprint != before.fingerprint)
    return False
