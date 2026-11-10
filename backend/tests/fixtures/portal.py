"""Portal falso que muda de layout. Serve para testar o motor em um navegador de verdade."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

_BASE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Portal</title></head><body>{body}</body></html>"""

_FORM = """
<h1>Relatórios</h1>
<label for="loja">Loja</label>
<select id="loja" name="loja">
  <option value="">Escolha</option>
  <option>Loja 01 - Shopping Norte</option>
  <option>Loja 02 - Aldeota</option>
  <option>Loja 03 - Messejana</option>
</select>
<label for="mes">Mês</label>
<input id="mes" name="mes" type="text" placeholder="mm/aaaa">
"""

_EXPORT_LAYOUTS = {
    # O layout em que a tarefa foi gravada
    "original": """
      <div id="acoes">
        <button id="imprimir">Imprimir</button>
        <a id="exportar" role="button" href="/baixar.pdf">Exportar PDF</a>
        <button>Excel</button>
      </div>""",
    # Só o texto mudou: a camada 2 resolve
    "renomeado": """
      <div id="acoes">
        <button id="imprimir">Imprimir</button>
        <a id="baixar" role="button" href="/baixar.pdf">Exportar em PDF</a>
        <button>Excel</button>
      </div>""",
    # O botão foi para dentro de um menu: só a IA acha
    "menu": """
      <div id="acoes">
        <button id="menu" onclick="document.getElementById('itens').style.display='block'">Ações</button>
        <div id="itens" style="display:none">
          <button>Imprimir</button>
          <a role="menuitem" href="/baixar.pdf">Baixar como PDF</a>
          <button onclick="document.body.dataset.apagou='sim'">Apagar relatório</button>
        </div>
      </div>""",
    # Duas opções quase iguais: é dúvida, então vai para a pessoa
    "ambiguo": """
      <div id="acoes">
        <button>Imprimir</button>
        <a role="button" href="/baixar.pdf">Exportar PDF A</a>
        <a role="button" href="/baixar.pdf">Exportar PDF B</a>
      </div>""",
    # O CSS gravado agora aponta para outro botão
    "trocado": """
      <div id="acoes">
        <button id="imprimir">Exportar Excel</button>
        <a id="exportar" role="button" href="/nada">Falar com o suporte</a>
        <button>Sair</button>
      </div>""",
    "captcha": """
      <div class="g-recaptcha" style="width:300px;height:80px">Não sou um robô</div>
      <div id="acoes"><button>Imprimir</button></div>""",
    "vazio": """<p>Página em manutenção.</p>""",
}

_LOGIN = """
<form action="/entrou" method="get" autocomplete="off">
  <label for="usuario">Usuário</label>
  <input id="usuario" name="usuario" type="text">
  <label for="senha">Senha</label>
  <input id="senha" name="senha" type="password">
  <button id="entrar" type="submit">Entrar</button>
</form>
"""

_DECLARATION = """
<h1>Declaração</h1>
<button id="enviar" onclick="document.getElementById('protocolo').style.display='block'; window.enviados = (window.enviados || 0) + 1; fetch('/registrar-envio')">Enviar declaração</button>
<p id="protocolo" style="display:none">Protocolo gerado</p>
"""


_BUSCA = """
<label for="cnpj">CNPJ</label>
<input id="cnpj" name="cnpj" type="text">
<button id="consultar" onclick="location.href='/consulta?cnpj=' + document.getElementById('cnpj').value">Consultar</button>
"""

_BUSCA_COM_FORMULARIO = """
<form action="/consulta">
  <label for="cnpj">CNPJ</label>
  <input id="cnpj" name="cnpj" type="text">
  <button>Consultar</button>
</form>
"""

# Como sites atuais são feitos: botões que são blocos comuns, menus que agem antes do clique,
# campos que somem, editores de texto e componentes isolados
_SITE_MODERNO = """
<div id="abrir-menu" style="cursor:pointer" onclick="document.getElementById('menu').hidden=false"><span>Filtrar por loja</span></div>
<div id="menu" hidden><div role="option" onmousedown="document.getElementById('escolhido').textContent=this.textContent;this.parentElement.remove()">Loja Centro</div></div>
<p id="escolhido"></p>
<p id="texto-comum">Texto sem ação nenhuma</p>
<div id="aba" class="fechada" style="cursor:pointer" onclick="this.className='aberta'">Aba de detalhes</div>
<div id="caixa"><input id="some" aria-label="Campo que some" oninput="if(this.value.length>=3){document.getElementById('caixa').innerHTML='<b>Trocado</b>'}"></div>
<div id="hospedeiro"></div>
<script>document.getElementById('hospedeiro').attachShadow({mode:'open'}).innerHTML='<input aria-label="Campo interno">'</script>
<div id="editor" contenteditable="true" role="textbox" aria-label="Anotações" style="min-height:40px;border:1px solid #999"></div>
<textarea id="chat" aria-label="Mensagem" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();this.value='';document.getElementById('enviado').textContent='enviado'}"></textarea>
<p id="enviado"></p>
<ul id="produtos"><li>Produto A <button>Comprar</button></li><li>Produto B <button>Comprar</button></li></ul>
<input id="sugere" aria-label="Busca com sugestões" oninput="if(!document.getElementById('lista')){const d=document.createElement('div');d.id='lista';d.setAttribute('role','listbox');d.setAttribute('aria-label','Busca com sugestões');d.textContent='Opção';document.body.append(d)}">
<input id="mascara" aria-label="CNPJ com máscara" oninput="this.value=this.value.replace(/\\D/g,'').replace(/^(\\d{2})(\\d)/,'$1.$2')">
"""

