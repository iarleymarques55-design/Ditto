import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitedError


class RateLimiter:
    """Janela deslizante em memória. Cada processo da API conta as próprias tentativas."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                raise RateLimitedError
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """O IP de quem fez o pedido.

    Atrás de um proxy (o do Railway, por exemplo), a conexão chega sempre do proxy: sem isto,
    todo mundo dividiria o mesmo limite. Cada proxy confiável acrescenta, no fim do
    X-Forwarded-For, o IP de quem falou com ele. O começo da lista quem escreve é o cliente,
    então vale a posição contada de trás para a frente, nunca o primeiro item.
    """
    peer = request.client.host if request.client else "desconhecido"
    hops = settings.trusted_proxy_hops
    if hops == 0:
        return peer
    forwarded = [
        part.strip()
        for part in request.headers.get("x-forwarded-for", "").split(",")
        if part.strip()
    ]
    # Pedido que não passou por todos os proxies esperados: fica o IP da conexão
    return forwarded[-hops] if len(forwarded) >= hops else peer


def limit_requests(limit: int, window_seconds: int = 60):
    """Dependência do FastAPI que limita as chamadas de um IP a uma rota."""

    def dependency(request: Request) -> None:
        rate_limiter.check(f"{request.url.path}:{client_ip(request)}", limit, window_seconds)

    return dependency
