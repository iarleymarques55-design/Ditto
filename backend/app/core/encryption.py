import json

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import settings


def _cipher() -> MultiFernet:
    keys = [
        key.strip() for key in settings.fernet_keys.get_secret_value().split(",") if key.strip()
    ]
    return MultiFernet([Fernet(key) for key in keys])


def encrypt_json(data: dict[str, str]) -> str:
    return _cipher().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict[str, str]:
    return json.loads(_cipher().decrypt(token.encode()))
