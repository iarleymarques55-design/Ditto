"""Bateria da skill backend-python: autenticação, acesso cruzado, injeção, entrada inválida e vazamentos."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Browser, Playwright
from playwright.sync_api import Error as PlaywrightError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.main import app
from app.models.flow import Flow
from app.models.user import User
from app.services.engine.browser import launch_browser, new_guarded_context
from app.services.engine.egress_proxy import EgressProxy
from app.services.worker_tasks import process_next_run
from tests.conftest import gravacao_relatorio
from tests.fixtures.portal import Portal

Cabecalho = dict[str, str]
UUID_QUALQUER = "00000000-0000-4000-8000-000000000000"
ROTAS_PUBLICAS = {
    "/api/v1/health",
    "/api/v1/health/db",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/google",
}
INJECOES = ["' OR 1=1 --", "'; DROP TABLE users; --", '" OR ""="', "<script>alert(1)</script>"]


def _rotas_protegidas() -> list[tuple[str, str]]:
    rotas = []
    for caminho, operacoes in app.openapi()["paths"].items():
        if caminho in ROTAS_PUBLICAS:
            continue
        for metodo in operacoes:
            rotas.append((metodo.upper(), caminho))
    return rotas


def _preencher(caminho: str) -> str:
    partes = [UUID_QUALQUER if p.startswith("{") else p for p in caminho.split("/")]
    return "/".join(partes)


@pytest.mark.parametrize(("metodo", "caminho"), _rotas_protegidas())
def test_toda_rota_protegida_recusa_sem_token(metodo: str, caminho: str, api: TestClient) -> None:
    resposta = api.request(metodo, _preencher(caminho))
    assert resposta.status_code == 401, f"{metodo} {caminho}"
    assert resposta.json()["code"] == "UNAUTHORIZED"


def test_existem_rotas_protegidas_suficientes_no_teste() -> None:
    # Se a descoberta de rotas quebrar, o teste acima passaria sem testar nada
    assert len(_rotas_protegidas()) >= 25


def _token(**campos: Any) -> str:
    agora = datetime.now(UTC)
    corpo = {"sub": UUID_QUALQUER, "iat": agora, "exp": agora + timedelta(hours=1), **campos}
    return jwt.encode(corpo, settings.jwt_secret.get_secret_value(), algorithm="HS256")


@pytest.mark.parametrize(
    "token",
    [
        "isto-nao-e-um-token",
        jwt.encode(
            {"sub": UUID_QUALQUER}, "chave-errada-com-tamanho-suficiente-aqui", algorithm="HS256"
        ),
        # Algoritmo "none": a assinatura precisa ser exigida
        jwt.encode({"sub": UUID_QUALQUER}, "", algorithm="none"),
    ],
)
def test_token_invalido_e_recusado(token: str, api: TestClient) -> None:
    resposta = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 401


def test_token_vencido_e_recusado(api: TestClient, criar_conta: Callable[..., Cabecalho]) -> None:
    criar_conta()
    vencido = _token(exp=datetime.now(UTC) - timedelta(minutes=1))
    assert (
        api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {vencido}"}).status_code
        == 401
    )


def test_token_sem_validade_e_recusado(api: TestClient) -> None:
    sem_exp = jwt.encode(
        {"sub": UUID_QUALQUER}, settings.jwt_secret.get_secret_value(), algorithm="HS256"
    )
    assert (
        api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {sem_exp}"}).status_code
        == 401
    )


def test_token_de_conta_apagada_e_recusado(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    with fabrica_sessao() as sessao:
        sessao.delete(sessao.query(User).one())
        sessao.commit()
    assert api.get("/api/v1/auth/me", headers=autenticado).status_code == 401


def test_acesso_cruzado_entre_contas_responde_404(
    api: TestClient,
    autenticado: Cabecalho,
    criar_conta: Callable[..., Cabecalho],
    tarefa_ativa: dict[str, Any],
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    portal: Portal,
) -> None:
    """A conta B tenta tudo nos recursos da conta A. Responde como se não existissem."""
    portal.layout = "ambiguo"
    flow_id = tarefa_ativa["id"]
    passo_id = tarefa_ativa["steps"][3]["id"]

    run_id = api.post(
        "/api/v1/runs",
        data={"flow_id": flow_id},
        files={"file": ("a.csv", b"loja\nLoja 01 - Shopping Norte\n")},
        headers=autenticado,
    ).json()["id"]
    process_next_run(fabrica_sessao, navegador)

    detalhe = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()
    artefato = detalhe["items"][0]["screenshot_artifact_id"]
    pedido = api.get("/api/v1/help-requests", headers=autenticado).json()[0]["id"]
    credencial = api.post(
        "/api/v1/credentials", json={"domain": "localhost", "password": "x"}, headers=autenticado
    ).json()["id"]
    agenda = api.post(
        "/api/v1/schedules",
        data={"flow_id": flow_id, "cron": "10 7 5 * *"},
        files={"file": ("a.csv", b"loja\nA\n")},
        headers=autenticado,
    ).json()["id"]

    b = criar_conta()
    tentativas = [
        ("GET", f"/api/v1/flows/{flow_id}", None),
        ("PATCH", f"/api/v1/flows/{flow_id}", {"name": "roubada"}),
        ("DELETE", f"/api/v1/flows/{flow_id}", None),
        ("PATCH", f"/api/v1/flows/{flow_id}/steps/{passo_id}", {"irreversible": False}),
        ("POST", f"/api/v1/flows/{flow_id}/confirm", None),
        (
            "POST",
            f"/api/v1/flows/{flow_id}/variables/{tarefa_ativa['variables'][0]['id']}/answer",
            {"is_variable": False},
        ),
        ("GET", f"/api/v1/runs/{run_id}", None),
        ("POST", f"/api/v1/runs/{run_id}/cancel", None),
        ("GET", f"/api/v1/runs/{run_id}/report", None),
        ("GET", f"/api/v1/runs/{run_id}/export", None),
        ("GET", f"/api/v1/artifacts/{artefato}", None),
        ("POST", f"/api/v1/help-requests/{pedido}/answer", {"action": "skip"}),
        ("DELETE", f"/api/v1/credentials/{credencial}", None),
        ("PATCH", f"/api/v1/schedules/{agenda}", {"enabled": False}),
        ("DELETE", f"/api/v1/schedules/{agenda}", None),
    ]
    for metodo, caminho, corpo in tentativas:
        resposta = api.request(metodo, caminho, json=corpo, headers=b)
        assert resposta.status_code == 404, f"{metodo} {caminho}: {resposta.status_code}"

    # B não consegue disparar nem agendar a tarefa de A
    dados = {"flow_id": flow_id}
    arquivo = {"file": ("a.csv", b"loja\nA\n")}
    assert api.post("/api/v1/runs", data=dados, files=arquivo, headers=b).status_code == 404
    assert (
        api.post(
            "/api/v1/schedules", data={**dados, "cron": "0 8 * * *"}, files=arquivo, headers=b
        ).status_code
        == 404
    )

    # As listagens de B vêm vazias
    assert api.get("/api/v1/flows", headers=b).json()["total"] == 0
    assert api.get("/api/v1/runs", headers=b).json()["total"] == 0
    assert api.get("/api/v1/repairs", headers=b).json()["total"] == 0
    assert api.get("/api/v1/help-requests", headers=b).json() == []
    assert api.get("/api/v1/credentials", headers=b).json() == []
    assert api.get("/api/v1/schedules", headers=b).json() == []
    resumo = api.get("/api/v1/dashboard/summary", headers=b).json()
    assert resumo["highlight"] is None
    assert resumo["recent_runs"] == []
    assert api.get(f"/api/v1/runs?flow_id={flow_id}", headers=b).json()["total"] == 0

    # Nada mudou para A
    assert api.get(f"/api/v1/flows/{flow_id}", headers=autenticado).json()["name"] != "roubada"
    assert len(api.get("/api/v1/credentials", headers=autenticado).json()) == 1


def test_mesma_credencial_de_dominio_nao_vaza_entre_contas(
    api: TestClient, criar_conta: Callable[..., Cabecalho], fabrica_sessao: sessionmaker[Session]
) -> None:
    a, b = criar_conta(), criar_conta()
    assert (
        api.post(
            "/api/v1/credentials", json={"domain": "portal.exemplo", "password": "de-a"}, headers=a
        ).status_code
        == 201
    )
    assert (
        api.post(
            "/api/v1/credentials", json={"domain": "portal.exemplo", "password": "de-b"}, headers=b
        ).status_code
        == 201
    )
    assert len(api.get("/api/v1/credentials", headers=a).json()) == 1


@pytest.mark.parametrize("carga", INJECOES)
def test_injecao_em_login_e_parametros_nao_quebra(
    carga: str, api: TestClient, autenticado: Cabecalho
) -> None:
    login = api.post("/api/v1/auth/login", json={"email": "a@teste.com", "password": carga})
    assert login.status_code == 401

    consulta = api.get("/api/v1/dashboard/summary", params={"timezone": carga}, headers=autenticado)
    assert consulta.status_code in {400, 422}

    uuid_invalido = api.get(f"/api/v1/flows/{carga.replace('/', '')}", headers=autenticado)
    assert uuid_invalido.status_code in {404, 422}


def test_injecao_em_nome_fica_so_como_texto(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    gravacao = gravacao_relatorio("https://portal.exemplo", name="'; DROP TABLE users; --")
    criada = api.post("/api/v1/flows", json=gravacao, headers=autenticado)
    assert criada.status_code == 201
    assert criada.json()["name"] == "'; DROP TABLE users; --"
    # A tabela continua lá
    with fabrica_sessao() as sessao:
        assert sessao.query(User).count() == 1


def test_campo_que_a_pessoa_nao_controla_e_recusado_no_cadastro(api: TestClient) -> None:
    corpo = {"name": "A", "email": "a@teste.com", "password": "senha-longa", "is_admin": True}
    assert api.post("/api/v1/auth/register", json=corpo).status_code == 422


@pytest.mark.parametrize(
    "extra",
    [{"owner_id": UUID_QUALQUER}, {"status": "active"}, {"id": UUID_QUALQUER}],
)
def test_mass_assignment_em_tarefa_e_recusado(
    extra: dict[str, str],
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: sessionmaker[Session],
) -> None:
    gravacao = {**gravacao_relatorio("https://portal.exemplo"), **extra}
    assert api.post("/api/v1/flows", json=gravacao, headers=autenticado).status_code == 422

    criada = api.post(
        "/api/v1/flows", json=gravacao_relatorio("https://portal.exemplo"), headers=autenticado
    )
    resposta = api.patch(f"/api/v1/flows/{criada.json()['id']}", json=extra, headers=autenticado)
    assert resposta.status_code == 422


def test_tarefa_nao_ativa_sem_passar_pela_revisao(
    api: TestClient, autenticado: Cabecalho, fabrica_sessao: sessionmaker[Session]
) -> None:
    criada = api.post(
        "/api/v1/flows", json=gravacao_relatorio("https://portal.exemplo"), headers=autenticado
    ).json()
    resposta = api.post(
        "/api/v1/runs",
        data={"flow_id": criada["id"]},
        files={"file": ("a.csv", b"loja\nA\n")},
        headers=autenticado,
    )
    assert resposta.status_code == 400
    with fabrica_sessao() as sessao:
        assert sessao.get(Flow, criada["id"]).status.value == "analyzing"


def test_erro_de_validacao_nao_devolve_a_senha(api: TestClient) -> None:
    corpo = {"name": "A", "email": "nao-e-email", "password": "senha-marcada-123"}
    resposta = api.post("/api/v1/auth/register", json=corpo)
    assert resposta.status_code == 422
    assert "senha-marcada-123" not in resposta.text
    assert resposta.json()["code"] == "VALIDATION_ERROR"
    assert isinstance(resposta.json()["detail"], str)


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"name": "A"},
        {"name": "", "email": "a@teste.com", "password": "senha-longa"},
        {"name": "A", "email": "a@teste.com", "password": "curta"},
        {"name": "A", "email": "a@teste.com", "password": "x" * 73},
        {"name": "A" * 121, "email": "a@teste.com", "password": "senha-longa"},
        {"name": 123, "email": ["x"], "password": None},
    ],
)
def test_cadastro_invalido_responde_422(corpo: dict[str, Any], api: TestClient) -> None:
    assert api.post("/api/v1/auth/register", json=corpo).status_code == 422


@pytest.mark.parametrize(
    "corpo",
    [
        {
            "name": "x",
            "start_url": "javascript:alert(1)",
            "steps": [{"action": "click", "target": {}}],
        },
        {
            "name": "x",
            "start_url": "file:///etc/passwd",
            "steps": [{"action": "click", "target": {}}],
        },
        {"name": "x", "start_url": "https://a.exemplo", "steps": []},
        {"name": "x", "start_url": "https://a.exemplo", "steps": [{"action": "click"}]},
        {"name": "x", "start_url": "https://a.exemplo", "steps": [{"action": "navigate"}]},
        {
            "name": "x",
            "start_url": "https://a.exemplo",
            "steps": [{"action": "navigate", "url": "file:///etc/passwd"}],
        },
        {
            "name": "x",
            "start_url": "https://a.exemplo",
            "steps": [{"action": "explodir", "target": {}}],
        },
        {
            "name": "x",
            "start_url": "https://a.exemplo",
            "steps": [{"action": "click", "target": {"role": "a"}}] * 201,
        },
    ],
)
def test_gravacao_invalida_responde_422(
    corpo: dict[str, Any], api: TestClient, autenticado: Cabecalho
) -> None:
    assert api.post("/api/v1/flows", json=corpo, headers=autenticado).status_code == 422


@pytest.mark.parametrize("dominio", ["localhost:8080", "http://a.com", "a b.com", "../..", ""])
def test_dominio_invalido_na_credencial(
    dominio: str, api: TestClient, autenticado: Cabecalho
) -> None:
    corpo = {"domain": dominio, "password": "x"}
    assert api.post("/api/v1/credentials", json=corpo, headers=autenticado).status_code == 422


@pytest.mark.parametrize("consulta", ["limit=101", "limit=0", "limit=-1", "offset=-1", "limit=abc"])
def test_paginacao_fora_do_limite_e_recusada(
    consulta: str, api: TestClient, autenticado: Cabecalho
) -> None:
    for rota in ("flows", "runs", "repairs", "schedules"):
        assert api.get(f"/api/v1/{rota}?{consulta}", headers=autenticado).status_code == 422


def test_listagem_e_paginada_de_verdade(api: TestClient, autenticado: Cabecalho) -> None:
    for _ in range(3):
        api.post(
            "/api/v1/flows", json=gravacao_relatorio("https://portal.exemplo"), headers=autenticado
        )
    pagina = api.get("/api/v1/flows?limit=2&offset=1", headers=autenticado).json()
    assert (len(pagina["items"]), pagina["total"], pagina["limit"], pagina["offset"]) == (
        2,
        3,
        2,
        1,
    )


def test_login_tem_limite_por_ip(api: TestClient) -> None:
    corpo = {"email": "a@teste.com", "password": "errada"}
    respostas = [
        api.post("/api/v1/auth/login", json={**corpo, "email": f"p{i}@teste.com"})
        for i in range(21)
    ]
    assert respostas[-1].status_code == 429
    assert respostas[-1].json()["code"] == "RATE_LIMITED"


def test_login_tem_limite_por_conta(api: TestClient) -> None:
    corpo = {"email": "a@teste.com", "password": "errada"}
    respostas = [api.post("/api/v1/auth/login", json=corpo) for _ in range(11)]
    assert respostas[-1].status_code == 429


def test_cadastro_tem_limite(api: TestClient) -> None:
    respostas = [
        api.post(
            "/api/v1/auth/register",
            json={"name": "A", "email": f"p{i}@teste.com", "password": "senha-longa"},
        )
        for i in range(11)
    ]
    assert respostas[-1].status_code == 429


def test_corpo_gigante_e_recusado_antes_de_ser_lido(
    api: TestClient, autenticado: Cabecalho
) -> None:
    resposta = api.post(
        "/api/v1/flows",
        content=b"{}",
        headers={
            **autenticado,
            "Content-Type": "application/json",
            "Content-Length": str(settings.max_body_bytes + 1),
        },
    )
    assert resposta.status_code == 413


def test_respostas_tem_cabecalhos_de_seguranca(api: TestClient) -> None:
    resposta = api.get("/api/v1/health")
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert resposta.headers["x-frame-options"] == "DENY"


def test_cors_nao_aceita_qualquer_origem() -> None:
    assert "*" not in settings.cors_origins


def test_resposta_nunca_traz_hash_nem_campos_internos(
    api: TestClient, autenticado: Cabecalho
) -> None:
    eu = api.get("/api/v1/auth/me", headers=autenticado)
    assert set(eu.json()) == {"id", "name", "email", "has_password", "avatar_id", "email_alerts"}


def test_producao_nao_aceita_acesso_a_rede_interna() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="ALLOW_PRIVATE_NETWORKS"):
        Settings(environment="production", allow_private_networks=True)


def test_jwt_secret_curto_impede_a_api_de_iniciar() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(jwt_secret="curto")


def test_navegador_nao_sai_dos_dominios_da_tarefa(navegador: Browser, portal: Portal) -> None:
    """Rede real: o filtro de requisições segura a navegação e os redirecionamentos."""
    contexto = new_guarded_context(navegador, ["localhost"])
    pagina = contexto.new_page()
    try:
        pagina.goto(f"{portal.url}/relatorios")
        assert "Relatórios" in pagina.content()

        with pytest.raises(Exception, match="BLOCKED|blocked"):
            pagina.goto(f"http://127.0.0.1:{portal.port}/relatorios")
        assert portal.requests.count("/relatorios") == 1
    finally:
        contexto.close()


def _so_localhost(host: str, _endereco: str) -> bool:
    """O portal roda em localhost: nesta política, "localhost" é público e 127.0.0.1 é a rede interna."""
    return host == "localhost"


def test_redirecionamento_para_a_rede_interna_e_barrado(
    portal: Portal, playwright_teste: Playwright
) -> None:
    """Regressão: o filtro do Playwright não vê redirecionamentos, e isso chegava à rede interna."""
    proxy = EgressProxy(_so_localhost)
    navegador = launch_browser(playwright_teste, proxy)
    pagina = new_guarded_context(navegador, ["localhost", "127.0.0.1"]).new_page()
    try:
        with pytest.raises(PlaywrightError):
            pagina.goto(f"{portal.url}/redireciona-interno")
    finally:
        navegador.close()
        proxy.stop()

    assert "/redireciona-interno" in portal.requests
    assert "/metadados-da-nuvem" not in portal.requests


def test_subrecurso_da_pagina_nao_alcanca_a_rede_interna(
    portal: Portal, playwright_teste: Playwright
) -> None:
    proxy = EgressProxy(_so_localhost)
    navegador = launch_browser(playwright_teste, proxy)
    pagina = new_guarded_context(navegador, ["localhost"]).new_page()
    try:
        pagina.goto(f"{portal.url}/subrecurso-interno")
        assert "Página" in pagina.content()
    finally:
        navegador.close()
        proxy.stop()

    assert "/subrecurso-interno" in portal.requests
    assert "/imagem-interna" not in portal.requests


def test_proxy_recusa_a_rede_interna_na_politica_de_producao(
    portal: Portal, playwright_teste: Playwright, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.engine.egress_proxy.settings.allow_private_networks", False)
    proxy = EgressProxy()
    navegador = launch_browser(playwright_teste, proxy)
    pagina = new_guarded_context(navegador, ["localhost"]).new_page()
    try:
        with pytest.raises(PlaywrightError):
            pagina.goto(f"{portal.url}/relatorios")
    finally:
        navegador.close()
        proxy.stop()

    assert "/relatorios" not in portal.requests


def test_redirecionamento_para_fora_nao_conta_como_sucesso(
    api: TestClient,
    autenticado: Cabecalho,
    fabrica_sessao: sessionmaker[Session],
    navegador: Browser,
    portal: Portal,
) -> None:
    from app.services.analyzer import analyze_flow

    gravacao = {
        "name": "Redireciona",
        "start_url": f"{portal.url}/redireciona",
        "steps": [{"action": "navigate", "url": f"{portal.url}/redireciona"}],
    }
    flow_id = api.post("/api/v1/flows", json=gravacao, headers=autenticado).json()["id"]
    with fabrica_sessao() as sessao:
        analyze_flow(sessao, sessao.get(Flow, flow_id))
    api.post(f"/api/v1/flows/{flow_id}/confirm", headers=autenticado)
    run_id = api.post("/api/v1/runs", data={"flow_id": flow_id}, headers=autenticado).json()["id"]

    process_next_run(fabrica_sessao, navegador)

    execucao = api.get(f"/api/v1/runs/{run_id}", headers=autenticado).json()
    assert execucao["items"][0]["status"] == "failed"
    assert execucao["status"] == "failed"


def test_swagger_documenta_cada_rota_e_campo(api: TestClient) -> None:
    documento = app.openapi()
    faltando = []
    for caminho, operacoes in documento["paths"].items():
        for metodo, operacao in operacoes.items():
            if not operacao.get("summary") or not operacao.get("description"):
                faltando.append(f"{metodo} {caminho}: summary/description")
            if not operacao.get("tags"):
                faltando.append(f"{metodo} {caminho}: tags")
            for parametro in operacao.get("parameters", []):
                if not parametro.get("description"):
                    faltando.append(f"{metodo} {caminho}: {parametro['name']}")

    for nome, esquema in documento["components"]["schemas"].items():
        if nome.startswith(("HTTPValidationError", "ValidationError", "Body_")):
            continue
        for campo, definicao in esquema.get("properties", {}).items():
            if not definicao.get("description"):
                faltando.append(f"schema {nome}.{campo}")

    assert faltando == []


def test_nenhum_segredo_de_configuracao_aparece_no_repr() -> None:
    texto = repr(settings)
    assert settings.jwt_secret.get_secret_value() not in texto
    assert settings.fernet_keys.get_secret_value() not in texto
