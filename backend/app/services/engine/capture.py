"""Lê dados da página. O valor muda a cada linha, então o que localiza o dado é a âncora ao redor dele."""

from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

MAX_TABLE_ROWS = 1000
_MAX_COLUMNS = 30
_MAX_VALUE_CHARS = 5000
_MAX_CELL_CHARS = 500

# Campo de senha e dados de cartão nunca são lidos, mesmo que alguém tente capturá-los.
_READ_VALUE = """
const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim();
const visible = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
const valueOf = (el) => {
  if (!el || !visible(el)) return null;
  const tag = el.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') {
    const autocomplete = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (el.type === 'password' || autocomplete.includes('password') || autocomplete.startsWith('cc-')) return null;
    return clean(el.value);
  }
  if (tag === 'SELECT') return clean(el.selectedOptions[0] ? el.selectedOptions[0].text : '');
  return clean(el.innerText);
};
"""

_FIND_VALUE = (
    """
(target) => {
"""
    + _READ_VALUE
    + """
  const anchor = clean(target.anchor);
  const all = (selector) => [...document.querySelectorAll(selector)].filter(visible);
  const finders = {
    table_header: () => {
      for (const table of all('table')) {
        const headerRow = (table.tHead && table.tHead.rows[0]) || table.rows[0];
        if (!headerRow) continue;
        const column = [...headerRow.cells].findIndex((cell) => clean(cell.innerText) === anchor);
        if (column < 0) continue;
        const rows = [...table.rows].filter((row) => row !== headerRow);
        const row = rows[target.row_index || 0];
        if (row && row.cells[column]) return row.cells[column];
      }
      return null;
    },
    definition: () => {
      const term = all('dt').find((el) => clean(el.innerText) === anchor);
      return term ? term.nextElementSibling : null;
    },
    label: () => {
      const label = all('label').find((el) => clean(el.innerText) === anchor);
      if (!label) return null;
      return label.control || label.querySelector('input,select,textarea');
    },
    adjacent: () => {
      const leaf = all('*').find((el) => el.children.length === 0 && clean(el.innerText) === anchor);
      if (!leaf) return null;
      return leaf.nextElementSibling || (leaf.parentElement && leaf.parentElement.nextElementSibling);
    },
  };

  if (target.test_id) {
    const el = document.querySelector('[data-testid="' + CSS.escape(target.test_id) + '"]');
    const value = valueOf(el);
    if (value !== null) return value;
  }

  if (anchor && target.anchor_kind === 'inline') {
    const prefix = anchor + ':';
    const leaf = all('*').find((el) => el.children.length === 0 && clean(el.innerText).startsWith(prefix));
    return leaf ? clean(leaf.innerText).slice(prefix.length).trim() : null;
  }
  if (anchor && finders[target.anchor_kind]) return valueOf(finders[target.anchor_kind]());

  // Com âncora, o CSS não é usado de reserva: depois de uma mudança no site, ele poderia ler
  // outro dado sem ninguém perceber, e um dado errado é pior que um pedido de ajuda.
  if (!anchor && target.css) {
    const matches = all(target.css);
    if (matches.length === 1) return valueOf(matches[0]);
  }
  return null;
}
"""
)

_FIND_TABLE = (
    """
([target, maxRows, maxColumns, maxCell]) => {
"""
    + _READ_VALUE
    + """
  const cellText = (cell) => clean(cell.innerText).slice(0, maxCell);
  const headerRowOf = (table) => (table.tHead && table.tHead.rows[0]) || table.rows[0];
  const headersOf = (table) => {
    const row = headerRowOf(table);
    return row ? [...row.cells].slice(0, maxColumns).map(cellText) : [];
  };
  const wanted = (target.neighbors || []).map(clean);
  const score = (table) => {
    const headers = headersOf(table);
    return wanted.filter((name) => headers.includes(name)).length;
  };

  const tables = [...document.querySelectorAll('table')].filter(visible);
  let table = null;
  if (wanted.length) {
    const best = tables.map((item) => [score(item), item]).sort((a, b) => b[0] - a[0])[0];
    // Metade dos cabeçalhos gravados precisa bater: outra tabela da página não serve
    if (best && best[0] * 2 >= wanted.length) table = best[1];
  } else if (tables.length === 1) {
    table = tables[0];
  }
  if (!table) return null;

  const names = headersOf(table).map((name, index) => name || 'coluna_' + (index + 1));
  const headerRow = headerRowOf(table);
  const rows = [...table.rows].filter((row) => row !== headerRow).slice(0, maxRows);
  return rows.map((row) => {
    const entry = {};
    names.forEach((name, index) => {
      entry[name] = row.cells[index] ? cellText(row.cells[index]) : '';
    });
    return entry;
  });
}
"""
)


def read_value(page: Page, target: dict[str, Any]) -> str | None:
    for frame in page.frames:
        try:
            value = frame.evaluate(_FIND_VALUE, target)
        except PlaywrightError:
            continue  # o iframe pode ter acabado de sair da página
        if value is not None:
            return value[:_MAX_VALUE_CHARS]
    return None


def read_table(page: Page, target: dict[str, Any]) -> list[dict[str, str]] | None:
    arguments = [target, MAX_TABLE_ROWS, _MAX_COLUMNS, _MAX_CELL_CHARS]
    for frame in page.frames:
        try:
            rows = frame.evaluate(_FIND_TABLE, arguments)
        except PlaywrightError:
            continue
        if rows is not None:
            return rows
    return None
