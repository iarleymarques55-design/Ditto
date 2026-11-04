"""A API com banco de verdade: contas, tarefas, agendas e resumo."""

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.models.flow import Flow
from app.models.user import User
from app.services.analyzer import analyze_flow
from app.services.llm_client import LlmUnavailableError
from app.services.worker_tasks import analyze_next_flow
from tests.conftest import gravacao_relatorio

Cabecalho = dict[str, str]


def test_migracao_cria_exatamente_o_que_os_models_descrevem(engine_de_teste: Engine) -> None:
    with engine_de_teste.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    assert diferencas == []


# Contas


def test_criar_conta_e_entrar(api: TestClient) -> None:
    corpo = {"name": "Carla", "email": "Carla@Empresa.com", "password": "senha-bem-longa"}
    criada = api.post("/api/v1/auth/register", json=corpo)
    assert criada.status_code == 201
    assert criada.json()["user"]["email"] == "carla@empresa.com"
    assert "senha-bem-longa" not in criada.text
    assert "password_hash" not in criada.text

    entrou = api.post(
        "/api/v1/auth/login", json={"email": "carla@empresa.com", "password": "senha-bem-longa"}
    )
    assert entrou.status_code == 200

    token = entrou.json()["access_token"]
    eu = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert eu.json()["name"] == "Carla"


def test_email_repetido_e_recusado(api: TestClient, criar_conta: Callable[..., Cabecalho]) -> None:
    criar_conta(email="a@teste.com")
    corpo = {"name": "B", "email": "A@teste.com", "password": "outra-senha-longa"}
    resposta = api.post("/api/v1/auth/register", json=corpo)
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "CONFLICT"


def test_senha_errada_e_email_inexistente_respondem_igual(
    api: TestClient, criar_conta: Callable[..., Cabecalho]
) -> None:
    criar_conta(email="a@teste.com")
    errada = api.post("/api/v1/auth/login", json={"email": "a@teste.com", "password": "errada"})
    ausente = api.post("/api/v1/auth/login", json={"email": "b@teste.com", "password": "errada"})
    assert errada.status_code == ausente.status_code == 401
    assert errada.json() == ausente.json()


def test_senha_guardada_so_como_hash(
    api: TestClient, criar_conta: Callable[..., Cabecalho], fabrica_sessao: sessionmaker[Session]
) -> None:
    criar_conta(email="a@teste.com", senha="senha-marcada-123")
    with fabrica_sessao() as sessao:
        usuario = sessao.query(User).one()
    assert usuario.password_hash.startswith("$2b$")
    assert "senha-marcada-123" not in usuario.password_hash


def _claims(**extras: Any) -> dict[str, Any]:
    return {
        "iss": "accounts.google.com",
        "sub": "google-1",
        "email": "a@teste.com",
        "email_verified": True,
        "name": "Ana",
        **extras,
    }


def test_google_cria_conta_na_primeira_vez(api: TestClient) -> None:
    with patch("app.services.auth_service._verify_google_token", return_value=_claims()):
        resposta = api.post("/api/v1/auth/google", json={"credential": "token"})
    assert resposta.status_code == 200
    assert resposta.json()["user"]["email"] == "a@teste.com"


def test_google_tira_a_senha_de_conta_criada_antes_com_o_mesmo_email(
    api: TestClient, criar_conta: Callable[..., Cabecalho]
) -> None:
    # Sem isso, quem cadastrou o e-mail de outra pessoa continuaria entrando na conta dela
    criar_conta(email="a@teste.com", senha="senha-do-invasor")
    with patch("app.services.auth_service._verify_google_token", return_value=_claims()):
        assert api.post("/api/v1/auth/google", json={"credential": "token"}).status_code == 200

    resposta = api.post(
        "/api/v1/auth/login", json={"email": "a@teste.com", "password": "senha-do-invasor"}
    )
    assert resposta.status_code == 401


