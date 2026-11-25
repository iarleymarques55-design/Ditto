"""Relé da extensão: nomes de arquivo vindos de fora e conexões que só ocupam vaga."""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from app.services.engine import extension_relay
from app.services.engine.extension_relay import (
    _DOWNLOAD_GUID,
    _MAX_PENDING_PER_IP,
    ExtensionRelay,
    RelayError,
    _inside,
    _is_plain_file,
)
from tests.test_executor_extensao import ESPERA_S, autenticador

# C1: o "guid" do download vinha da extensão e virava parte do caminho do arquivo no worker


@pytest.mark.parametrize(
    "guid",
    [
        "../../home/ditto/.local/lib/python3.12/site-packages/x.pth",
        "..\\..\\Windows\\x.dll",
        "/etc/passwd",
        "C:\\Windows\\x",
        "a/b",
        "..",
        "",
    ],
)
def test_guid_que_tenta_sair_da_pasta_e_recusado(guid: str, tmp_path: Path) -> None:
    assert not _DOWNLOAD_GUID.fullmatch(guid)
    with pytest.raises(RelayError):
        _inside(tmp_path, guid)


def test_guid_do_chrome_fica_dentro_da_pasta(tmp_path: Path) -> None:
    guid = str(uuid.uuid4())
    destino = _inside(tmp_path, guid)
    assert destino.parent == tmp_path.resolve()
    assert destino.name == guid


def test_copia_local_so_aceita_arquivo_comum_e_pequeno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arquivo = tmp_path / "relatorio.csv"
    arquivo.write_bytes(b"a" * 100)
    assert _is_plain_file(arquivo)
    assert not _is_plain_file(tmp_path)
    assert not _is_plain_file(tmp_path / "nao-existe")

    monkeypatch.setattr(extension_relay, "_MAX_DOWNLOAD_BYTES", 10)
    assert not _is_plain_file(arquivo)


def test_atalho_para_outro_arquivo_nao_e_copiado(tmp_path: Path) -> None:
    segredo = tmp_path / "segredo.env"
    segredo.write_text("JWT_SECRET=...")
    atalho = tmp_path / "download.csv"
    try:
        atalho.symlink_to(segredo)
    except OSError:
        pytest.skip("Este Windows não deixa criar atalhos sem permissão de administrador.")
    assert not _is_plain_file(atalho)


# M12: um script abria centenas de conexões sem token e ninguém mais conseguia ligar


def test_conexoes_sem_token_do_mesmo_ip_tem_limite(
    fabrica_sessao: sessionmaker[Session],
) -> None:
    relay = ExtensionRelay(0, autenticador(fabrica_sessao))
    relay.start()
    abertas = []
    try:
        url = f"ws://127.0.0.1:{relay.port}/extension"
        for _ in range(_MAX_PENDING_PER_IP):
            abertas.append(connect(url, origin="chrome-extension://abc"))

        with connect(url, origin="chrome-extension://abc") as excedente:
            with pytest.raises(ConnectionClosed) as fechamento:
                excedente.recv(timeout=ESPERA_S)
        assert fechamento.value.rcvd is not None and fechamento.value.rcvd.code == 1013

        # Quem se apresenta (mesmo com token errado) libera a vaga
        abertas[0].send(json.dumps({"type": "hello", "token": "errado"}))
        with pytest.raises(ConnectionClosed):
            abertas[0].recv(timeout=ESPERA_S)
        with connect(url, origin="chrome-extension://abc") as nova:
            nova.send(json.dumps({"type": "hello", "token": "errado"}))
            with pytest.raises(ConnectionClosed) as recusa:
                nova.recv(timeout=ESPERA_S)
        assert recusa.value.rcvd is not None and recusa.value.rcvd.code == 4401
    finally:
        for conexao in abertas:
            conexao.close()
        relay.stop()


def test_extensao_de_outra_origem_aparece_no_log(
    fabrica_sessao: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    # Com EXTENSION_ORIGINS desatualizado, a recusa era silenciosa e a extensão só dizia
    # "esperando o Ditto responder"
    relay = ExtensionRelay(
        0, autenticador(fabrica_sessao), allowed_origins=["chrome-extension://id-certo"]
    )
    relay.start()
    try:
        with caplog.at_level("WARNING"):
            with connect(
                f"ws://127.0.0.1:{relay.port}/extension", origin="chrome-extension://id-antigo"
            ) as conexao:
                with pytest.raises(ConnectionClosed):
                    conexao.recv(timeout=ESPERA_S)
        assert "chrome-extension://id-antigo" in caplog.text
        assert "EXTENSION_ORIGINS" in caplog.text
    finally:
        relay.stop()
