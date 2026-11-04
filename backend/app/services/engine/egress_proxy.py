"""Toda conexão do navegador passa por aqui, e o destino é conferido na hora de conectar.

O filtro de requisições do Playwright não vê redirecionamentos: um portal malicioso poderia
responder 302 para a rede interna, e o navegador iria até lá. Conferir aqui cobre esse caso,
além de WebSocket e de DNS rebinding, porque a conexão é feita no mesmo IP que foi conferido.
"""

import ipaddress
import logging
import select
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from app.core.config import settings

logger = logging.getLogger(__name__)

_IDLE_TIMEOUT_SECONDS = 60
_CONNECT_TIMEOUT_SECONDS = 10
_BUFFER_BYTES = 64 * 1024
_HOP_BY_HOP = {"proxy-connection", "proxy-authorization", "connection", "keep-alive"}

Policy = Callable[[str, str], bool]


def is_public_address(address: str) -> bool:
    # Só endereços realmente públicos: nada de loopback, rede privada, link-local ou metadados da nuvem
    ip = ipaddress.ip_address(address.split("%")[0])
    return ip.is_global and not ip.is_multicast


def default_policy(_host: str, address: str) -> bool:
    return settings.allow_private_networks or is_public_address(address)


def resolve_allowed(host: str, port: int, policy: Policy) -> list[str]:
    """Devolve os IPs para conectar. Se qualquer endereço do nome for proibido, recusa o nome inteiro."""
    try:
        addresses = [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    except OSError:
        return []
    return addresses if all(policy(host, address) for address in addresses) else []


def _relay(first: socket.socket, second: socket.socket) -> None:
    sockets = [first, second]
    while True:
        readable, _, failed = select.select(sockets, [], sockets, _IDLE_TIMEOUT_SECONDS)
        if failed or not readable:
            return
        for source in readable:
            data = source.recv(_BUFFER_BYTES)
            if not data:
                return
            (second if source is first else first).sendall(data)


class _Handler(BaseHTTPRequestHandler):
    policy: Policy = default_policy
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        pass  # endereços acessados podem conter dados da planilha: não vão para o log

    def _refuse_tunnel(self) -> None:
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _refuse_http(self) -> None:
        # Em HTTP simples o navegador trataria um 403 como resposta do próprio site, e o bloqueio
        # pareceria sucesso. Fechar sem responder vira erro de rede, que é o que aconteceu.
        self.close_connection = True

    def _connect_upstream(self, host: str, port: int) -> socket.socket | None:
        addresses = resolve_allowed(host, port, type(self).policy)
        if not addresses:
            logger.warning("Conexão bloqueada pelo filtro de saída.")
            return None
        # Um site pode ter IPv4 e IPv6: vale o primeiro que atender, sempre entre os já conferidos.
        # IPv4 antes: uma recusa em IPv6 pode levar segundos, e cada recurso da página pagaria isso.
        for address in sorted(addresses, key=lambda item: ":" in item):
            try:
                upstream = socket.create_connection(
                    (address, port), timeout=_CONNECT_TIMEOUT_SECONDS
                )
            except OSError:
                continue
            upstream.settimeout(_IDLE_TIMEOUT_SECONDS)
            return upstream
        return None

    def do_CONNECT(self) -> None:
        host, _, port_text = self.path.rpartition(":")
        upstream = self._connect_upstream(host.strip("[]"), int(port_text or 443))
        if upstream is None:
            self._refuse_tunnel()
            return

        self.send_response(200, "Connection Established")
        self.end_headers()
        self.close_connection = True
        with upstream:
            _relay(self.connection, upstream)

    def _forward_http(self) -> None:
        parts = urlsplit(self.path)
        if parts.scheme != "http" or not parts.hostname:
            self._refuse_http()
            return

        upstream = self._connect_upstream(parts.hostname, parts.port or 80)
        if upstream is None:
            self._refuse_http()
            return

        self.close_connection = True
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        headers = [
            f"{name}: {value}"
            for name, value in self.headers.items()
            if name.lower() not in _HOP_BY_HOP
        ]
        request = "\r\n".join(
            [f"{self.command} {path} HTTP/1.1", *headers, "Connection: close", "", ""]
        )
        with upstream:
            upstream.sendall(request.encode("latin-1", errors="replace"))
            _relay(self.connection, upstream)

    do_GET = _forward_http
    do_POST = _forward_http
    do_PUT = _forward_http
    do_PATCH = _forward_http
    do_DELETE = _forward_http
    do_HEAD = _forward_http
    do_OPTIONS = _forward_http


class EgressProxy:
    def __init__(self, policy: Policy = default_policy) -> None:
        handler = type("EgressHandler", (_Handler,), {"policy": staticmethod(policy)})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
