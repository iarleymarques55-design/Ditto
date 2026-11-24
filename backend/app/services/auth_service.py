import logging
import threading
import time
from datetime import UTC, datetime

from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    InvalidCredentialsError,
    ServiceNotConfiguredError,
    UnauthorizedError,
)
from app.core.rate_limit import rate_limiter
from app.core.security import (
    RUNNER_SCOPE,
    create_access_token,
    decode_access_token,
    hash_password,
    issued_before,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

# Por e-mail e IP: quem erra a própria senha é travado sem travar a dona da conta em outro lugar
_LOGIN_ATTEMPTS_PER_EMAIL_AND_IP = 10
# Por e-mail, de qualquer lugar: freia ataque distribuído. Alto o bastante para que travar a
# conta de outra pessoa custe muitas tentativas de muitos IPs
_LOGIN_ATTEMPTS_PER_EMAIL = 50
_LOGIN_WINDOW_SECONDS = 15 * 60
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


# Os certificados do Google mudam poucas vezes por dia: buscar a cada login deixava cada
# entrada mais lenta e, com o Google fora do ar, presa por até 2 minutos
_GOOGLE_TIMEOUT_SECONDS = 10
_GOOGLE_CERTS_CACHE_SECONDS = 60 * 60


class _CachedGoogleRequest(google_requests.Request):
    """Transporte do google-auth com tempo limite curto e cache das respostas GET."""

    def __init__(self) -> None:
        super().__init__()
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: object,
    ) -> object:
        timeout = min(timeout or _GOOGLE_TIMEOUT_SECONDS, _GOOGLE_TIMEOUT_SECONDS)
        if method != "GET" or body is not None:
            return super().__call__(url, method, body, headers, timeout, **kwargs)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(url)
            if cached and now - cached[0] < _GOOGLE_CERTS_CACHE_SECONDS:
                return cached[1]
        response = super().__call__(url, method, body, headers, timeout, **kwargs)
        if response.status == 200:
            with self._lock:
                self._cache[url] = (now, response)
        return response


_google_request = _CachedGoogleRequest()


def _verify_google_token(credential: str) -> dict:
    return id_token.verify_oauth2_token(credential, _google_request, settings.google_client_id)


def token_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserResponse.model_validate(user)
    )


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register(self, payload: RegisterRequest) -> TokenResponse:
        email = payload.email.lower()
        if self.users.get_by_email(email):
            raise ConflictError("Já existe uma conta com este e-mail.")

        user = self.users.add(
            User(
                email=email,
                name=payload.name.strip(),
                password_hash=hash_password(payload.password),
            )
        )
        try:
            self.session.commit()
        except IntegrityError as error:
            # Dois cadastros simultâneos com o mesmo e-mail: o banco decide
            self.session.rollback()
            raise ConflictError("Já existe uma conta com este e-mail.") from error
        return token_for(user)

    def login(self, payload: LoginRequest, client: str = "desconhecido") -> TokenResponse:
        email = payload.email.lower()
        # Além do limite por IP da rota
        rate_limiter.check(
            f"login:{email}:{client}", _LOGIN_ATTEMPTS_PER_EMAIL_AND_IP, _LOGIN_WINDOW_SECONDS
        )
        rate_limiter.check(f"login:{email}", _LOGIN_ATTEMPTS_PER_EMAIL, _LOGIN_WINDOW_SECONDS)

        user = self.users.get_by_email(email)
        if not verify_password(payload.password, user.password_hash if user else None):
            raise InvalidCredentialsError
        return token_for(user)

    def login_with_google(self, payload: GoogleLoginRequest) -> TokenResponse:
        if not settings.google_client_id:
            raise ServiceNotConfiguredError("O login com Google não está configurado.")

        try:
            claims = _verify_google_token(payload.credential)
        except (ValueError, GoogleAuthError) as error:
            logger.info("Token do Google recusado: %s", type(error).__name__)
            raise UnauthorizedError("Não foi possível confirmar sua conta Google.") from error

        if claims.get("iss") not in _GOOGLE_ISSUERS or not claims.get("email_verified"):
            raise UnauthorizedError("Não foi possível confirmar sua conta Google.")

        user = self._find_or_create_google_user(claims)
        self.session.commit()
        return token_for(user)

    def _find_or_create_google_user(self, claims: dict) -> User:
        user = self.users.get_by_google_sub(claims["sub"])
        if user:
            return user

        email = claims["email"].lower()
        user = self.users.get_by_email(email)
        if user:
            # O cadastro por senha não confirma o e-mail. Sem apagar a senha, quem criou a conta
            # antes com o e-mail de outra pessoa continuaria entrando depois que ela usasse o Google.
            user.password_hash = None
            user.google_sub = claims["sub"]
            # E os tokens que essa pessoa já tinha tirado (o de acesso e o do executor, que dura
            # 30 dias) também deixam de valer: sem isto ela continuaria ligada à conta
            user.tokens_valid_after = datetime.now(UTC)
            return user

        return self.users.add(
            User(email=email, name=claims.get("name") or email, google_sub=claims["sub"])
        )

    def get_runner_user(self, token: str) -> User:
        """Só o token do executor liga a extensão ao worker, nem o token de acesso comum."""
        _, issued_at, scope = decode_access_token(token)
        if scope != RUNNER_SCOPE:
            raise UnauthorizedError
        user = self.get_user_from_token(token, allowed_scope=RUNNER_SCOPE)
        # "Desligar este Chrome" no painel ou na extensão
        if issued_before(issued_at, user.runner_tokens_valid_after):
            raise UnauthorizedError
        return user

    def revoke_runner_tokens(self, user: User) -> None:
        """Encerra todos os Chromes ligados a esta conta. O relé derruba a conexão em até 1 min."""
        user.runner_tokens_valid_after = datetime.now(UTC)
        self.session.commit()

    def get_user_from_token(self, token: str, *, allowed_scope: str | None = None) -> User:
        user_id, issued_at, scope = decode_access_token(token)
        # Um token com escopo (os da extensão) só vale onde aquele escopo é aceito
        if scope is not None and scope != allowed_scope:
            raise UnauthorizedError
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UnauthorizedError
        # A senha foi trocada depois que este token saiu: a sessão antiga acabou
        if issued_before(issued_at, user.tokens_valid_after):
            raise UnauthorizedError
        return user
