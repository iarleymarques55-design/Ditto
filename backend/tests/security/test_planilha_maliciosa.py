"""Planilhas enviadas para repetir uma tarefa: um .xlsx é um zip de XML, e o XML pode atacar."""

import io
import time
import zipfile
from pathlib import Path

import openpyxl.xml
import pytest
from openpyxl import Workbook

from app.core.config import BACKEND_DIR
from app.core.exceptions import BusinessRuleError
from app.services.batch import parse_rows

# "Bilhão de risadas": 10 entidades, cada uma com 10 da anterior. Expandido, passa de gigabytes
_BOMBA = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
  <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
  <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
  <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
  <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&lol9;</t></is></c></row></sheetData>
</worksheet>"""


def planilha_com_folha(conteudo_da_folha: str) -> bytes:
    """Uma planilha válida em que a primeira folha foi trocada pelo XML dado."""
    livro = Workbook()
    livro.active.append(["cnpj"])
    original = io.BytesIO()
    livro.save(original)

    alterada = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original.getvalue())) as entrada,
        zipfile.ZipFile(alterada, "w", zipfile.ZIP_DEFLATED) as saida,
    ):
        for item in entrada.infolist():
            dados = entrada.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                dados = conteudo_da_folha.encode()
            saida.writestr(item, dados)
    return alterada.getvalue()


def test_bomba_xml_e_recusada_sem_travar() -> None:
    inicio = time.monotonic()
    with pytest.raises(BusinessRuleError):
        parse_rows("lojas.xlsx", planilha_com_folha(_BOMBA), ["cnpj"])
    # Recusada antes de expandir: nada de segundos de CPU nem gigabytes de memória
    assert time.monotonic() - inicio < 2


def test_xml_quebrado_no_meio_da_folha_vira_mensagem_e_nao_erro_500() -> None:
    quebrado = '<?xml version="1.0"?><worksheet><sheetData><row r="1"><c r="A1"'
    with pytest.raises(BusinessRuleError, match="Não foi possível ler"):
        parse_rows("lojas.xlsx", planilha_com_folha(quebrado), ["cnpj"])


def test_protecao_de_xml_vai_junto_para_producao() -> None:
    # O openpyxl só se protege quando o defusedxml está instalado
    assert openpyxl.xml.DEFUSEDXML is True
    dependencias = (Path(BACKEND_DIR) / "requirements.txt").read_text(encoding="utf-8")
    assert "\ndefusedxml==" in dependencias
