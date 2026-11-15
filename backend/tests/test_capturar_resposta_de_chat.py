"""Captura que espera o texto parar de mudar, como a resposta de um chat sendo escrita."""

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from app.models.enums import CaptureKind, StepAction
from app.services.engine.executor import StepPlan, StepRunner

# Um chat de mentira: cada pergunta ganha uma resposta escrita aos poucos, com um botão de
# parar visível enquanto escreve, e até uma pausa no meio, como um modelo "pensando"
CHAT = """
<div id="conversa"></div>
<button id="parar" hidden>Parar</button>
<div id="caixa" contenteditable="true" style="width:300px;height:24px;border:1px solid"></div>
<script>
  const respostas = [
    'Automação de tarefas no navegador repete cliques e digitação por você.',
    'Em uma frase: o navegador trabalha sozinho.',
  ]
  const caixa = document.getElementById('caixa')
  const parar = document.getElementById('parar')
  caixa.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Enter') return
    evento.preventDefault()
    const pergunta = document.createElement('p')
    pergunta.className = 'pessoa'
    pergunta.textContent = caixa.innerText
    document.getElementById('conversa').append(pergunta)
    caixa.innerText = ''

    const resposta = document.createElement('p')
    resposta.className = 'assistente'
    document.getElementById('conversa').append(resposta)
    const texto = respostas.shift()
    parar.hidden = false
    let letra = 0
    const escrever = () => {
      resposta.textContent = texto.slice(0, ++letra)
      if (letra < texto.length) setTimeout(escrever, letra === 10 ? 900 : 25)
      else parar.hidden = true
    }
    setTimeout(escrever, 300)
  })
</script>
"""

ESPERA = {
    "type": "text_stable",
    "quiet_seconds": 0.5,
    "timeout_seconds": 20,
    "busy_css": "#parar",
}


def perguntar(texto: str) -> StepPlan:
    return StepPlan(
        position=1,
        action=StepAction.FILL,
        intent=f"perguntar {texto}",
        postcondition={"type": "none"},
        value=f"{texto}\n",
        url=None,
        irreversible=False,
        targets=[{"css": "#caixa"}],
        allowed_domains=["localhost"],
    )


def ler_resposta(indice: int) -> StepPlan:
    return StepPlan(
        position=2,
        action=StepAction.CAPTURE,
        intent=f"ler a resposta {indice + 1}",
        postcondition=ESPERA,
        value=None,
        url=None,
        irreversible=False,
        targets=[{"css": "p.assistente", "index": indice}],
        allowed_domains=["localhost"],
        capture_kind=CaptureKind.VALUE,
    )


@pytest.fixture
def pagina(navegador: Browser) -> Iterator[Page]:
    contexto = navegador.new_context()
    page = contexto.new_page()
    page.set_content(CHAT)
    yield page
    contexto.close()


def test_le_cada_resposta_inteira_so_depois_que_o_chat_termina(pagina: Page) -> None:
    runner = StepRunner(pagina)

    assert runner.run(perguntar("O que é automação de tarefas?")).status == "ok"
    primeira = runner.run(ler_resposta(0))
    assert primeira.status == "ok"
    assert primeira.captured == (
        "Automação de tarefas no navegador repete cliques e digitação por você."
    )

    # A segunda captura não pode devolver a primeira resposta, que já está parada na tela
    assert runner.run(perguntar("Resuma em uma frase.")).status == "ok"
    segunda = runner.run(ler_resposta(1))
    assert segunda.status == "ok"
    assert segunda.captured == "Em uma frase: o navegador trabalha sozinho."


def test_texto_que_nunca_para_de_mudar_pede_ajuda(pagina: Page) -> None:
    pagina.set_content(
        '<p class="assistente">0</p>'
        "<script>let n = 0; setInterval(() => "
        "document.querySelector('.assistente').textContent = ++n, 100)</script>"
    )
    plano = ler_resposta(0)
    plano.postcondition = {**ESPERA, "timeout_seconds": 2}
    resultado = StepRunner(pagina).run(plano)
    assert resultado.status == "needs_human"
    assert "não parou de mudar" in resultado.message
