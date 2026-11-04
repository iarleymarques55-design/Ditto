import shutil
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import NotFoundError


def _resolve(key: str) -> Path:
    root = settings.storage_dir.resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise NotFoundError("Arquivo não encontrado.")
    return path


def path_for_write(key: str) -> Path:
    path = _resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_bytes(key: str, content: bytes) -> int:
    path = path_for_write(key)
    path.write_bytes(content)
    return len(content)


def path_for_read(key: str) -> Path:
    path = _resolve(key)
    if not path.is_file():
        raise NotFoundError("Arquivo não encontrado.")
    return path


def delete(key: str) -> None:
    _resolve(key).unlink(missing_ok=True)


def delete_tree(prefix: str) -> None:
    path = _resolve(prefix)
    # Um prefixo vazio apontaria para a raiz, com os arquivos de todo mundo
    if path == settings.storage_dir.resolve():
        raise ValueError("O prefixo não pode ser a raiz do armazenamento.")
    shutil.rmtree(path, ignore_errors=True)
