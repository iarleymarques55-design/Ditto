import logging

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
    create_access_token,
    decode_access_token,
    hash_password,
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

_LOGIN_ATTEMPTS_PER_EMAIL = 10
_LOGIN_WINDOW_SECONDS = 15 * 60
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def _verify_google_token(credential: str) -> dict:
    return id_token.verify_oauth2_token(
        credential, google_requests.Request(), settings.google_client_id
    )


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

    def login(self, payload: LoginRequest) -> TokenResponse:
        email = payload.email.lower()
        # Conta por e-mail, além do limite por IP da rota: protege a conta de ataques distribuídos
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
            return user

        return self.users.add(
            User(email=email, name=claims.get("name") or email, google_sub=claims["sub"])
        )

    def get_user_from_token(self, token: str) -> User:
        user_id, issued_at = decode_access_token(token)
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UnauthorizedError
        # A senha foi trocada depois que este token saiu: a sessão antiga acabou
        if user.tokens_valid_after and issued_at < int(user.tokens_valid_after.timestamp()):
            raise UnauthorizedError
        return user
