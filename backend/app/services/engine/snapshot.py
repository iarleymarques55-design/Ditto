from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

MARKER_ATTRIBUTE = "data-ditto-id"

# O valor digitado nos campos nunca é lido: nem o worker nem a IA recebem o que está dentro deles.
# A exceção são os botões <input type="submit">, em que o "value" é o texto visível.
_COLLECT_ELEMENTS = """
() => {
  const selector = 'a,button,input,select,textarea,summary,[role=button],[role=link],[role=menuitem],' +
    '[role=tab],[role=option],[role=checkbox],[role=combobox],[onclick]';
  const isVisible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim().slice(0, 200);
  const textOf = (el) => {
    if (el.tagName === 'INPUT') {
      return ['submit', 'button'].includes(el.type) ? clean(el.getAttribute('value')) : '';
    }
    if (el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') return '';
    return clean(el.innerText);
  };
  const labelOf = (el) => clean(el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText));
  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName;
    if (tag === 'A') return 'link';
    if (tag === 'BUTTON' || tag === 'SUMMARY') return 'button';
    if (tag === 'SELECT') return 'combobox';
    if (tag === 'TEXTAREA') return 'textbox';
    if (tag === 'INPUT') {
      if (['submit', 'button', 'reset'].includes(el.type)) return 'button';
      if (el.type === 'checkbox' || el.type === 'radio') return el.type;
      return 'textbox';
    }
    return 'generic';
  };
  const cssOf = (el) => {
    if (el.id && /^[A-Za-z][\\w-]*$/.test(el.id)) return '#' + el.id;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 4) {
      if (node.id && /^[A-Za-z][\\w-]*$/.test(node.id)) { parts.unshift('#' + node.id); break; }
      const siblings = node.parentElement ? [...node.parentElement.children].filter((s) => s.tagName === node.tagName) : [];
      const position = siblings.indexOf(node) + 1;
      parts.unshift(node.tagName.toLowerCase() + (siblings.length > 1 ? ':nth-of-type(' + position + ')' : ''));
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const neighborsOf = (el) => {
    const scope = el.parentElement;
    if (!scope) return [];
    return [...scope.querySelectorAll(selector)]
      .filter((other) => other !== el && isVisible(other))
      .map((other) => textOf(other) || labelOf(other))
      .filter(Boolean)
      .slice(0, 4);
  };
  document.querySelectorAll('[' + 'data-ditto-id' + ']').forEach((el) => el.removeAttribute('data-ditto-id'));
  return [...document.querySelectorAll(selector)].filter(isVisible).slice(0, 400).map((el, index) => {
    el.setAttribute('data-ditto-id', String(index));
    return {
      index,
      role: roleOf(el),
      tag: el.tagName.toLowerCase(),
      text: textOf(el),
      label: labelOf(el),
      placeholder: clean(el.getAttribute('placeholder')),
      name: clean(el.getAttribute('name')),
      test_id: clean(el.getAttribute('data-testid')),
      input_type: el.tagName === 'INPUT' ? el.type : '',
      css: cssOf(el),
      neighbors: neighborsOf(el),
    };
  });
}
"""

_HAS_CAPTCHA = """
() => {
  const selector = 'iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="turnstile"],iframe[title*="captcha" i],' +
    '.g-recaptcha,.h-captcha,.cf-turnstile,[id*="captcha" i],[class*="captcha" i],[name*="captcha" i]';
  return [...document.querySelectorAll(selector)].some((el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  });
}
"""

_FINGERPRINT_FIELDS = (
    "role",
    "tag",
    "text",
    "label",
    "placeholder",
    "name",
    "test_id",
    "input_type",
    "css",
)


@dataclass
class PageElement:
    index: int
    role: str
    tag: str
    text: str = ""
    label: str = ""
    placeholder: str = ""
    name: str = ""
    test_id: str = ""
    input_type: str = ""
    css: str = ""
    neighbors: list[str] = field(default_factory=list)

    def to_target(self, prelude: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """A impressão digital que fica salva como nova versão do passo."""
        target: dict[str, Any] = {
            key: getattr(self, key) for key in _FINGERPRINT_FIELDS if getattr(self, key)
        }
        if self.neighbors:
            target["neighbors"] = self.neighbors
        if prelude:
            target["prelude"] = prelude
        return target


def take_snapshot(page: Page) -> list[PageElement]:
    return [PageElement(**item) for item in page.evaluate(_COLLECT_ELEMENTS)]


def locator_for(page: Page, element: PageElement) -> Locator:
    return page.locator(f'[{MARKER_ATTRIBUTE}="{element.index}"]')


def has_login_form(page: Page) -> bool:
    try:
        return page.locator("input[type=password]:visible").count() > 0
    except PlaywrightError:
        return False


def has_captcha(page: Page) -> bool:
    return bool(page.evaluate(_HAS_CAPTCHA))
