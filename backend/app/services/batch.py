import csv
import io
import unicodedata
from xml.etree.ElementTree import ParseError  # nosec B405: só o tipo do erro; a leitura usa defusedxml
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, PayloadTooLargeError

_EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
# Um .xlsx é um zip. Um arquivo de 5 MB pode se abrir em gigabytes (bomba de descompressão) e
# derrubar a API: o tamanho aberto é conferido antes de o openpyxl ler qualquer coisa
_MAX_EXCEL_UNPACKED_BYTES = 60 * 1024 * 1024
_MAX_EXCEL_ENTRIES = 2000
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def normalize_column(name: str) -> str:
    """Tira acentos e espaços do nome da coluna: "Mês " vira "mes"."""
    decomposed = unicodedata.normalize("NFD", str(name).strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _read_csv(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # O Excel em português costuma exportar neste formato
        text = content.decode("cp1252", errors="replace")

    first_line = text.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _check_unpacked_size(content: bytes) -> None:
    with ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) > _MAX_EXCEL_ENTRIES:
            raise BusinessRuleError("Esta planilha tem partes demais para ser lida.")
        # O zipfile nunca abre mais que o tamanho declarado de cada parte: a soma é um teto real
        unpacked = sum(entry.file_size for entry in entries)
        if unpacked > _MAX_EXCEL_UNPACKED_BYTES:
            raise PayloadTooLargeError(
                "A planilha fica grande demais quando aberta. Divida em partes menores."
            )


def _read_excel(content: bytes) -> list[list[str]]:
    # As linhas só são lidas durante o laço (read_only): um XML malicioso ou quebrado dentro da
    # planilha aparece ali, e não ao abrir. Os dois ficam dentro da mesma proteção
    try:
        _check_unpacked_size(content)
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            return _rows_until_limit(workbook)
        finally:
            workbook.close()
    except (BadZipFile, InvalidFileException, KeyError, ValueError, ParseError) as error:
        # Entidade XML recusada pelo defusedxml também é ValueError
        raise BusinessRuleError("Não foi possível ler esta planilha do Excel.") from error


def _rows_until_limit(workbook: Workbook) -> list[list[str]]:
    # Para de ler logo depois do limite: um arquivo pequeno pode declarar milhões de linhas
    rows: list[list[str]] = []
    for row in workbook.active.iter_rows(values_only=True):
        rows.append(["" if cell is None else str(cell) for cell in row])
        if len(rows) > settings.max_batch_rows + 1:
            break
    return rows


def parse_rows(file_name: str, content: bytes, expected_columns: list[str]) -> list[dict[str, str]]:
    """Lê CSV ou Excel e devolve só as colunas que a tarefa usa."""
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            "A planilha passa do tamanho permitido. Divida em partes menores."
        )

    name = file_name.lower()
    if name.endswith(".csv"):
        table = _read_csv(content)
    elif name.endswith(_EXCEL_EXTENSIONS):
        table = _read_excel(content)
    else:
        raise BusinessRuleError("Envie a planilha em .csv ou .xlsx.")

    if not table:
        raise BusinessRuleError("A planilha está vazia.")

    header = [normalize_column(cell) for cell in table[0]]
    missing = [column for column in expected_columns if column not in header]
    if missing:
        raise BusinessRuleError(
            f"Faltam as colunas {', '.join(missing)}. A primeira linha da planilha precisa ter esses nomes."
        )

    indexes = {column: header.index(column) for column in expected_columns}
    rows = []
    for raw in table[1:]:
        if not any(str(cell).strip() for cell in raw):
            continue
        rows.append(
            {
                column: raw[index].strip() if index < len(raw) else ""
                for column, index in indexes.items()
            }
        )

    if not rows:
        raise BusinessRuleError("A planilha só tem o cabeçalho. Adicione ao menos uma linha.")
    if len(rows) > settings.max_batch_rows:
        raise BusinessRuleError(f"A planilha passa de {settings.max_batch_rows} linhas.")
    return rows


def neutralize_cell(value: str) -> str:
    """Impede que uma célula exportada vire fórmula ao abrir no Excel."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value
