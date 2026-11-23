"""Onde ficam os arquivos gerados: downloads das tarefas, telas das falhas e fotos de perfil.

O destino é escolhido pela configuração, sem mudar o código de quem chama:
- sem S3_BUCKET, na pasta STORAGE_DIR do disco. Serve quando a API e o worker dividem a pasta
  (no seu computador ou no Docker);
- com S3_BUCKET, num bucket compatível com S3 (Railway, AWS, Cloudflare R2). Serve quando a API e
  o worker rodam em máquinas separadas, como no Railway, e precisam ver os mesmos arquivos.

As chaves são sempre montadas pelo Ditto, no formato "<conta>/<execução>/<arquivo>".
"""

import shutil
from collections.abc import Iterator
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.config import settings
from app.core.exceptions import NotFoundError

_CHUNK_BYTES = 64 * 1024
# delete_objects aceita até mil chaves por chamada
_DELETE_BATCH = 1000


def _uses_bucket() -> bool:
    return bool(settings.s3_bucket)


def _check_key(key: str) -> str:
    """Nenhuma chave sai da pasta da conta: nada de "..", caminho absoluto ou barra invertida."""
    parts = PurePosixPath(key).parts
    if not key or "\\" in key or key.startswith("/") or ".." in parts or "" in key.split("/"):
        raise NotFoundError("Arquivo não encontrado.")
    return key


# ─── Disco ──────────────────────────────────────────────────────────────


def _resolve(key: str) -> Path:
    root = settings.storage_dir.resolve()
    path = (root / _check_key(key)).resolve()
    if not path.is_relative_to(root):
        raise NotFoundError("Arquivo não encontrado.")
    return path


def _file_chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as file:
        while chunk := file.read(_CHUNK_BYTES):
            yield chunk


# ─── Bucket ─────────────────────────────────────────────────────────────


@cache
def _bucket_client() -> Any:
    # O boto3 só é carregado quando há bucket: no computador ele nem precisa estar em uso
    import boto3

    # Sessão própria: a sessão padrão do boto3 não é segura entre as linhas de trabalho do worker.
    # Se duas threads criarem o cliente ao mesmo tempo, cada uma fica com o seu, sem problema
    return boto3.session.Session().client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
    )


def _object_chunks(body: Any) -> Iterator[bytes]:
    try:
        yield from body.iter_chunks(_CHUNK_BYTES)
    finally:
        body.close()


def _is_missing(error: Exception) -> bool:
    code = getattr(error, "response", {}).get("Error", {}).get("Code", "")
    return code in {"NoSuchKey", "404", "NotFound"}


# ─── Usado pelo resto do Ditto ──────────────────────────────────────────


def save_bytes(key: str, content: bytes) -> int:
    if _uses_bucket():
        _bucket_client().put_object(Bucket=settings.s3_bucket, Key=_check_key(key), Body=content)
    else:
        path = _resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return len(content)


def save_file(key: str, source: Path) -> int:
    """Guarda um arquivo que já está no disco, como o que o navegador acabou de baixar."""
    if _uses_bucket():
        _bucket_client().upload_file(str(source), settings.s3_bucket, _check_key(key))
    else:
        path = _resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
    return source.stat().st_size


def open_for_read(key: str) -> Iterator[bytes]:
    """O conteúdo em pedaços. Arquivo que não existe dá NotFoundError aqui, antes de a resposta
    começar a ser enviada."""
    if not _uses_bucket():
        path = _resolve(key)
        if not path.is_file():
            raise NotFoundError("Arquivo não encontrado.")
        return _file_chunks(path)

    from botocore.exceptions import ClientError

    try:
        found = _bucket_client().get_object(Bucket=settings.s3_bucket, Key=_check_key(key))
    except ClientError as error:
        if _is_missing(error):
            raise NotFoundError("Arquivo não encontrado.") from error
        raise
    return _object_chunks(found["Body"])


def delete(key: str) -> None:
    if _uses_bucket():
        # Apagar o que não existe não é erro no S3
        _bucket_client().delete_object(Bucket=settings.s3_bucket, Key=_check_key(key))
    else:
        _resolve(key).unlink(missing_ok=True)


def delete_tree(prefix: str) -> None:
    """Apaga tudo de uma conta ou de uma execução."""
    # Um prefixo vazio apontaria para a raiz, com os arquivos de todo mundo
    if not prefix.strip("/"):
        raise ValueError("O prefixo não pode ser a raiz do armazenamento.")
    if not _uses_bucket():
        shutil.rmtree(_resolve(prefix), ignore_errors=True)
        return

    client = _bucket_client()
    pages = client.get_paginator("list_objects_v2").paginate(
        Bucket=settings.s3_bucket, Prefix=f"{_check_key(prefix.rstrip('/'))}/"
    )
    keys = [item["Key"] for page in pages for item in page.get("Contents", [])]
    for start in range(0, len(keys), _DELETE_BATCH):
        batch = [{"Key": key} for key in keys[start : start + _DELETE_BATCH]]
        client.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": batch, "Quiet": True})
