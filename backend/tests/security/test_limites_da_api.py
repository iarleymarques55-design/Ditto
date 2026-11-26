"""Limites que protegem a API: tentativas de login, tamanho do envio e planilhas que explodem."""

import io
import zipfile
from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core import rate_limit
from app.core.config import Settings, settings
from app.core.exceptions import PayloadTooLargeError, RateLimitedError
from app.core.rate_limit import RateLimiter
from app.main import create_app
from app.services.batch import parse_rows

Cabecalho = dict[str, str]
SENHA = "senha-longa-de-teste"


# Limite de tentativas


def test_chaves_antigas_saem_da_memoria(monkeypatch: pytest.MonkeyPatch) -> None:
    # Relógio que anda 1 s a cada consulta: o do Windows só avança a cada ~15 ms, e várias
    # chaves ficavam com o mesmo instante
    relogio = iter(range(1, 10_000_000))
    monkeypatch.setattr(rate_limit, "time", SimpleNamespace(monotonic=lambda: float(next(relogio))))
    limitador = RateLimiter()
    # Janela de 0 s: toda chave já está vencida na volta seguinte
    for numero in range(5000):
        limitador.check(f"login:pessoa{numero}@teste.com", 10, 0)
    assert limitador.size() < 1000


def test_limite_continua_valendo_dentro_da_janela() -> None:
    limitador = RateLimiter()
    for _ in range(3):
        limitador.check("chave", 3, 60)
    with pytest.raises(RateLimitedError):
        limitador.check("chave", 3, 60)


def test_errar_a_senha_de_outro_ip_nao_trava_a_dona_da_conta(
    api: TestClient,
    criar_conta: Callable[..., Cabecalho],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    criar_conta(email="ana@teste.com")

    def entrar(ip: str, senha: str) -> int:
        return api.post(
            "/api/v1/auth/login",
            json={"email": "ana@teste.com", "password": senha},
            headers={"X-Forwarded-For": ip},
        ).status_code

    for _ in range(10):
        assert entrar("203.0.113.9", "senha-errada") == 401
    # Quem está tentando adivinhar fica travado
    assert entrar("203.0.113.9", SENHA) == 429
    # A dona, de outro lugar, continua entrando
    assert entrar("198.51.100.4", SENHA) == 200


# Tamanho do envio


def _em_partes(tamanho: int, parte: int = 64 * 1024) -> Iterator[bytes]:
    enviado = 0
    while enviado < tamanho:
        pedaco = min(parte, tamanho - enviado)
        enviado += pedaco
        yield b"a" * pedaco


def test_envio_em_partes_acima_do_limite_e_cortado(client: TestClient) -> None:
    # Sem Content-Length (Transfer-Encoding: chunked): antes passava direto pelo limite
    resposta = client.post(
        "/api/v1/auth/login",
        content=_em_partes(settings.max_body_bytes + 1024),
        headers={"Content-Type": "application/json"},
    )
    assert resposta.status_code == 413
    assert resposta.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_envio_declarado_acima_do_limite_e_cortado(client: TestClient) -> None:
    resposta = client.post(
        "/api/v1/auth/login",
        content=b"a" * (settings.max_body_bytes + 1),
        headers={"Content-Type": "application/json"},
    )
    assert resposta.status_code == 413


def test_envio_pequeno_em_partes_passa(client: TestClient) -> None:
    resposta = client.post(
        "/api/v1/auth/login",
        content=_em_partes(200),
        headers={"Content-Type": "application/json"},
    )
    # JSON inválido: chega até a validação, que responde 422
    assert resposta.status_code == 422


# Cabeçalhos e modo padrão


def test_respostas_nao_ficam_em_cache(client: TestClient) -> None:
    resposta = client.get("/api/v1/auth/me")
    assert resposta.headers["Cache-Control"] == "no-store"
    # Em desenvolvimento (HTTP comum) o HSTS não faz sentido
    assert "Strict-Transport-Security" not in resposta.headers


def test_producao_manda_hsts_e_fecha_a_documentacao() -> None:
    producao = Settings(environment="production", allow_private_networks=False, bcrypt_rounds=12)
    with TestClient(create_app(producao), raise_server_exceptions=False) as cliente:
        resposta = cliente.get("/api/v1/auth/me")
        assert resposta.headers["Strict-Transport-Security"].startswith("max-age=")
        assert cliente.get("/docs").status_code == 404
        assert cliente.get("/openapi.json").status_code == 404


def test_sem_environment_o_padrao_e_producao() -> None:
    assert Settings.model_fields["environment"].default == "production"


def test_ip_atras_de_proxy_usa_o_mesmo_calculo_no_rele(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    assert rate_limit.ip_behind_proxies("10.0.0.1", "1.1.1.1, 203.0.113.9") == "203.0.113.9"
    assert rate_limit.ip_behind_proxies("10.0.0.1", "") == "10.0.0.1"
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    assert rate_limit.ip_behind_proxies("10.0.0.1", "203.0.113.9") == "10.0.0.1"


# Planilha que explode ao abrir


def test_planilha_bomba_de_descompressao_e_recusada_antes_de_abrir() -> None:
    livro = Workbook()
    livro.active.append(["cnpj"])
    original = io.BytesIO()
    livro.save(original)

    bomba = io.BytesIO()
    with (
        zipfile.ZipFile(original) as origem,
        zipfile.ZipFile(bomba, "w", zipfile.ZIP_DEFLATED) as destino,
    ):
        for item in origem.infolist():
            destino.writestr(item, origem.read(item.filename))
        # 80 MB de texto repetido viram poucos KB comprimidos
        destino.writestr("xl/bomba.xml", b"a" * (80 * 1024 * 1024))
    conteudo = bomba.getvalue()
    assert len(conteudo) < settings.max_upload_bytes

    with pytest.raises(PayloadTooLargeError):
        parse_rows("lote.xlsx", conteudo, ["cnpj"])


def test_planilha_normal_continua_sendo_lida() -> None:
    livro = Workbook()
    livro.active.append(["CNPJ"])
    livro.active.append(["12.345.678/0001-90"])
    arquivo = io.BytesIO()
    livro.save(arquivo)

    assert parse_rows("lote.xlsx", arquivo.getvalue(), ["cnpj"]) == [{"cnpj": "12.345.678/0001-90"}]