def test_google_recusa_email_nao_verificado(api: TestClient) -> None:
    with patch(
        "app.services.auth_service._verify_google_token",
        return_value=_claims(email_verified=False),
    ):
        assert api.post("/api/v1/auth/google", json={"credential": "t"}).status_code == 401


def test_google_recusa_token_invalido(api: TestClient) -> None:
    with patch("app.services.auth_service._verify_google_token", side_effect=ValueError("ruim")):
        assert api.post("/api/v1/auth/google", json={"credential": "t"}).status_code == 401


# Gravações


def _gravacao_com_login(url: str) -> dict[str, Any]:
    return {
        "name": "Com login",
        "start_url": f"{url}/login",
        "steps": [
            {"action": "navigate", "url": f"{url}/login"},
            {
                "action": "fill",
                "value": "financeiro",
                "target": {"role": "textbox", "label": "Usuário", "input_type": "text"},
            },
            {
                "action": "fill",
                "value": "senha-marcada-123",
                "target": {"role": "textbox", "label": "Senha", "input_type": "password"},
            },
            {"action": "click", "target": {"role": "button", "text": "Entrar"}},
        ],
    }


def test_senha_da_gravacao_nunca_e_guardada(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    # A extensão não marcou como sensível: o backend mascara mesmo assim
    resposta = api.post(
        "/api/v1/flows", json=_gravacao_com_login("https://portal.exemplo"), headers=autenticado
    )
    assert resposta.status_code == 201
    assert "senha-marcada-123" not in resposta.text

    with fabrica_sessao() as sessao:
        flow = sessao.query(Flow).one()
        passo_usuario, passo_senha = flow.steps[1], flow.steps[2]
        assert passo_senha.credential_field == "password"
        assert passo_senha.value_template is None
        assert passo_usuario.credential_field == "username"
        assert passo_usuario.value_template is None

        analyze_flow(sessao, flow)
        # Nem vira uma pergunta para a pessoa
        assert flow.variables == []


def test_analise_sugere_intencoes_variaveis_e_passos_sem_volta(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    gravacao = gravacao_relatorio("https://portal.exemplo")
    gravacao["steps"].append(
        {"action": "click", "target": {"role": "button", "text": "Enviar declaração"}}
    )
    flow_id = api.post("/api/v1/flows", json=gravacao, headers=autenticado).json()["id"]

    with fabrica_sessao() as sessao:
        assert analyze_next_flow(sessao) is True
        assert analyze_next_flow(sessao) is False  # a fila ficou vazia

    tarefa = api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).json()
    assert tarefa["status"] == "awaiting_confirmation"

    passos = tarefa["steps"]
    assert passos[1]["intent"] == 'Escolher "Loja"'
    assert passos[3]["postcondition"] == {"type": "download", "extension": "pdf"}
    assert passos[1]["postcondition"] == {"type": "field_value"}
    assert passos[4]["irreversible"] is True
    assert passos[3]["irreversible"] is False

    variaveis = {variavel["name"]: variavel for variavel in tarefa["variables"]}
    assert variaveis["loja"]["source"] == "column"
    assert variaveis["loja"]["example"] == "Loja 01 - Shopping Norte"
    assert variaveis["mes"]["source"] == "previous_month"


class _IaFalsa:
    def __init__(self, resposta: dict[str, Any] | Exception) -> None:
        self.resposta = resposta
        self.pedidos: list[str] = []

    def chat_json(self, _sistema: str, usuario: str) -> dict[str, Any]:
        self.pedidos.append(usuario)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def test_ia_melhora_a_analise_e_so_pode_pedir_mais_cautela(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    gravacao = gravacao_relatorio("https://portal.exemplo")
    gravacao["steps"].append(
        {"action": "click", "target": {"role": "button", "text": "Enviar declaração"}}
    )
    flow_id = api.post("/api/v1/flows", json=gravacao, headers=autenticado).json()["id"]

    ia = _IaFalsa(
        {
            "passos": [
                {"posicao": 2, "intencao": "Escolher a loja do relatório", "sem_volta": False},
                # A página poderia enganar a IA para dizer que enviar é seguro
                {"posicao": 5, "intencao": "Enviar", "sem_volta": False},
            ]
        }
    )
    with fabrica_sessao() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id), ia)

    passos = api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).json()["steps"]
    assert passos[1]["intent"] == "Escolher a loja do relatório"
    assert passos[4]["irreversible"] is True

    # A IA recebeu o formato do valor, nunca o conteúdo
    assert "Shopping Norte" not in ia.pedidos[0]
    assert "09/2026" not in ia.pedidos[0]