# O número antigo fica na tela até o site responder: quem lê cedo demais leva o valor errado
_RESULTADO_DEMORA = """
<button id="filtrar" onclick="this.textContent='Filtrando';fetch('/api/total-filtrado').then(()=>{document.getElementById('total').textContent='2'})">Filtrar</button>
<dl><dt>Total</dt><dd id="total">12</dd></dl>
"""

# O site mostra um texto que, se fosse tratado como HTML, rodaria um script
_TEXTO_PERIGOSO = """
<dl><dt>Situação</dt><dd>&lt;img src=x onerror="window.__invadido=1"&gt;</dd></dl>
"""

_VALOR_CURTO = """
<dl><dt>Código</dt><dd>7</dd></dl>
<label for="quantidade">Quantidade</label><input id="quantidade" name="quantidade" type="text">
"""

_RESPOSTAS = {
    "111": "ATIVA",
    "222": "BAIXADA",
    "formula": '=HYPERLINK("http://golpe.exemplo","ATIVA")',
}


def _consulta(cnpj: str, layout: str) -> str:
    situacao = _RESPOSTAS.get(cnpj, "INAPTA")
    if layout == "sem_rotulo":
        return f"<dl><dt>Capital</dt><dd>R$ 1,00</dd><dt>Status</dt><dd>{situacao}</dd></dl>"
    return f"""
<dl><dt>Situação</dt><dd>{situacao}</dd></dl>
<p><span>Razão social: Empresa {cnpj} Ltda</span></p>
<p><span>Acesso: senha-do-portal-111</span></p>
<div><span>Vencimento</span><span>10/12/2026</span></div>
<p data-testid="protocolo">PROT-{cnpj}</p>
<table id="notas"><thead><tr><th>Número</th><th>Valor</th></tr></thead>
<tbody><tr><td>NF-1</td><td>R$ 10,00</td></tr><tr><td>NF-2</td><td>R$ 20,00</td></tr></tbody></table>
"""


_ERP = """
<form action="/erp-salvo" method="get">
<label for="situacao">Situação no ERP</label>
<input id="situacao" name="situacao" type="text">
<button id="salvar" type="submit">Salvar</button>
</form>
"""

_SIGILOSOS = """
<label for="senha">Senha</label><input id="senha" type="password" value="nao-pode-ler">
<label for="cartao">Cartão</label><input id="cartao" autocomplete="cc-number" value="4111">
<label for="protocolo">Protocolo</label><input id="protocolo" readonly value="ABC-1">
"""

_LENTA = """
<div id="area"></div>
<script>
setTimeout(() => {
  document.getElementById('area').innerHTML = '<button id="carregou" onclick="document.body.dataset.ok=1;this.textContent=&quot;Feito&quot;">Carregou</button>';
}, 150);
</script>
"""

_ABRE_JANELA = """
<a id="abrir" href="/consulta?cnpj=111" target="_blank">Abrir</a>
<a id="baixar" href="/baixar.pdf" target="_blank">Baixar</a>
"""

_COM_IFRAME = """
<h1>Página de fora</h1>
<iframe src="/dentro-do-iframe" width="400" height="200"></iframe>
"""

_DENTRO_DO_IFRAME = """
<dl><dt>Situação</dt><dd>ATIVA</dd></dl>
<button id="no-iframe" onclick="fetch('/clicou-no-iframe');this.textContent='Clicado'">Botão no iframe</button>
"""


def _dialogo(mensagem: str) -> str:
    return f"""
<button id="acao" onclick="if (confirm('{mensagem}')) {{ fetch('/dialogo-aceito'); }} this.textContent='Respondido'">Continuar</button>
"""


