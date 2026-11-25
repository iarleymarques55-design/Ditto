"""A espera entre os passos: segura até a página parar, sem fotografá-la várias vezes."""

import time
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from app.services.engine.postcondition import wait_until_quiet

QUIETO = 0.5
MAXIMO = 3.0


@pytest.fixture
def pagina(navegador: Browser) -> Iterator[Page]:
    page = navegador.new_page()
    yield page
    page.close()


def _esperar(page: Page, **extra) -> float:
    inicio = time.monotonic()
    wait_until_quiet(page, quiet_seconds=QUIETO, max_seconds=MAXIMO, **extra)
    return time.monotonic() - inicio


def test_pagina_parada_libera_logo(pagina: Page) -> None:
    pagina.set_content("<button>Salvar</button>")

    gasto = _esperar(pagina)

    # Mesmo parada, espera o mínimo depois da ação: o site pode responder um instante depois
    assert QUIETO <= gasto < QUIETO + 1


def test_espera_a_resposta_que_chega_depois(pagina: Page) -> None:
    pagina.set_content(
        "<p id='situacao'>Salvando</p>"
        "<script>setTimeout(() => situacao.textContent = 'Salvo', 400)</script>"
    )

    _esperar(pagina)

    # Sem perceber a mudança, a espera liberaria antes do "Salvo" aparecer
    assert pagina.text_content("#situacao") == "Salvo"


def test_pagina_que_nunca_para_custa_so_o_maximo(pagina: Page) -> None:
    pagina.set_content(
        "<p id='relogio'></p><script>setInterval(() => relogio.textContent = Date.now(), 50)</script>"
    )

    gasto = _esperar(pagina)

    assert MAXIMO - 0.2 <= gasto < MAXIMO + 1


def test_animacao_de_estilo_nao_segura(pagina: Page) -> None:
    # Um carrossel mexendo só no estilo não pode fazer todo passo esperar o máximo
    pagina.set_content(
        "<div id='faixa'></div>"
        "<script>setInterval(() => faixa.style.left = Math.random() * 100 + 'px', 30)</script>"
    )

    gasto = _esperar(pagina)

    assert gasto < QUIETO + 1


def test_mudanca_dentro_de_iframe_tambem_segura(pagina: Page) -> None:
    pagina.set_content(
        "<iframe srcdoc=\"<p id='r'></p><script>setInterval(() => r.textContent = Date.now(), 50)</script>\"></iframe>"
    )
    pagina.wait_for_timeout(200)

    gasto = _esperar(pagina)

    assert gasto >= MAXIMO - 0.2


def test_rede_ocupada_segura(pagina: Page) -> None:
    pagina.set_content("<p>pronto</p>")
    pedidos = {"abertos": True}

    def ocupado() -> bool:
        return pedidos["abertos"]

    inicio = time.monotonic()
    wait_until_quiet(pagina, busy=ocupado, quiet_seconds=QUIETO, max_seconds=1.0)

    assert time.monotonic() - inicio >= 0.9


def test_nao_le_o_texto_da_pagina(pagina: Page) -> None:
    pagina.set_content("<p>CPF 123.456.789-09</p>")
    pagina.evaluate("window.__lido = false")
    # A espera não pode tocar no texto: troca innerText por uma armadilha
    pagina.evaluate(
        """() => Object.defineProperty(HTMLElement.prototype, 'innerText', {
             get() { window.__lido = true; return '' }
           })"""
    )

    _esperar(pagina)

    assert pagina.evaluate("window.__lido") is False
