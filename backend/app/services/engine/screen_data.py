"""Dados que a IA pode guardar ao criar uma tarefa: tabelas e pares "Rótulo: valor" da tela.
Cada item já sai com o alvo no formato que capture.py sabe ler de novo nas execuções."""

from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Frame, Page

from app.services.engine.snapshot import MARKER_ATTRIBUTE

MAX_ITEMS = 40
MAX_OPTIONS = 25

_COLLECT_DATA = """
([maxItems]) => {
  const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const inContent = (el) => !el.closest('nav,header,footer,[role=navigation],[role=banner],[role=contentinfo]');
  const sensitive = (el) => !!el.querySelector('input[type=password]');
  const items = [];

  for (const table of document.querySelectorAll('table')) {
    if (items.length >= maxItems) break;
    if (!visible(table) || !inContent(table) || sensitive(table)) continue;
    const header = (table.tHead && table.tHead.rows[0]) || table.rows[0];
    if (!header) continue;
    const columns = [...header.cells].map((cell) => clean(cell.innerText).slice(0, 200)).filter(Boolean).slice(0, 10);
    const rows = [...table.rows].filter((row) => row !== header);
    if (columns.length < 2 || rows.length < 1) continue;
    const first = [...rows[0].cells].map((cell) => clean(cell.innerText).slice(0, 60)).slice(0, 10);
    items.push({ kind: 'table', columns, rows: rows.length, sample: first });
  }

  const seen = new Set();
  const pair = (anchor, anchorKind, valueEl) => {
    if (items.length >= maxItems || !valueEl || !visible(valueEl)) return;
    if (valueEl.querySelector('input,select,textarea,table')) return;
    const value = clean(valueEl.innerText);
    const key = anchorKind + '|' + anchor;
    if (!anchor || !value || value.length > 300 || anchor.length > 80 || seen.has(key)) return;
    seen.add(key);
    items.push({ kind: 'value', anchor, anchor_kind: anchorKind, tag: valueEl.tagName.toLowerCase(), sample: value.slice(0, 80) });
  };

  for (const term of document.querySelectorAll('dt')) {
    if (visible(term) && inContent(term) && term.nextElementSibling && term.nextElementSibling.tagName === 'DD') {
      pair(clean(term.innerText), 'definition', term.nextElementSibling);
    }
  }
  for (const head of document.querySelectorAll('tr > th:first-child')) {
    const cell = head.nextElementSibling;
    if (visible(head) && inContent(head) && cell && cell.tagName === 'TD' && head.parentElement.cells.length === 2) {
      pair(clean(head.innerText), 'adjacent', cell);
    }
  }
  for (const leaf of document.body.querySelectorAll('p,span,div,li,strong,b,small,td')) {
    if (items.length >= maxItems) break;
    if (leaf.children.length || !visible(leaf) || !inContent(leaf)) continue;
    const match = /^([^:]{1,60}):\\s*(.{1,300})$/.exec(clean(leaf.innerText));
    if (!match) continue;
    const anchor = match[1].trim();
    const key = 'inline|' + anchor;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({ kind: 'value', anchor, anchor_kind: 'inline', tag: leaf.tagName.toLowerCase(), sample: match[2].trim().slice(0, 80) });
  }
  return items.slice(0, maxItems);
}
"""

# O texto que a pessoa vê, sem menus e rodapés: é por ele que a IA sabe se um passo deu certo.
# innerText não traz o que está digitado nos campos.
_VISIBLE_TEXT = """
([maxChars]) => {
  const root = document.querySelector('main,[role=main]') || document.body;
  if (!root) return '';
  let text = root.innerText || '';
  for (const chrome of root.querySelectorAll('nav,header,footer,[role=navigation],[role=banner],[role=contentinfo]')) {
    const piece = (chrome.innerText || '').trim();
    if (piece) text = text.replace(piece, '');
  }
  return text.replace(/[ \\t]+/g, ' ').replace(/\\s*\\n\\s*/g, '\\n').trim().slice(0, maxChars);
}
"""

# Listas comuns e as de formulários como o Google Forms, com as opções escondidas até abrir
_SELECT_OPTIONS = """
([marker, maxOptions]) => {
  const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim();
  return [...document.querySelectorAll('select[' + marker + '],[role=listbox][' + marker + ']')].map((el) => ({
    index: Number(el.getAttribute(marker)),
    options: (el.tagName === 'SELECT'
      ? [...el.options].map((option) => option.text)
      : [...el.querySelectorAll('[role=option]')].map((option) => option.textContent))
      .map(clean).filter(Boolean).slice(0, maxOptions),
  }));
}
"""


@dataclass
class ScreenData:
    index: int
    kind: str  # "table" ou "value"
    sample: list[str] | str
    columns: list[str] = field(default_factory=list)
    rows: int = 0
    anchor: str = ""
    anchor_kind: str = ""
    tag: str = ""

    def to_target(self) -> dict[str, Any]:
        """O alvo da captura, igual ao que a extensão grava."""
        if self.kind == "table":
            return {"tag": "table", "neighbors": self.columns}
        return {"tag": self.tag, "anchor": self.anchor, "anchor_kind": self.anchor_kind}


def collect_screen_data(page: Page) -> list[ScreenData]:
    """Da página e dos iframes. capture.py também procura em todos os frames ao ler de novo."""
    raw: list[dict[str, Any]] = []
    for frame in page.frames:
        try:
            raw.extend(frame.evaluate(_COLLECT_DATA, [MAX_ITEMS]))
        except PlaywrightError:
            continue
    return [ScreenData(index=index, **item) for index, item in enumerate(raw[:MAX_ITEMS])]


def visible_text(page: Page, max_chars: int = 1500) -> str:
    """Da página e dos iframes, até o limite. O sanitizador ainda passa por cima antes da IA."""
    parts: list[str] = []
    room = max_chars
    for frame in page.frames:
        if room <= 0:
            break
        try:
            text = frame.evaluate(_VISIBLE_TEXT, [room])
        except PlaywrightError:
            continue
        if text:
            parts.append(text)
            room -= len(text) + 1
    return "\n".join(parts)[:max_chars]


def select_options(frame: Page | Frame) -> dict[int, list[str]]:
    """As opções de cada lista do frame, pelo número local que a leitura da tela marcou."""
    try:
        raw = frame.evaluate(_SELECT_OPTIONS, [MARKER_ATTRIBUTE, MAX_OPTIONS])
    except PlaywrightError:
        return {}
    return {item["index"]: item["options"] for item in raw}
