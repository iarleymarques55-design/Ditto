"""Linhas de trabalho do worker: cada conta conectada roda em paralelo, sem esperar as outras."""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from typing import Any

import pytest

from app.core.config import settings
from app.services import worker_tasks
from app.services.ai_explorer import BrowserUnavailableError
from app.services.worker_pool import WorkerPool

ESPERA_S = 5


def esperar(condicao: Callable[[], Any]) -> None:
    limite = time.monotonic() + ESPERA_S
    while time.monotonic() < limite:
        if condicao():
            return
        time.sleep(0.02)
    raise AssertionError("A condição não aconteceu a tempo.")


class NavegadorFalso:
    def __init__(self, dono: Any) -> None:
        self.dono = dono
        self.fechado = False

    def is_connected(self) -> bool:
        return not self.fechado

    def close(self) -> None:
        self.fechado = True


class ReleFalso:
    def __init__(self, *contas: uuid.UUID) -> None:
        self.contas = list(contas)

    def connected_users(self) -> list[uuid.UUID]:
        return list(self.contas)

    def cdp_url_for(self, user_id: uuid.UUID) -> str:
        return f"ws://127.0.0.1:1/cdp/segredo/{user_id}"


class Fila:
    """Faz o papel das execuções: anota quem pegou e pode prender uma conta numa tarefa longa."""

    def __init__(self) -> None:
        self.atendidas: list[Any] = []
        self.presas: dict[Any, threading.Event] = {}
        self.falhas_de_ligacao: set[Any] = set()

    def rodar(
        self, _fabrica: Any, navegador: NavegadorFalso, owner_id: Any = None, **_extras: Any
    ) -> bool:
        self.atendidas.append(owner_id)
        if owner_id in self.presas:
            # Uma execução de 500 linhas, ou o Criar com IA esperando a resposta da pessoa
            self.presas[owner_id].wait(ESPERA_S)
        return False

    def rascunho(self, _fabrica: Any, navegador: NavegadorFalso, owner_id: Any) -> bool:
        if owner_id in self.falhas_de_ligacao:
            self.falhas_de_ligacao.discard(owner_id)
            raise BrowserUnavailableError
        return False


@pytest.fixture
def fila(monkeypatch: pytest.MonkeyPatch) -> Fila:
    fila = Fila()
    monkeypatch.setattr(worker_tasks, "process_next_run", fila.rodar)
    monkeypatch.setattr(worker_tasks, "process_next_draft", fila.rascunho)
    monkeypatch.setattr(settings, "worker_poll_seconds", 0.02)
    return fila


@pytest.fixture
def parar() -> Iterator[threading.Event]:
    evento = threading.Event()
    yield evento
    evento.set()


def piscina(
    rele: ReleFalso | None, parar: threading.Event, abertos: list[NavegadorFalso]
) -> WorkerPool:
    def conectar(_playwright: Any, url: str) -> NavegadorFalso:
        navegador = NavegadorFalso(uuid.UUID(url.rsplit("/", 1)[-1]))
        abertos.append(navegador)
        return navegador

    def lancar(_playwright: Any) -> NavegadorFalso:
        navegador = NavegadorFalso(None)
        abertos.append(navegador)
        return navegador

    return WorkerPool(rele, parar, playwright_factory=nullcontext, launch=lancar, connect=conectar)


def test_conta_presa_numa_tarefa_longa_nao_segura_as_outras(
    fila: Fila, parar: threading.Event
) -> None:
    ana, bia = uuid.uuid4(), uuid.uuid4()
    fila.presas[ana] = threading.Event()
    abertos: list[NavegadorFalso] = []
    trabalho = piscina(ReleFalso(ana, bia), parar, abertos)

    trabalho.refresh()

    # A Ana está presa, e mesmo assim a fila da Bia anda várias vezes
    esperar(lambda: fila.atendidas.count(bia) >= 3)
    assert fila.atendidas.count(ana) == 1
    # Cada conta no próprio navegador
    assert {navegador.dono for navegador in abertos} == {ana, bia}
    fila.presas[ana].set()


def test_linha_termina_quando_a_pessoa_desconecta(fila: Fila, parar: threading.Event) -> None:
    ana, bia = uuid.uuid4(), uuid.uuid4()
    rele = ReleFalso(ana, bia)
    abertos: list[NavegadorFalso] = []
    trabalho = piscina(rele, parar, abertos)
    trabalho.refresh()
    esperar(lambda: len(trabalho.lanes()) == 2)

    rele.contas.remove(bia)

    esperar(lambda: [linha.owner_id for linha in trabalho.lanes()] == [ana])
    # O Chrome da Bia foi solto
    assert next(navegador for navegador in abertos if navegador.dono == bia).fechado


def test_pessoa_que_conecta_depois_ganha_a_propria_linha(
    fila: Fila, parar: threading.Event
) -> None:
    ana, bia = uuid.uuid4(), uuid.uuid4()
    rele = ReleFalso(ana)
    trabalho = piscina(rele, parar, [])
    trabalho.refresh()
    esperar(lambda: len(trabalho.lanes()) == 1)

    rele.contas.append(bia)
    trabalho.refresh()

    esperar(lambda: bia in fila.atendidas)
    assert {linha.owner_id for linha in trabalho.lanes()} == {ana, bia}


def test_ligacao_que_cai_e_aberta_de_novo_so_naquela_conta(
    fila: Fila, parar: threading.Event
) -> None:
    ana, bia = uuid.uuid4(), uuid.uuid4()
    fila.falhas_de_ligacao.add(ana)
    abertos: list[NavegadorFalso] = []
    trabalho = piscina(ReleFalso(ana, bia), parar, abertos)

    trabalho.refresh()

    esperar(lambda: [navegador.dono for navegador in abertos].count(ana) == 2)
    assert [navegador.dono for navegador in abertos].count(bia) == 1


def test_limite_de_contas_ao_mesmo_tempo(
    fila: Fila, parar: threading.Event, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "worker_max_accounts", 2)
    contas = [uuid.uuid4() for _ in range(3)]
    trabalho = piscina(ReleFalso(*contas), parar, [])

    trabalho.refresh()

    esperar(lambda: len(trabalho.lanes()) == 2)
    assert {linha.owner_id for linha in trabalho.lanes()} == set(contas[:2])


def test_sem_extensao_varias_linhas_dividem_a_fila(
    fila: Fila, parar: threading.Event, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "worker_concurrency", 3)
    abertos: list[NavegadorFalso] = []
    trabalho = piscina(None, parar, abertos)

    trabalho.refresh()

    esperar(lambda: len(trabalho.lanes()) == 3)
    # Cada linha com o seu Chromium, e nenhuma presa a uma conta
    assert len(abertos) == 3
    assert {linha.owner_id for linha in trabalho.lanes()} == {None}


def test_desligar_o_worker_fecha_todos_os_navegadores(fila: Fila, parar: threading.Event) -> None:
    abertos: list[NavegadorFalso] = []
    trabalho = piscina(ReleFalso(uuid.uuid4(), uuid.uuid4()), parar, abertos)
    trabalho.refresh()
    esperar(lambda: len(abertos) == 2)

    parar.set()
    trabalho.join(ESPERA_S)

    assert trabalho.lanes() == []
    assert all(navegador.fechado for navegador in abertos)
