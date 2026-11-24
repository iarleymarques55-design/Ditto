import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitedError

# De quantas em quantas chamadas as chaves sem tentativas recentes saem da memória
_SWEEP_EVERY = 1000


class RateLimiter:
    """Janela deslizante em memória. Cada processo da API conta as próprias tentativas.

    O Ditto roda uma réplica da API (docker-compose e Railway). Com várias réplicas, cada uma
    contaria à parte e o limite real seria multiplicado: aí o contador precisa ir para o banco
    ou para um Redis.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._windows: dict[str, int] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._calls += 1
            if self._calls % _SWEEP_EVERY == 0:
                self._sweep(now)
            hits = self._hits[key]
            self._windows[key] = window_seconds
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                raise RateLimitedError
            hits.append(now)

    def _sweep(self, now: float) -> None:
        """Sem isto, cada e-mail ou IP diferente ficaria na memória para sempre."""
        stale = [
            key
            for key, hits in self._hits.items()
            if not hits or now - hits[-1] > self._windows.get(key, 0)
        ]
        for key in stale:
            del self._hits[key]
            self._windows.pop(key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._windows.clear()
            self._calls = 0


rate_limiter = RateLimiter()


def ip_behind_proxies(peer: str, forwarded_for: str) -> str:
    """O IP do cliente a partir do IP da conexão e do X-Forwarded-For (veja client_ip)."""
    hops = settings.trusted_proxy_hops
    if hops == 0:
        return peer
    forwarded = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    # Pedido que não passou por todos os proxies esperados: fica o IP da conexão
    return forwarded[-hops] if len(forwarded) >= hops else peer


def client_ip(request: Request) -> str:
    """O IP de quem fez o pedido.

    Atrás de um proxy (o do Railway, por exemplo), a conexão chega sempre do proxy: sem isto,
    todo mundo dividiria o mesmo limite. Cada proxy confiável acrescenta, no fim do
    X-Forwarded-For, o IP de quem falou com ele. O começo da lista quem escreve é o cliente,
    então vale a posição contada de trás para a frente, nunca o primeiro item.
    """
    peer = request.client.host if request.client else "desconhecido"
    return ip_behind_proxies(peer, request.headers.get("x-forwarded-for", ""))


def limit_requests(limit: int, window_seconds: int = 60):
    """Dependência do FastAPI que limita as chamadas de um IP a uma rota."""

    def dependency(request: Request) -> None:
        rate_limiter.check(f"{request.url.path}:{client_ip(request)}", limit, window_seconds)

    return dependency
