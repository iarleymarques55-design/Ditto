import re
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

from app.core.exceptions import BusinessRuleError
from app.models.enums import VariableSource
from app.models.flow import Variable

_PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")
_UNSAFE_CHARS = re.compile(r"[^\w .-]+", re.UNICODE)


def render(template: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise BusinessRuleError(f'A variável "{name}" não tem valor nesta linha.')
        return values[name]

    return _PLACEHOLDER.sub(replace, template)


def rule_values(variables: list[Variable], timezone: str) -> dict[str, str]:
    """Calcula as variáveis que não vêm da planilha, no fuso de quem agendou."""
    today = datetime.now(ZoneInfo(timezone))
    previous_month = today.replace(day=1) - timedelta(days=1)
    computed = {
        VariableSource.PREVIOUS_MONTH: previous_month.strftime("%m/%Y"),
        VariableSource.TODAY: today.strftime("%d/%m/%Y"),
    }
    return {v.name: computed[v.source] for v in variables if v.source in computed}


def _safe_segment(segment: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("-", segment).strip(" .")
    if not cleaned or cleaned == "..":
        raise BusinessRuleError("O caminho para salvar o arquivo é inválido.")
    return cleaned[:120]


def safe_relative_path(template: str | None, values: dict[str, str], fallback: str) -> str:
    """Monta o caminho do arquivo. Valores da planilha nunca criam pastas nem saem da execução."""
    if not template:
        return _safe_segment(fallback)

    normalized = template.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise BusinessRuleError("O caminho para salvar o arquivo não pode ser absoluto.")

    # A divisão vem antes da troca: uma "/" dentro de um valor não vira uma pasta nova
    segments = [_safe_segment(render(part, values)) for part in normalized.split("/") if part]
    if any(part == ".." for part in normalized.split("/")) or not segments:
        raise BusinessRuleError("O caminho para salvar o arquivo é inválido.")

    return str(PurePosixPath(*segments))