class Portal:
    def __init__(self) -> None:
        self.layout = "original"
        self.consulta_layout = "normal"
        self.recordings: list[dict] = []
        self.recording_auth: list[str] = []
        self.flows_status = 201
        self.saved_values: list[str] = []
        self.submissions = 0
        self.requests: list[str] = []
        self.passwords_seen: list[str] = []
        self.login_ok = True
        portal = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def _html(self, body: str, status: int = 200) -> None:
                content = _BASE.format(body=body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def do_POST(self) -> None:
                tamanho = int(self.headers.get("Content-Length", 0))
                corpo = self.rfile.read(tamanho)
                resposta = b'{"id": "tarefa-gravada"}'
                if urlsplit(self.path).path == "/api/flows" and portal.flows_status == 201:
                    portal.recordings.append(json.loads(corpo))
                    portal.recording_auth.append(self.headers.get("Authorization", ""))
                elif portal.flows_status != 201:
                    resposta = b'{"detail": "Erro de teste."}'
                self.send_response(portal.flows_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resposta)))
                self.end_headers()
                self.wfile.write(resposta)

            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                portal.requests.append(parts.path)

                query = parse_qs(parts.query)
                paginas = {
                    "/busca": lambda: _BUSCA,
                    "/painel-falso": lambda: "<h1>Painel</h1>",
                    "/com-arquivo": lambda: '<input type="file">',
                    "/site-moderno": lambda: _SITE_MODERNO,
                    "/resultado-demora": lambda: _RESULTADO_DEMORA,
                    "/texto-perigoso": lambda: _TEXTO_PERIGOSO,
                    "/valor-curto": lambda: _VALOR_CURTO,
                    "/busca-com-formulario": lambda: _BUSCA_COM_FORMULARIO,
                    "/painel/tarefas/tarefa-gravada": lambda: "<h1>Tarefa no painel</h1>",
                    "/consulta": lambda: _consulta(
                        query.get("cnpj", [""])[0], portal.consulta_layout
                    ),
                    "/erp": lambda: _ERP,
                    "/campos-sigilosos": lambda: _SIGILOSOS,
                    "/lenta": lambda: _LENTA,
                    "/abre-janela": lambda: _ABRE_JANELA,
                    "/com-iframe": lambda: _COM_IFRAME,
                    "/dentro-do-iframe": lambda: _DENTRO_DO_IFRAME,
                    "/dialogo-comum": lambda: _dialogo("Deseja continuar?"),
                    "/dialogo-perigoso": lambda: _dialogo("Confirmar pagamento de R$ 500,00?"),
                    "/clicou-no-iframe": lambda: "ok",
                    "/dialogo-aceito": lambda: "ok",
                }
                if parts.path == "/api/total-filtrado":
                    time.sleep(0.8)
                    self._html("2")
                elif parts.path == "/erp-salvo":
                    portal.saved_values.extend(query.get("situacao", []))
                    self._html("<h1>Salvo</h1>")
                elif parts.path in paginas:
                    self._html(paginas[parts.path]())
                elif parts.path == "/relatorios":
                    self._html(_FORM + _EXPORT_LAYOUTS[portal.layout])
                elif parts.path == "/baixar.pdf":
                    content = b"%PDF-1.4 relatorio de teste"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", 'attachment; filename="relatorio.pdf"')
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                elif parts.path == "/login":
                    self._html(_LOGIN)
                elif parts.path == "/entrou":
                    query = parse_qs(parts.query)
                    portal.passwords_seen.extend(query.get("senha", []))
                    self._html(
                        "<h1>Bem-vinda</h1>" if portal.login_ok else "<h1>Senha incorreta</h1>"
                    )
                elif parts.path == "/declaracao":
                    self._html(_DECLARATION)
                elif parts.path == "/registrar-envio":
                    portal.submissions += 1
                    self._html("ok")
                elif parts.path == "/redireciona-interno":
                    # Simula um portal malicioso mandando o navegador para a rede interna
                    self.send_response(302)
                    self.send_header(
                        "Location", f"http://127.0.0.1:{portal.port}/metadados-da-nuvem"
                    )
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif parts.path == "/subrecurso-interno":
                    imagem = f'<img src="http://127.0.0.1:{portal.port}/imagem-interna">'
                    self._html(imagem + "<h1>Página</h1>")
                elif parts.path == "/redireciona":
                    self.send_response(302)
                    self.send_header("Location", "http://outro-dominio.invalid/")
                    self.end_headers()
                else:
                    self._html("<h1>Não encontrado</h1>", 404)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self.url = f"http://localhost:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def reset(self) -> None:
        self.layout = "original"
        self.consulta_layout = "normal"
        self.recordings.clear()
        self.recording_auth.clear()
        self.flows_status = 201
        self.saved_values.clear()
        self.submissions = 0
        self.requests.clear()
        self.passwords_seen.clear()
        self.login_ok = True
