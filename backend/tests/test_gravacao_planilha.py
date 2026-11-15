"""Gravação em planilha (Excel Online): cada célula chega como "ir até ela" e "escrever o valor"."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.flow import Flow
from app.schemas.flow import RecordingCreate
from app.services.analyzer import analyze_flow

Cabecalho = dict[str, str]

CAIXA_DE_NOME = {"css": "#FormulaBar-NameBox-input", "tag": "input", "role": "combobox"}
BARRA = {"css": "#formulaBarTextDivId_textElement", "tag": "div", "role": "textbox"}


def celula(endereco: str, valor: str) -> list[dict[str, Any]]:
    base = {"action": "fill", "spreadsheet_cell": endereco}
    return [
        {**base, "spreadsheet_part": "address", "target": CAIXA_DE_NOME, "value": f"{endereco}\n"},
        {**base, "spreadsheet_part": "value", "target": BARRA, "value": f"{valor}\n"},
    ]


def gravacao() -> dict[str, Any]:
    return {
        "name": "Planilha gravada",
        "start_url": "https://excel.cloud.microsoft/",
        "steps": [
            {"action": "navigate", "url": "https://excel.cloud.microsoft/"},
            *celula("A1", "Produto"),
            *celula("B1", "Janeiro"),
            *celula("E2", "=SOMA(B2:D2)"),
        ],
    }


def test_celulas_viram_passos_com_nome_claro_sem_perguntas(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    resposta = api.post("/api/v1/flows", json=gravacao(), headers=autenticado)
    assert resposta.status_code == 201, resposta.text
    flow_id = resposta.json()["id"]
    with fabrica_sessao() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id))

    detalhe = api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).json()
    intencoes = [passo["intent"] for passo in detalhe["steps"][1:]]
    assert intencoes == [
        "Ir para a célula A1",
        'A1: escrever "Produto"',
        "Ir para a célula B1",
        'B1: escrever "Janeiro"',
        "Ir para a célula E2",
        'E2: escrever "=SOMA(B2:D2)"',
    ]
    # Depois do Enter a barra fica vazia: a verificação de campo falharia em toda célula
    assert {passo["postcondition"]["type"] for passo in detalhe["steps"][1:]} == {"none"}
    # Nenhuma célula vira pergunta, então a tarefa ativa direto
    assert detalhe["variables"] == []
    ativada = api.post(f"/api/v1/flows/{flow_id}/confirm", headers=autenticado)
    assert ativada.status_code == 200, ativada.text


def test_celula_invalida_e_recusada() -> None:
    errada = gravacao()
    errada["steps"][1]["spreadsheet_cell"] = "A0; DROP"
    resposta = RecordingCreate.model_validate
    try:
        resposta(errada)
    except ValueError as erro:
        assert "spreadsheet_cell" in str(erro)
    else:
        raise AssertionError("célula inválida foi aceita")

    sem_parte = gravacao()
    del sem_parte["steps"][1]["spreadsheet_part"]
    try:
        RecordingCreate.model_validate(sem_parte)
    except ValueError as erro:
        assert "andam juntos" in str(erro)
    else:
        raise AssertionError("célula sem a parte foi aceita")
