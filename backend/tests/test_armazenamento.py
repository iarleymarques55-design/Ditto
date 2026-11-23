"""Armazenamento dos arquivos: o mesmo comportamento no disco e num bucket compatível com S3.

O bucket é simulado pelo moto, sem rede nem conta na nuvem.
"""

from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.core.exceptions import NotFoundError
from app.services import storage
from tests.test_conta import enviar_foto, imagem

Cabecalho = dict[str, str]
BUCKET = "ditto-teste"


@pytest.fixture
def no_bucket(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with mock_aws():
        monkeypatch.setattr(settings, "s3_bucket", BUCKET)
        monkeypatch.setattr(settings, "s3_endpoint_url", None)
        monkeypatch.setattr(settings, "s3_region", "us-east-1")
        monkeypatch.setattr(settings, "s3_access_key_id", SecretStr("chave-de-teste"))
        monkeypatch.setattr(settings, "s3_secret_access_key", SecretStr("segredo-de-teste"))
        storage._bucket_client.cache_clear()
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield
        storage._bucket_client.cache_clear()


@pytest.fixture(params=["disco", "bucket"])
def destino(request: pytest.FixtureRequest) -> str:
    if request.param == "bucket":
        request.getfixturevalue("no_bucket")
    return request.param


def ler(chave: str) -> bytes:
    return b"".join(storage.open_for_read(chave))


def chaves_no_bucket() -> list[str]:
    resposta = boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket=BUCKET)
    return sorted(item["Key"] for item in resposta.get("Contents", []))


def test_guarda_le_e_apaga(destino: str) -> None:
    assert storage.save_bytes("conta-a/exec-1/relatorio.pdf", b"%PDF conteudo") == 13
    assert ler("conta-a/exec-1/relatorio.pdf") == b"%PDF conteudo"

    storage.delete("conta-a/exec-1/relatorio.pdf")
    with pytest.raises(NotFoundError):
        storage.open_for_read("conta-a/exec-1/relatorio.pdf")


def test_guarda_arquivo_baixado_pelo_navegador(destino: str, tmp_path: Path) -> None:
    baixado = tmp_path / "baixado.xml"
    baixado.write_bytes(b"<nota>1</nota>")

    assert storage.save_file("conta-a/exec-1/nota.xml", baixado) == 14
    assert ler("conta-a/exec-1/nota.xml") == b"<nota>1</nota>"


def test_apagar_uma_execucao_nao_toca_nas_outras(destino: str) -> None:
    storage.save_bytes("conta-a/exec-1/a.pdf", b"1")
    storage.save_bytes("conta-a/exec-1/.telas/linha-1.png", b"2")
    storage.save_bytes("conta-a/exec-10/b.pdf", b"3")
    storage.save_bytes("conta-b/exec-1/c.pdf", b"4")

    storage.delete_tree("conta-a/exec-1")

    for apagada in ("conta-a/exec-1/a.pdf", "conta-a/exec-1/.telas/linha-1.png"):
        with pytest.raises(NotFoundError):
            storage.open_for_read(apagada)
    # "exec-10" começa igual a "exec-1", mas é outra execução
    assert ler("conta-a/exec-10/b.pdf") == b"3"
    assert ler("conta-b/exec-1/c.pdf") == b"4"


def test_nunca_apaga_a_raiz(destino: str) -> None:
    for prefixo in ("", "/"):
        with pytest.raises(ValueError, match="raiz"):
            storage.delete_tree(prefixo)


@pytest.mark.parametrize(
    "chave",
    ["../fora/segredo.env", "conta-a/../../segredo.env", "/etc/passwd", "conta-a\\..\\x", "a//b"],
)
def test_chave_nao_sai_da_pasta_da_conta(destino: str, chave: str) -> None:
    with pytest.raises(NotFoundError):
        storage.open_for_read(chave)
    with pytest.raises(NotFoundError):
        storage.save_bytes(chave, b"x")


def test_no_bucket_nada_vai_para_o_disco(no_bucket: None) -> None:
    storage.save_bytes("conta-a/exec-1/a.pdf", b"1")

    assert chaves_no_bucket() == ["conta-a/exec-1/a.pdf"]
    assert not (settings.storage_dir / "conta-a" / "exec-1" / "a.pdf").exists()


def test_foto_de_perfil_vai_e_volta_pelo_bucket(
    no_bucket: None, api: TestClient, autenticado: Cabecalho
) -> None:
    assert enviar_foto(api, autenticado, imagem()).status_code == 200

    foto = api.get("/api/v1/account/avatar", headers=autenticado)

    assert foto.status_code == 200
    assert foto.headers["content-type"] == "image/webp"
    assert foto.content.startswith(b"RIFF")
    assert len(chaves_no_bucket()) == 1


def test_bucket_sem_chaves_nao_inicia() -> None:
    with pytest.raises(ValueError, match="S3_ACCESS_KEY_ID"):
        Settings(s3_bucket="ditto")
    # Vazio no .env quer dizer desligado: os arquivos ficam no disco
    assert Settings(s3_bucket="", s3_access_key_id="").s3_bucket is None
