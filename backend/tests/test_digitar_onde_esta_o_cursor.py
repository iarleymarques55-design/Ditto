"""Passos de teclado sem alvo: digitam onde o cursor está, como numa planilha desenhada em canvas."""

import json
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from app.models.enums import StepAction
from app.services.engine.executor import FOCUSED_TARGET, StepPlan, StepRunner, is_focused_target

# A grade não é campo de texto: só um elemento que recebe as teclas e "grava" na célula ativa
GRADE = """
<canvas id="grade" tabindex="0" width="300" height="100"></canvas>
<ol id="celulas"></ol>
<script>
  let atual = ''
  const grade = document.getElementById('grade')
  grade.addEventListener('keydown', (evento) => {
    if (evento.key === 'Enter' || evento.key === 'Tab') {
      const celula = document.createElement('li')
      celula.textContent = atual
      document.getElementById('celulas').append(celula)
      atual = ''
    } else if (evento.key.length === 1) {
      atual += evento.key
    }
    evento.preventDefault()
  })
  grade.focus()
</script>
"""


def plano(action: StepAction, value: str) -> StepPlan:
    return StepPlan(
        position=1,
        action=action,
        intent=f"{action} {value}",
        postcondition={"type": "none"},
        value=value,
        url=None,
        irreversible=False,
        targets=[FOCUSED_TARGET],
        allowed_domains=["localhost"],
    )


@pytest.fixture
def pagina(navegador: Browser) -> Iterator[Page]:
    contexto = navegador.new_context()
    page = contexto.new_page()
    page.set_content(GRADE)
    yield page
    contexto.close()


def test_digita_e_aperta_enter_onde_o_cursor_esta(pagina: Page) -> None:
    runner = StepRunner(pagina)
    for action, value in [
        (StepAction.FILL, "iarley"),
        (StepAction.PRESS, "Enter"),
        (StepAction.FILL, "marques"),
        (StepAction.PRESS, "Enter"),
    ]:
        resultado = runner.run(plano(action, value))
        assert resultado.status == "ok"
        assert resultado.layer == 1

    assert pagina.locator("#celulas li").all_inner_texts() == ["iarley", "marques"]


def test_tab_e_quebra_de_linha_no_texto_viram_teclas(pagina: Page) -> None:
    # Assim um passo só preenche a célula e já anda para a próxima, como numa planilha
    runner = StepRunner(pagina)
    assert runner.run(plano(StepAction.FILL, "Produto\t")).status == "ok"
    assert runner.run(plano(StepAction.FILL, "=SOMA(B2:D2)\n")).status == "ok"

    assert pagina.locator("#celulas li").all_inner_texts() == ["Produto", "=SOMA(B2:D2)"]


def test_nao_digita_com_o_cursor_num_botao(navegador: Browser) -> None:
    contexto = navegador.new_context()
    try:
        page = contexto.new_page()
        page.set_content(
            '<input id="nome">'
            '<button id="comprar" onclick="document.title=\'comprou\'">Comprar</button>'
        )
        page.focus("#comprar")
        resultado = StepRunner(page).run(plano(StepAction.PRESS, "Enter"))
        assert resultado.status == "failed"
        assert "botão" in resultado.message
        # Para investigar: onde estava o cursor, sem nenhum valor da página
        principal = resultado.diagnostics["frames"][0]
        assert principal["active"]["tag"] == "BUTTON"
        assert principal["active"]["id"] == "comprar"
        assert any(item["id"] == "nome" for item in principal["editables"])
        assert "Comprar" not in str(resultado.diagnostics)

        # O Tab leva o cursor do campo para o botão: o Enter que viria depois não acontece
        page.focus("#nome")
        resultado = StepRunner(page).run(plano(StepAction.FILL, "Março\t\n"))
        assert resultado.status == "failed"
        assert page.input_value("#nome") == "Março"
        assert page.title() != "comprou"
    finally:
        contexto.close()


def test_cursor_solto_na_pagina_para_em_vez_de_digitar_no_vazio(navegador: Browser) -> None:
    contexto = navegador.new_context()
    try:
        page = contexto.new_page()
        page.set_content('<input id="nome"><p>nada com o cursor</p>')
        resultado = StepRunner(page).run(plano(StepAction.FILL, "Produto\t"))
        assert resultado.status == "failed"
        assert "nenhum lugar onde digitar" in resultado.message
        assert resultado.diagnostics["frames"][0]["active"]["tag"] == "BODY"
        assert resultado.diagnostics["frames"][0]["visibility"] == "visible"
    finally:
        contexto.close()


def test_espera_o_site_levar_o_cursor_para_a_grade(navegador: Browser) -> None:
    contexto = navegador.new_context()
    try:
        page = contexto.new_page()
        # Como o Excel: a célula é escolhida, e o cursor só chega à grade um instante depois
        page.set_content(GRADE.replace("grade.focus()", "setTimeout(() => grade.focus(), 800)"))
        resultado = StepRunner(page).run(plano(StepAction.FILL, "iarley\n"))
        assert resultado.status == "ok"
        assert page.locator("#celulas li").all_inner_texts() == ["iarley"]
    finally:
        contexto.close()


# Imita o Excel Online: a Caixa de Nome escolhe a célula e solta o cursor; a Barra de fórmulas
# grava na célula ativa com Enter
EXCEL = """
<input id="caixa" aria-label="Caixa de Nome">
<div id="barra" role="textbox" aria-label="formula bar" contenteditable="true"
     style="width:300px;height:20px;border:1px solid"></div>
<pre id="celulas"></pre>
<script>
  const celulas = {}
  let ativa = 'A1'
  const caixa = document.getElementById('caixa')
  const barra = document.getElementById('barra')
  caixa.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Enter') return
    ativa = caixa.value.trim().toUpperCase()
    caixa.blur()
  })
  barra.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Enter') return
    evento.preventDefault()
    celulas[ativa] = barra.innerText
    barra.innerText = ''
    barra.blur()
    document.getElementById('celulas').textContent = JSON.stringify(celulas)
  })
</script>
"""


def plano_no_campo(css: str, valor: str) -> StepPlan:
    return StepPlan(
        position=1,
        action=StepAction.FILL,
        intent=f"escrever {valor!r}",
        postcondition={"type": "none"},
        value=valor,
        url=None,
        irreversible=False,
        targets=[{"css": css}],
        allowed_domains=["localhost"],
    )


def test_celula_por_celula_pela_caixa_de_nome_e_barra_de_formulas(navegador: Browser) -> None:
    contexto = navegador.new_context()
    try:
        page = contexto.new_page()
        page.set_content(EXCEL)
        runner = StepRunner(page)
        for celula, valor in [("A1", "Produto"), ("B1", "Janeiro"), ("E2", "=SOMA(B2:D2)")]:
            assert runner.run(plano_no_campo("#caixa", f"{celula}\n")).status == "ok"
            assert runner.run(plano_no_campo("#barra", f"{valor}\n")).status == "ok"

        gravadas = json.loads(page.inner_text("#celulas"))
        assert gravadas == {"A1": "Produto", "B1": "Janeiro", "E2": "=SOMA(B2:D2)"}
    finally:
        contexto.close()


def test_so_o_alvo_marcado_age_onde_o_cursor_esta() -> None:
    assert is_focused_target([FOCUSED_TARGET])
    assert not is_focused_target([])
    assert not is_focused_target([{"css": "#campo", "focused": "sim"}])
