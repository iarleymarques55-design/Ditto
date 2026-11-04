import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.enums import ItemStatus, RunStatus
from app.models.run import Run
from app.repositories.run_repository import RunCounts

_INK = colors.HexColor("#4b37a0")
_LINE = colors.HexColor("#dfe3f0")

ITEM_STATUS_LABELS = {
    ItemStatus.PENDING: "Na fila",
    ItemStatus.RUNNING: "Rodando",
    ItemStatus.SUCCEEDED: "Concluída",
    ItemStatus.REPAIRED: "Concluída com reparo",
    ItemStatus.WAITING_HUMAN: "Espera você",
    ItemStatus.FAILED: "Falhou",
    ItemStatus.SKIPPED: "Pulada",
}

_RUN_STATUS_LABELS = {
    RunStatus.QUEUED: "Na fila",
    RunStatus.RUNNING: "Rodando",
    RunStatus.WAITING_HUMAN: "Espera você",
    RunStatus.SUCCEEDED: "Concluída",
    RunStatus.PARTIAL: "Com falhas",
    RunStatus.FAILED: "Falhou",
    RunStatus.CANCELED: "Cancelada",
}


def _cell(text: str | None, style) -> Paragraph:
    # O Paragraph interpreta marcação: sem escape, um valor da planilha poderia virar tag
    return Paragraph(escape(text or ""), style)


def build_run_report(run: Run, counts: RunCounts | None) -> bytes:
    counts = counts or RunCounts()
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, title="Relatório da execução", leftMargin=2 * cm, rightMargin=2 * cm
    )

    moment = run.created_at.strftime("%d/%m/%Y %H:%M UTC")
    story = [
        Paragraph(escape(run.flow.name), styles["Title"]),
        Paragraph(f"{escape(_RUN_STATUS_LABELS[run.status])}, iniciada em {moment}", body),
        Paragraph(
            f"{counts.done} de {counts.total} cópias concluídas, {counts.repaired} com reparo, {counts.failed} com falha.",
            body,
        ),
        Spacer(1, 0.5 * cm),
    ]

    rows = [["Linha", "Nome", "Situação", "Tempo", "Observação"]]
    for item in run.items:
        rows.append(
            [
                str(item.position),
                _cell(item.label, body),
                _cell(ITEM_STATUS_LABELS[item.status], body),
                f"{item.duration_ms / 1000:.0f} s" if item.duration_ms else "",
                _cell(item.error_message, body),
            ]
        )

    table = Table(rows, colWidths=[1.3 * cm, 5.2 * cm, 3.3 * cm, 1.5 * cm, 5.7 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (0, 0), (-1, 0), _INK),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, _LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    document.build(story)
    return buffer.getvalue()
