"""A extensão de verdade, carregada no Chromium: grava o que uma pessoa faz e envia para a API."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Page, Playwright, expect

from app.core.config import BACKEND_DIR
from app.schemas.flow import RecordingCreate
from tests.fixtures.portal import Portal

ORIGEM_EXTENSAO = Path(BACKEND_DIR).parent / "extension"
ESPERA_MS = 15000


@pytest.fixture
def navegador_com_extensao(
    playwright_teste: Playwright, portal: Portal, tmp_path: Path
) -> Iterator[BrowserContext]:
    # Cópia com o portal de teste no lugar do painel: o manifest real nunca aceita esta origem
    copia = tmp_path / "extensao"
    shutil.copytree(ORIGEM_EXTENSAO, copia)
    manifest = json.loads((copia / "manifest.json").read_text(encoding="utf-8"))
    manifest["content_scripts"][0]["matches"] = [f"{portal.url}/painel-falso*"]
    (copia / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    gravador = copia / "recorder.js"
    gravador.write_text(
        gravador.read_text(encoding="utf-8").replace("mode: 'closed'", "mode: 'open'"),
        encoding="utf-8",
    )

    contexto = playwright_teste.chromium.launch_persistent_context(
        str(tmp_path / "perfil"),
        channel="chromium",
        headless=True,
        args=[f"--disable-extensions-except={copia}", f"--load-extension={copia}"],
    )
    contexto.set_default_timeout(ESPERA_MS)
    # A extensão sobe depois do navegador: uma página aberta antes disso ficaria sem a ponte
    if not contexto.service_workers:
        contexto.wait_for_event("serviceworker")
    yield contexto
    contexto.close()


def abrir_painel(contexto: BrowserContext, portal: Portal) -> Page:
    pagina = contexto.new_page()
    pagina.goto(f"{portal.url}/painel-falso")
    pagina.wait_for_timeout(200)
    return pagina


def falar_com_extensao(
    pagina: Page, tipo: str, dados: dict[str, Any] | None = None, espera_ms: int = 12000
) -> dict[str, Any] | None:
    return pagina.evaluate(
        """([tipo, dados, espera]) => new Promise((resolver) => {
            const requestId = Math.random().toString(36);
            const aoReceber = (evento) => {
              if (evento.data?.source === 'ditto-extension' && evento.data.requestId === requestId) {
                window.removeEventListener('message', aoReceber);
                resolver(evento.data);
              }
            };
            window.addEventListener('message', aoReceber);
            window.postMessage({ source: 'ditto-panel', type: tipo, requestId, payload: dados }, location.origin);
            setTimeout(() => resolver(null), espera);
        })""",
        [tipo, dados or {}, espera_ms],
    )


def iniciar_gravacao(contexto: BrowserContext, portal: Portal, caminho: str) -> Page:
    painel = abrir_painel(contexto, portal)
    with contexto.expect_page() as nova:
        resposta = falar_com_extensao(
            painel,
            "start",
            {
                "name": "Tarefa gravada",
                "startUrl": f"{portal.url}{caminho}",
                "token": "token-de-teste-da-gravacao",
                "apiUrl": f"{portal.url}/api",
                "panelUrl": portal.url,
            },
        )
    assert resposta and resposta["ok"], resposta
    aba = nova.value
    barra(aba).wait_for()
    assert caminho in aba.url
    return aba


def barra(aba: Page):
    return aba.locator("ditto-gravador .barra")


def parar_e_pegar_gravacao(aba: Page, portal: Portal) -> dict[str, Any]:
    barra(aba).get_by_role("button", name="Parar e salvar").click()
    aba.wait_for_url("**/painel/tarefas/tarefa-gravada")
    assert len(portal.recordings) == 1
    gravacao = portal.recordings[0]
    # O que a extensão envia precisa ser aceito pela API
    RecordingCreate.model_validate(gravacao)
    return gravacao


def capturar(aba: Page, seletor: str, nome: str | None = None, tabela: bool = False) -> None:
    barra(aba).get_by_role("button", name="Capturar dado").click()
    barra(aba).get_by_text("Clique no dado").wait_for()
    aba.locator(seletor).first.click()
    campo = barra(aba).locator("input[type=text]")
    campo.wait_for()
    if nome:
        campo.fill(nome)
    if tabela:
        barra(aba).get_by_label("A tabela inteira").check()
    barra(aba).get_by_role("button", name="Salvar", exact=True).click()
    barra(aba).get_by_role("button", name="Capturar dado").wait_for()


def test_painel_detecta_a_extensao(navegador_com_extensao: BrowserContext, portal: Portal) -> None:
    painel = abrir_painel(navegador_com_extensao, portal)
    assert painel.evaluate("document.documentElement.dataset.dittoExtensao") == "1.0.0"
    resposta = falar_com_extensao(painel, "ping")
    assert resposta["ok"] is True
    assert resposta["recording"] is False


def test_grava_digitacao_clique_e_captura(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/busca")

    aba.get_by_label("CNPJ").fill("111")
    aba.get_by_label("CNPJ").blur()
    aba.get_by_role("button", name="Consultar").click()
    aba.wait_for_url("**/consulta?cnpj=111")
    barra(aba).wait_for()

    capturar(aba, "dd")
    capturar(aba, "text=Razão social", "Razão social")
    capturar(aba, "td >> nth=3", "Valor da nota")
    capturar(aba, "td >> nth=0", "Notas", tabela=True)

    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert gravacao["name"] == "Tarefa gravada"
    assert gravacao["start_url"].endswith("/busca")
    assert "localhost" in gravacao["allowed_hosts"]

    passos = gravacao["steps"]
    assert [p["action"] for p in passos] == [
        "navigate",
        "fill",
        "click",
        "capture",
        "capture",
        "capture",
        "capture",
    ]
    assert passos[1]["value"] == "111"
    assert passos[1]["target"]["label"] == "CNPJ"
    assert passos[2]["target"]["text"] == "Consultar"

    # O nome vem do rótulo, e o valor não fica guardado como referência para achar o dado
    situacao = passos[3]
    assert situacao["capture_name"] == "Situação"
    assert situacao["target"]["anchor"] == "Situação"
    assert situacao["target"]["anchor_kind"] == "definition"
    assert "ATIVA" not in json.dumps(situacao)

    razao = passos[4]
    assert razao["target"]["anchor"] == "Razão social"
    assert razao["target"]["anchor_kind"] == "inline"

    celula = passos[5]
    assert celula["target"]["anchor"] == "Valor"
    assert celula["target"]["anchor_kind"] == "table_header"
    assert celula["target"]["row_index"] == 1

    notas = passos[6]
    assert notas["capture_kind"] == "table"
    assert notas["target"]["neighbors"] == ["Número", "Valor"]


def test_nunca_le_nem_envia_senha(navegador_com_extensao: BrowserContext, portal: Portal) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/login")
    aba.get_by_label("Usuário").fill("financeiro")
    aba.get_by_label("Senha").fill("senha-marcada-123")
    aba.get_by_label("Senha").press("Tab")
    aba.get_by_role("button", name="Entrar").click()
    aba.wait_for_url("**/entrou**")
    barra(aba).wait_for()

    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert "senha-marcada-123" not in json.dumps(gravacao)
    sensiveis = [p for p in gravacao["steps"] if p.get("sensitive")]
    assert len(sensiveis) == 1
    assert "value" not in sensiveis[0]


def test_nao_deixa_capturar_campo_de_senha(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/campos-sigilosos")
    barra(aba).get_by_role("button", name="Capturar dado").click()
    barra(aba).get_by_text("Clique no dado").wait_for()
    aba.locator("#senha").click()
    barra(aba).get_by_text("sigiloso").wait_for()
    assert "nao-pode-ler" not in barra(aba).inner_text()


def test_clique_para_apontar_nao_aciona_a_pagina(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/com-iframe")
    frame = aba.frame_locator("iframe")
    frame.locator("#no-iframe").wait_for()

    barra(aba).get_by_role("button", name="Capturar dado").click()
    barra(aba).get_by_text("Clique no dado").wait_for()
    frame.locator("#no-iframe").click()
    barra(aba).locator("input[type=text]").wait_for()
    assert "/clicou-no-iframe" not in portal.requests


def test_grava_dentro_de_iframe(navegador_com_extensao: BrowserContext, portal: Portal) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/com-iframe")
    aba.frame_locator("iframe").locator("#no-iframe").click()
    expect(barra(aba)).to_contain_text("2 passos")
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert gravacao["steps"][1]["target"]["text"] == "Botão no iframe"


def test_valor_capturado_vira_referencia_no_passo_seguinte(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/consulta?cnpj=111")
    capturar(aba, "dd")
    aba.goto(f"{portal.url}/erp")
    barra(aba).wait_for()
    aba.get_by_label("Situação no ERP").fill("ATIVA")
    aba.get_by_label("Situação no ERP").blur()

    gravacao = parar_e_pegar_gravacao(aba, portal)
    preenchimento = next(p for p in gravacao["steps"] if p["action"] == "fill")
    assert preenchimento["value_from_capture"] == "Situação"
    assert "value" not in preenchimento


def test_marca_o_download_no_clique(navegador_com_extensao: BrowserContext, portal: Portal) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    with aba.expect_download():
        aba.get_by_role("button", name="Exportar PDF").click()
    aba.wait_for_timeout(600)
    gravacao = parar_e_pegar_gravacao(aba, portal)
    clique = next(p for p in gravacao["steps"] if p["action"] == "click")
    assert clique["downloaded_extension"] == "pdf"


def test_janela_aberta_pelo_clique_entra_na_gravacao(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/abre-janela")
    with navegador_com_extensao.expect_page() as nova:
        aba.get_by_role("link", name="Abrir").click()
    janela = nova.value
    janela.wait_for_load_state()
    barra(janela).wait_for()
    capturar(janela, "dd")
    barra(janela).get_by_role("button", name="Parar e salvar").click()
    aba.wait_for_url("**/painel/tarefas/tarefa-gravada")
    assert [p["action"] for p in portal.recordings[0]["steps"]] == ["navigate", "click", "capture"]


def test_evento_falso_criado_pela_pagina_e_ignorado(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    # Um script malicioso da página tentando injetar passos na gravação
    aba.evaluate("document.getElementById('imprimir').click()")
    aba.evaluate(
        """() => {
            const campo = document.getElementById('mes');
            campo.value = 'injetado';
            campo.dispatchEvent(new Event('change', { bubbles: true }));
        }"""
    )
    aba.wait_for_timeout(300)
    expect(barra(aba)).to_contain_text("1 passo")


def test_abas_fora_da_gravacao_nao_recebem_nada(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/busca")
    outra = navegador_com_extensao.new_page()
    outra.goto(f"{portal.url}/relatorios")
    outra.wait_for_timeout(400)
    assert outra.locator("ditto-gravador").count() == 0
    outra.get_by_role("button", name="Imprimir").click()
    outra.close()
    expect(barra(aba)).to_contain_text("1 passo")


def test_erro_ao_enviar_mantem_a_gravacao_para_tentar_de_novo(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    portal.flows_status = 500
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    aba.get_by_role("button", name="Imprimir").click()
    barra(aba).get_by_role("button", name="Parar e salvar").click()
    barra(aba).locator(".erro").wait_for()

    portal.flows_status = 201
    parar_e_pegar_gravacao(aba, portal)


def test_sem_nada_gravado_avisa_em_vez_de_salvar(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/busca")
    barra(aba).get_by_role("button", name="Parar e salvar").click()
    barra(aba).get_by_text("Nada foi gravado").wait_for()
    assert portal.recordings == []


def test_descartar_nao_envia_nada(navegador_com_extensao: BrowserContext, portal: Portal) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    aba.get_by_role("button", name="Imprimir").click()
    aba.once("dialog", lambda dialogo: dialogo.accept())
    barra(aba).get_by_role("button", name="Descartar").click()
    barra(aba).wait_for(state="detached")
    assert portal.recordings == []


def test_uma_gravacao_de_cada_vez(navegador_com_extensao: BrowserContext, portal: Portal) -> None:
    iniciar_gravacao(navegador_com_extensao, portal, "/busca")
    painel = abrir_painel(navegador_com_extensao, portal)
    resposta = falar_com_extensao(
        painel,
        "start",
        {
            "name": "Outra",
            "startUrl": f"{portal.url}/erp",
            "token": "t",
            "apiUrl": "x",
            "panelUrl": "x",
        },
    )
    assert resposta["ok"] is False
    assert "em andamento" in resposta["error"]


def test_token_e_enviado_so_para_a_api(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    aba.get_by_role("button", name="Imprimir").click()
    # A página gravada nunca enxerga o token
    conteudo = aba.content()
    assert "token-de-teste-da-gravacao" not in conteudo
    parar_e_pegar_gravacao(aba, portal)
    assert portal.recording_auth == ["Bearer token-de-teste-da-gravacao"]


def test_enter_no_campo_grava_uma_vez_e_sem_clique_falso(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/busca-com-formulario")
    aba.get_by_label("CNPJ").fill("222")
    aba.get_by_label("CNPJ").press("Enter")
    aba.wait_for_url("**/consulta?cnpj=222")
    barra(aba).wait_for()
    aba.wait_for_timeout(300)

    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert [p["action"] for p in gravacao["steps"]] == ["navigate", "fill", "press"]
    assert gravacao["steps"][2]["value"] == "Enter"


def test_clique_de_script_nao_aciona_a_barra(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    aba.get_by_role("button", name="Imprimir").click()
    expect(barra(aba)).to_contain_text("2 passos")

    # Mesmo alcançando o botão, o que veio de um script é ignorado
    aba.evaluate(
        """() => document.querySelector('ditto-gravador').shadowRoot
            .querySelector('[data-acao=parar]').click()"""
    )
    aba.wait_for_timeout(400)
    assert portal.recordings == []
    assert barra(aba).is_visible()


def test_a_barra_entregue_e_fechada_para_a_pagina() -> None:
    assert "mode: 'closed'" in (ORIGEM_EXTENSAO / "recorder.js").read_text(encoding="utf-8")


def test_manifest_entregue_so_aceita_o_painel_local() -> None:
    manifest = json.loads((ORIGEM_EXTENSAO / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["content_scripts"][0]["matches"] == ["http://localhost:5173/*"]
    assert "externally_connectable" not in manifest


def test_avisa_que_envio_de_arquivo_nao_e_gravado(
    navegador_com_extensao: BrowserContext, portal: Portal, tmp_path: Path
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/com-arquivo")
    arquivo = tmp_path / "nota.txt"
    arquivo.write_text("x", encoding="utf-8")
    aba.locator("input[type=file]").set_input_files(arquivo)
    barra(aba).get_by_text("Envio de arquivo").wait_for()
    expect(barra(aba)).to_contain_text("1 passo")


def test_a_pagina_nao_enxerga_o_token_nem_a_mensagem_da_extensao(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    aba.evaluate(
        """() => {
            window.__mensagens = [];
            window.addEventListener('message', (e) => window.__mensagens.push(JSON.stringify(e.data)));
        }"""
    )
    aba.get_by_role("button", name="Imprimir").click()
    expect(barra(aba)).to_contain_text("2 passos")
    mensagens = aba.evaluate("window.__mensagens")
    assert not any("token-de-teste" in m for m in mensagens)
    # Fora do painel a ponte não existe: nada responde a quem imita o painel
    assert falar_com_extensao(aba, "ping", espera_ms=500) is None
    assert aba.evaluate("document.documentElement.dataset.dittoExtensao") is None


def test_texto_do_site_nunca_vira_html_na_barra(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/texto-perigoso")
    barra(aba).get_by_role("button", name="Capturar dado").click()
    barra(aba).get_by_text("Clique no dado").wait_for()
    aba.locator("dd").click()
    barra(aba).locator("input[type=text]").wait_for()

    expect(barra(aba)).to_contain_text("<img src=x")
    assert barra(aba).locator("img").count() == 0
    aba.wait_for_timeout(200)
    assert aba.evaluate("window.__invadido") is None
    # O formulário aberto substitui a instrução de clicar no dado
    expect(barra(aba)).not_to_contain_text("Clique no dado")


def test_painel_nao_controla_a_gravacao_alem_de_iniciar(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/relatorios")
    painel = abrir_painel(navegador_com_extensao, portal)
    for pedido in ("stop", "discard", "step", "status"):
        assert falar_com_extensao(painel, pedido, espera_ms=500) is None, pedido
    assert barra(aba).is_visible()
    assert portal.recordings == []


def test_valor_muito_curto_nao_vira_referencia_por_coincidencia(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/valor-curto")
    capturar(aba, "dd")
    aba.get_by_label("Quantidade").fill("7")
    aba.get_by_label("Quantidade").blur()
    expect(barra(aba)).to_contain_text("3 passos")

    gravacao = parar_e_pegar_gravacao(aba, portal)
    preenchimento = next(p for p in gravacao["steps"] if p["action"] == "fill")
    assert preenchimento["value"] == "7"
    assert "value_from_capture" not in preenchimento


# Sites atuais, onde quase nada é um botão ou um formulário de verdade


def _acoes(gravacao: dict[str, Any]) -> list[str]:
    return [passo["action"] for passo in gravacao["steps"]]


def test_clique_em_bloco_com_maozinha_e_gravado(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.get_by_text("Filtrar por loja").click()
    expect(barra(aba)).to_contain_text("2 passos")
    expect(barra(aba)).to_contain_text('Anotado: clique em "Filtrar por loja"')
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert gravacao["steps"][1]["target"]["css"] == "#abrir-menu"
    assert "role" not in gravacao["steps"][1]["target"]


def test_clique_em_texto_comum_nao_vira_passo(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.locator("#texto-comum").click()
    aba.wait_for_timeout(500)
    expect(barra(aba)).to_contain_text("1 passo")


def test_opcao_que_some_antes_do_clique_e_gravada(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.get_by_text("Filtrar por loja").click()
    aba.get_by_role("option", name="Loja Centro").click()
    expect(aba.locator("#escolhido")).to_have_text("Loja Centro")
    expect(barra(aba)).to_contain_text("3 passos")
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert gravacao["steps"][2]["target"]["text"] == "Loja Centro"


def test_digitacao_nao_se_perde_quando_o_campo_some(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.locator("#some").click()
    aba.keyboard.type("abc")
    expect(aba.locator("#caixa b")).to_have_text("Trocado")
    aba.get_by_text("Filtrar por loja").click()
    expect(barra(aba)).to_contain_text("3 passos")
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert _acoes(gravacao) == ["navigate", "fill", "click"]
    assert gravacao["steps"][1]["value"] == "abc"
    assert gravacao["steps"][1]["target"]["label"] == "Campo que some"


def test_campo_dentro_de_componente_isolado_e_gravado(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.get_by_label("Campo interno").click()
    aba.keyboard.type("dentro")
    aba.locator("#texto-comum").click()
    expect(barra(aba)).to_contain_text("2 passos")
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert gravacao["steps"][1]["value"] == "dentro"


def test_editor_com_varias_linhas_vira_um_passo_so(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.locator("#editor").click()
    aba.keyboard.type("primeira")
    aba.keyboard.press("Enter")
    aba.keyboard.type("segunda")
    aba.locator("#texto-comum").click()
    expect(barra(aba)).to_contain_text("2 passos")
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert gravacao["steps"][1]["action"] == "fill"
    assert gravacao["steps"][1]["value"] == "primeira\nsegunda"


def test_enter_que_envia_em_um_chat_e_gravado(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.locator("#chat").click()
    aba.keyboard.type("olá")
    aba.keyboard.press("Enter")
    expect(aba.locator("#enviado")).to_have_text("enviado")
    expect(barra(aba)).to_contain_text("3 passos")
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert _acoes(gravacao) == ["navigate", "fill", "press"]
    assert gravacao["steps"][1]["value"] == "olá"


def test_botoes_iguais_recebem_seletor_que_aponta_para_um_so(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.get_by_role("button", name="Comprar").nth(1).click()
    expect(barra(aba)).to_contain_text("2 passos")
    seletor = parar_e_pegar_gravacao(aba, portal)["steps"][1]["target"]["css"]
    pagina = navegador_com_extensao.new_page()
    pagina.goto(f"{portal.url}/site-moderno")
    assert pagina.locator(seletor).count() == 1
    assert "Produto B" in pagina.locator(seletor).evaluate("el => el.parentElement.textContent")


def test_barra_muda_de_canto_para_nao_cobrir_o_site(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/busca")
    assert barra(aba).get_attribute("data-canto") == "0"
    barra(aba).get_by_role("button", name="Mover").click()
    expect(barra(aba)).to_have_attribute("data-canto", "1")
    # Vale também para a próxima página
    aba.get_by_label("CNPJ").fill("111")
    aba.get_by_role("button", name="Consultar").click()
    aba.wait_for_url("**/consulta?cnpj=111")
    expect(barra(aba)).to_have_attribute("data-canto", "1")


def test_clique_logo_depois_de_uma_opcao_que_some_nao_apaga_a_opcao(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    aba.get_by_text("Filtrar por loja").click()
    aba.get_by_role("option", name="Loja Centro").click()
    aba.get_by_text("Aba de detalhes").click()
    expect(barra(aba)).to_contain_text("4 passos")
    gravacao = parar_e_pegar_gravacao(aba, portal)
    assert [p["target"]["text"] for p in gravacao["steps"][1:]] == [
        "Filtrar por loja",
        "Loja Centro",
        "Aba de detalhes",
    ]


def test_botoes_da_barra_nao_sao_refeitos_a_cada_passo(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    # Um botão refeito entre apertar e soltar o mouse perde o clique
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/site-moderno")
    marcar = """() => {
        const sombra = document.querySelector('ditto-gravador').shadowRoot;
        window.__botao = sombra.querySelector('[data-acao=parar]');
        return window.__botao.textContent;
    }"""
    assert aba.evaluate(marcar) == "Parar e salvar"
    aba.get_by_text("Filtrar por loja").click()
    expect(barra(aba)).to_contain_text("2 passos")
    assert aba.evaluate("window.__botao.isConnected") is True


def test_atualizar_a_barra_nao_apaga_o_nome_que_a_pessoa_esta_digitando(
    navegador_com_extensao: BrowserContext, portal: Portal
) -> None:
    aba = iniciar_gravacao(navegador_com_extensao, portal, "/consulta?cnpj=111")
    barra(aba).get_by_role("button", name="Capturar dado").click()
    barra(aba).get_by_text("Clique no dado").wait_for()
    aba.locator("dd").click()
    campo = barra(aba).locator("input[type=text]")
    campo.wait_for()
    campo.fill("Nome em digitação")
    barra(aba).get_by_role("button", name="Mover").click()
    expect(barra(aba)).to_have_attribute("data-canto", "1")
    assert campo.input_value() == "Nome em digitação"
