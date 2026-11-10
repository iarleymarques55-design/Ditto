import io

from openpyxl import Workbook

from app.models.enums import ArtifactKind, CaptureKind
from app.models.run import Run
from app.services.batch import neutralize_cell
from app.services.pdf_report import ITEM_STATUS_LABELS
from app.services.presenters import current_target

_SHEET_NAME_LIMIT = 31
_FORBIDDEN_IN_SHEET_NAME = str.maketrans({char: " " for char in "[]:*?/\\"})


def _sheet_name(label: str, used: set[str]) -> str:
    base = label.translate(_FORBIDDEN_IN_SHEET_NAME).strip()[:_SHEET_NAME_LIMIT] or "Dados"
    name = base
    suffix = 2
    while name.lower() in used:
        name = f"{base[: _SHEET_NAME_LIMIT - 3]} {suffix}"
        suffix += 1
    used.add(name.lower())
    return name


def _cell(value: object) -> object:
    # O texto veio de um site: sem isto, um "=..." viraria fórmula ao abrir no Excel
    return neutralize_cell(value) if isinstance(value, str) else value


def build_workbook(run: Run) -> bytes:
    """Uma aba com uma linha por cópia e uma aba para cada tabela capturada."""
    captures = [step for step in run.flow.steps if step.capture_key]
    values = [step for step in captures if step.capture_kind == CaptureKind.VALUE]
    tables = [step for step in captures if step.capture_kind == CaptureKind.TABLE]

    workbook = Workbook(write_only=True)
    used = {"resultado"}
    summary = workbook.create_sheet("Resultado")
    summary.append(
        [
            "Linha",
            "Nome",
            "Situação da linha",
            *(step.capture_label for step in values),
            "Tempo (s)",
            "Arquivo",
            "Erro",
        ]
    )
    for item in run.items:
        output = item.output or {}
        file = next((a.file_name for a in item.artifacts if a.kind == ArtifactKind.FILE), "")
        summary.append(
            [
                item.position,
                _cell(item.label),
                ITEM_STATUS_LABELS[item.status],
                *(_cell(output.get(step.capture_key, "")) for step in values),
                round(item.duration_ms / 1000, 1) if item.duration_ms else None,
                _cell(file),
                _cell(item.error_message or ""),
            ]
        )

    for step in tables:
        rows = [
            (item, row)
            for item in run.items
            for row in (item.output or {}).get(step.capture_key, [])
        ]
        # O banco não guarda a ordem das chaves: quem manda é a ordem dos cabeçalhos gravados
        recorded = current_target(step).get("neighbors", [])
        columns = list(dict.fromkeys([*recorded, *(name for _, row in rows for name in row)]))
        sheet = workbook.create_sheet(_sheet_name(step.capture_label, used))
        sheet.append(["Linha", "Nome", *(_cell(name) for name in columns)])
        for item, row in rows:
            sheet.append(
                [item.position, _cell(item.label), *(_cell(row.get(name, "")) for name in columns)]
            )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
