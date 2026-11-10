import threading
import time
from collections import defaultdict, deque

from fastapi import Request

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


def limit_requests(limit: int, window_seconds: int = 60):
    """Dependência do FastAPI que limita as chamadas de um IP a uma rota."""

    def dependency(request: Request) -> None:
        client = request.client.host if request.client else "desconhecido"
        rate_limiter.check(f"{request.url.path}:{client}", limit, window_seconds)

    return dependency