def test_analise_segue_sem_ia_quando_ela_falha(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    gravacao = gravacao_relatorio("https://portal.exemplo")
    flow_id = api.post("/api/v1/flows", json=gravacao, headers=autenticado).json()["id"]
    with fabrica_sessao() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id), _IaFalsa(LlmUnavailableError("fora")))
    tarefa = api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).json()
    assert tarefa["status"] == "awaiting_confirmation"


def test_tarefa_so_ativa_depois_de_responder_tudo(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    gravacao = gravacao_relatorio("https://portal.exemplo")
    flow_id = api.post("/api/v1/flows", json=gravacao, headers=autenticado).json()["id"]

    # Ainda analisando
    assert api.post(f"/api/v1/flows/{flow_id}/confirm", headers=autenticado).status_code == 400

    with fabrica_sessao() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id))

    # Perguntas abertas
    resposta = api.post(f"/api/v1/flows/{flow_id}/confirm", headers=autenticado)
    assert resposta.status_code == 400
    assert "perguntas" in resposta.json()["detail"]

    tarefa = api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).json()
    variaveis = {v["name"]: v for v in tarefa["variables"]}

    # "Muda a cada vez": o passo passa a usar a variável
    url = f"/api/v1/flows/{flow_id}/variables/{variaveis['loja']['id']}/answer"
    tarefa = api.post(url, json={"is_variable": True}, headers=autenticado).json()
    assert {v["name"]: v["status"] for v in tarefa["variables"]}["loja"] == "confirmed"

    # "Não muda": deixa de ser pergunta e o valor fica fixo
    url = f"/api/v1/flows/{flow_id}/variables/{variaveis['mes']['id']}/answer"
    tarefa = api.post(url, json={"is_variable": False}, headers=autenticado).json()
    assert [v["name"] for v in tarefa["variables"]] == ["loja"]

    with fabrica_sessao() as sessao:
        flow = sessao.get(Flow, flow_id)
        assert flow.steps[1].value_template == "{loja}"
        assert flow.steps[2].value_template == "09/2026"

    ativada = api.post(f"/api/v1/flows/{flow_id}/confirm", headers=autenticado)
    assert ativada.json()["status"] == "active"
    assert api.post(f"/api/v1/flows/{flow_id}/confirm", headers=autenticado).status_code == 409


def test_editar_passo_e_caminho_inseguro(
    api: TestClient, autenticado: Cabecalho, tarefa_ativa: dict[str, Any]
) -> None:
    flow_id, passo = tarefa_ativa["id"], tarefa_ativa["steps"][3]["id"]
    url = f"/api/v1/flows/{flow_id}/steps/{passo}"

    assert (
        api.patch(url, json={"save_as": "relatorios/{loja}.pdf"}, headers=autenticado).status_code
        == 200
    )
    assert (
        api.patch(url, json={"save_as": "../../fora.pdf"}, headers=autenticado).status_code == 400
    )

    resposta = api.patch(
        url, json={"irreversible": True, "auto_confirm": True}, headers=autenticado
    )
    assert resposta.json()["steps"][3]["irreversible"] is True


