"""A senha salva para um site só é digitada naquele site (e nos subdomínios dele)."""

from dataclasses import dataclass

import pytest

from app.services.run_processor import RunProcessor


@dataclass
class PaginaFalsa:
    url: str


def processador(credenciais: dict[str, dict[str, str]]) -> RunProcessor:
    # Só a escolha do acesso importa aqui: nada de banco nem navegador
    processador = RunProcessor.__new__(RunProcessor)
    processador.credentials = credenciais
    return processador


BANCO = {"username": "cliente", "password": "senha-do-banco"}
TERCEIRO = {"username": "cliente", "password": "senha-do-terceiro"}


@pytest.mark.parametrize(
    ("endereco", "esperado"),
    [
        ("https://banco.exemplo/login", BANCO),
        ("https://app.banco.exemplo/entrar", BANCO),
        ("https://sso.terceiro.exemplo/login", TERCEIRO),
    ],
)
def test_cada_site_recebe_o_proprio_acesso(endereco: str, esperado: dict[str, str]) -> None:
    escolhido = processador({"banco.exemplo": BANCO, "terceiro.exemplo": TERCEIRO})._credential_for(
        PaginaFalsa(endereco)
    )
    assert escolhido == esperado


def test_senha_do_banco_nunca_vai_para_outro_site() -> None:
    """Regressão: com um único acesso salvo, a senha dele era usada em qualquer site."""
    for endereco in (
        "https://sso.terceiro.exemplo/login",
        "https://banco.exemplo.atacante.exemplo/login",
        "https://falsobanco.exemplo/login",
        "about:blank",
    ):
        assert processador({"banco.exemplo": BANCO})._credential_for(PaginaFalsa(endereco)) == {}


def test_acesso_mais_especifico_vence() -> None:
    login = {"username": "outro", "password": "senha-do-login"}
    escolhido = processador({"banco.exemplo": BANCO, "login.banco.exemplo": login})._credential_for(
        PaginaFalsa("https://login.banco.exemplo/")
    )
    assert escolhido == login
