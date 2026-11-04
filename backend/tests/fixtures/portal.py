"""Portal falso que muda de layout. Serve para testar o motor em um navegador de verdade."""

import threading
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


class Portal:
    def __init__(self) -> None:
        self.layout = "original"
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

            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                portal.requests.append(parts.path)

                if parts.path == "/relatorios":
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
        self.submissions = 0
        self.requests.clear()
        self.passwords_seen.clear()
        self.login_ok = True