def test_arquivar_tira_da_lista_e_pausa_a_agenda(
    api: TestClient, autenticado: Cabecalho, tarefa_ativa: dict[str, Any]
) -> None:
    flow_id = tarefa_ativa["id"]
    criada = api.post(
        "/api/v1/schedules",
        data={"flow_id": flow_id, "cron": "10 7 5 * *"},
        files={"file": ("a.csv", b"loja\nLoja 01 - Shopping Norte\n")},
        headers=autenticado,
    )
    assert criada.status_code == 201

    assert api.delete(f"/api/v1/flows/{flow_id}", headers=autenticado).status_code == 204
    assert api.get("/api/v1/flows", headers=autenticado).json()["total"] == 0
    assert api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).status_code == 404
    assert api.get("/api/v1/schedules", headers=autenticado).json()[0]["enabled"] is False


# Acessos


def test_acesso_salvo_nao_volta_na_resposta(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    corpo = {"domain": "Portal.Exemplo", "username": "financeiro", "password": "senha-marcada-123"}
    salvo = api.post("/api/v1/credentials", json=corpo, headers=autenticado)
    assert salvo.status_code == 201
    assert salvo.json()["domain"] == "portal.exemplo"
    assert "senha-marcada-123" not in salvo.text
    assert "financeiro" not in salvo.text

    # Salvar de novo substitui, em vez de duplicar
    api.post("/api/v1/credentials", json={**corpo, "password": "outra"}, headers=autenticado)
    lista = api.get("/api/v1/credentials", headers=autenticado)
    assert len(lista.json()) == 1
    assert "outra" not in lista.text

    assert (
        api.delete(f"/api/v1/credentials/{salvo.json()['id']}", headers=autenticado).status_code
        == 204
    )
    assert api.get("/api/v1/credentials", headers=autenticado).json() == []


# Agendas


def test_agenda_valida_horario_e_uma_por_tarefa(
    api: TestClient, autenticado: Cabecalho, tarefa_ativa: dict[str, Any]
) -> None:
    arquivo = {"file": ("a.csv", b"loja\nA\nB\n")}
    dados = {"flow_id": tarefa_ativa["id"], "timezone": "America/Fortaleza"}

    for cron in ("isto nao e cron", "* * * * *", "0 0 * * * *"):
        resposta = api.post(
            "/api/v1/schedules", data={**dados, "cron": cron}, files=arquivo, headers=autenticado
        )
        assert resposta.status_code == 400, cron

    invalido = {**dados, "cron": "10 7 5 * *", "timezone": "Marte/Olympus"}
    assert (
        api.post("/api/v1/schedules", data=invalido, files=arquivo, headers=autenticado).status_code
        == 400
    )

    criada = api.post(
        "/api/v1/schedules",
        data={**dados, "cron": "10 7 5 * *"},
        files=arquivo,
        headers=autenticado,
    )
    assert criada.status_code == 201
    assert criada.json()["row_count"] == 2

    repetida = api.post(
        "/api/v1/schedules", data={**dados, "cron": "0 8 * * *"}, files=arquivo, headers=autenticado
    )
    assert repetida.status_code == 409

    pausada = api.patch(
        f"/api/v1/schedules/{criada.json()['id']}", json={"enabled": False}, headers=autenticado
    )
    assert pausada.json()["enabled"] is False

    assert (
        api.delete(f"/api/v1/schedules/{criada.json()['id']}", headers=autenticado).status_code
        == 204
    )


# Mesa


def test_conta_nova_tem_resumo_vazio(api: TestClient, autenticado: Cabecalho) -> None:
    resumo = api.get("/api/v1/dashboard/summary", headers=autenticado).json()
    assert resumo == {
        "copies_today": 0,
        "help_requests": [],
        "highlight": None,
        "recent_runs": [],
        "upcoming": [],
    }


def test_resumo_recusa_fuso_invalido(api: TestClient, autenticado: Cabecalho) -> None:
    resposta = api.get("/api/v1/dashboard/summary?timezone=Marte/Olympus", headers=autenticado)
    assert resposta.status_code == 400


def test_estatistica_de_conta_nova_vem_zerada(api: TestClient, autenticado: Cabecalho) -> None:
    linhas = api.get("/api/v1/repairs/stats", headers=autenticado).json()
    assert [linha["steps"] for linha in linhas] == [0, 0, 0, 0]
