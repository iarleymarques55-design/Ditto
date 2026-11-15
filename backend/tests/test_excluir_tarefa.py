"""Excluir uma tarefa apaga tudo o que é dela, inclusive os arquivos baixados no disco."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from playwright.sync_api import Browser
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.enums import RunStatus
from app.models.flow import Step
from app.models.run import Artifact, Run
from app.services.worker_tasks import process_next_run
from tests.test_execucao import PLANILHA_1, disparar

Cabecalho = dict[str, str]
Fabrica = sessionmaker[Session]


def test_excluir_apaga_tarefa_execucoes_agenda_e_arquivos(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
    navegador: Browser,
) -> None:
    flow_id = tarefa_ativa["id"]
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    assert process_next_run(fabrica_sessao, navegador) is True
    agenda = api.post(
        "/api/v1/schedules",
        data={"flow_id": flow_id, "cron": "10 7 5 * *"},
        files={"file": ("a.csv", b"loja\nLoja 01 - Shopping Norte\n")},
        headers=autenticado,
    )
    assert agenda.status_code == 201

    with fabrica_sessao() as sessao:
        chaves = sessao.scalars(select(Artifact.storage_key)).all()
    arquivos = [settings.storage_dir / chave for chave in chaves]
    assert arquivos and all(arquivo.is_file() for arquivo in arquivos)

    assert api.delete(f"/api/v1/flows/{flow_id}", headers=autenticado).status_code == 204

    assert api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).status_code == 404
    assert api.get(f"/api/v1/runs/{run_id}", headers=autenticado).status_code == 404
    assert api.get("/api/v1/schedules", headers=autenticado).json() == []
    assert not any(arquivo.exists() for arquivo in arquivos)
    with fabrica_sessao() as sessao:
        assert sessao.scalar(select(func.count()).select_from(Run)) == 0
        assert sessao.scalar(select(func.count()).select_from(Step)) == 0
        assert sessao.scalar(select(func.count()).select_from(Artifact)) == 0


def test_tarefa_rodando_nao_pode_ser_excluida(
    api: TestClient,
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: Fabrica,
) -> None:
    run_id = disparar(api, tarefa_ativa, autenticado, PLANILHA_1)
    with fabrica_sessao() as sessao:
        sessao.get(Run, run_id).status = RunStatus.RUNNING
        sessao.commit()

    resposta = api.delete(f"/api/v1/flows/{tarefa_ativa['id']}", headers=autenticado)
    assert resposta.status_code == 409
    assert "Cancele" in resposta.json()["detail"]
    assert api.get(f"/api/v1/flows/{tarefa_ativa['id']}", headers=autenticado).status_code == 200


def test_tarefa_de_outra_conta_nao_e_excluida(
    api: TestClient,
    criar_conta: Callable[..., Cabecalho],
    autenticado: Cabecalho,
    tarefa_ativa: dict[str, Any],
) -> None:
    outra = criar_conta()
    assert api.delete(f"/api/v1/flows/{tarefa_ativa['id']}", headers=outra).status_code == 404
    assert api.get(f"/api/v1/flows/{tarefa_ativa['id']}", headers=autenticado).status_code == 200
