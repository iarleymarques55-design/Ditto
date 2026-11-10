"""Regras puras, sem banco nem navegador."""

import io
import socket
import struct
import time

import pytest
from openpyxl import Workbook

from app.core.encryption import decrypt_json, encrypt_json
from app.core.exceptions import BusinessRuleError, PayloadTooLargeError
from app.models.enums import StepAction
from app.services.batch import neutralize_cell, normalize_column, parse_rows
from app.services.engine import matcher
from app.services.engine.browser import host_matches, is_request_allowed
from app.services.engine.egress_proxy import (
    EgressProxy,
    default_policy,
    is_public_address,
    resolve_allowed,
)
from app.services.engine.safety import looks_irreversible
from app.services.engine.snapshot import PageElement
from app.services.sanitizer import SecretLeakError, build_repair_payload, scrub, value_shape
from app.services.templating import render, safe_relative_path


def test_navegador_fechando_a_conexao_nao_suja_o_terminal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # O navegador fecha ao fim de cada linha, e as conexões abertas caem de forma abrupta
    proxy = EgressProxy(lambda _host, _address: True)
    with socket.create_server(("127.0.0.1", 0)) as destino:
        porta = destino.getsockname()[1]
        endereco_proxy = proxy.url.removeprefix("http://").split(":")
        navegador = socket.create_connection((endereco_proxy[0], int(endereco_proxy[1])))
        navegador.sendall(f"CONNECT 127.0.0.1:{porta} HTTP/1.1\r\n\r\n".encode())
        assert b"200" in navegador.recv(1024)

        # Fecha como quem cai: o outro lado recebe um erro, e não um fim de conexão normal
        navegador.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        navegador.close()
        time.sleep(0.5)
    proxy.stop()

    assert "Traceback" not in capsys.readouterr().err


def elemento(indice: int = 0, **campos) -> PageElement:
    campos.setdefault("role", "button")
    campos.setdefault("tag", "button")
    return PageElement(index=indice, **campos)


# Planilhas


def test_csv_com_ponto_e_virgula_e_acento_no_cabecalho() -> None:
    conteudo = "\ufeffLoja;Mês;Extra\nLoja 01;09/2026;x\n\n Loja 02 ;10/2026;y\n".encode()
    linhas = parse_rows("a.csv", conteudo, ["loja", "mes"])
    assert linhas == [{"loja": "Loja 01", "mes": "09/2026"}, {"loja": "Loja 02", "mes": "10/2026"}]


def test_csv_em_cp1252_do_excel_portugues() -> None:
    conteudo = "loja\nSão Paulo\n".encode("cp1252")
    assert parse_rows("a.csv", conteudo, ["loja"]) == [{"loja": "São Paulo"}]


def test_csv_com_aspas_e_virgula_dentro_do_valor() -> None:
    linhas = parse_rows("a.csv", b'loja,obs\n"Loja, Centro",x\n', ["loja"])
    assert linhas == [{"loja": "Loja, Centro"}]


def test_excel_mantem_zero_a_esquerda_e_ignora_colunas_extras() -> None:
    planilha = Workbook()
    planilha.active.append(["CNPJ", "Nome"])
    planilha.active.append(["00123", "A"])
    buffer = io.BytesIO()
    planilha.save(buffer)
    assert parse_rows("a.xlsx", buffer.getvalue(), ["cnpj"]) == [{"cnpj": "00123"}]


@pytest.mark.parametrize(
    ("nome", "conteudo", "mensagem"),
    [
        ("a.csv", b"nome\nA\n", "Faltam as colunas loja"),
        ("a.csv", b"loja\n", "cabe\u00e7alho"),
        ("a.csv", b"", "vazia"),
        ("a.exe", b"loja\nA", ".csv ou .xlsx"),
        ("a.xlsx", b"isto nao e um excel", "Excel"),
    ],
)
def test_planilhas_invalidas_explicam_o_problema(nome: str, conteudo: bytes, mensagem: str) -> None:
    with pytest.raises(BusinessRuleError, match=mensagem):
        parse_rows(nome, conteudo, ["loja"])


def test_planilha_acima_do_limite_de_linhas() -> None:
    conteudo = ("loja\n" + "x\n" * 501).encode()
    with pytest.raises(BusinessRuleError, match="500"):
        parse_rows("a.csv", conteudo, ["loja"])


def test_planilha_acima_do_tamanho() -> None:
    with pytest.raises(PayloadTooLargeError):
        parse_rows("a.csv", b"x" * (5 * 1024 * 1024 + 1), ["loja"])


def test_normaliza_coluna() -> None:
    assert normalize_column(" Mês ") == "mes"


@pytest.mark.parametrize("valor", ["=1+1", "+55", "-1", "@SOMA(A1)"])
def test_celula_que_viraria_formula_e_neutralizada(valor: str) -> None:
    assert neutralize_cell(valor) == f"'{valor}"


# Caminhos de arquivo


def test_caminho_normal() -> None:
    assert safe_relative_path(
        "relatorios/{mes}/{loja}.pdf", {"mes": "09-2026", "loja": "Loja 01"}, "x"
    ) == ("relatorios/09-2026/Loja 01.pdf")


@pytest.mark.parametrize(
    "valor", ["../../etc/passwd", "..\\..\\windows", "a/b/c", "/etc/passwd", "C:\\windows"]
)
def test_valor_da_planilha_nunca_cria_pasta_nem_sai_da_execucao(valor: str) -> None:
    caminho = safe_relative_path("saida/{loja}.pdf", {"loja": valor}, "x")
    partes = caminho.split("/")
    assert len(partes) == 2
    assert ".." not in partes
    assert partes[0] == "saida"


@pytest.mark.parametrize("modelo", ["/absoluto/{a}", "C:\\pasta\\{a}", "../fora/{a}", "a/../../b"])
def test_modelo_de_caminho_inseguro_e_recusado(modelo: str) -> None:
    with pytest.raises(BusinessRuleError):
        safe_relative_path(modelo, {"a": "x"}, "x")


def test_variavel_ausente_explica_qual_faltou() -> None:
    with pytest.raises(BusinessRuleError, match="loja"):
        render("{loja}", {})


# Camada 2


def test_botao_renomeado_com_vizinhos_iguais_passa_do_limiar() -> None:
    alvo = {"role": "button", "text": "Exportar PDF", "neighbors": ["Imprimir", "Excel"]}
    candidatos = matcher.rank(
        alvo,
        StepAction.CLICK,
        [
            elemento(0, text="Exportar em PDF", neighbors=["Imprimir", "Excel"]),
            elemento(1, text="Imprimir", neighbors=["Exportar em PDF", "Excel"]),
        ],
    )
    assert candidatos[0].element.index == 0
    assert matcher.is_confident(candidatos, 0.75, 0.05)


def test_botao_muito_diferente_fica_abaixo_do_limiar() -> None:
    alvo = {"role": "button", "text": "Exportar PDF", "neighbors": ["Imprimir", "Excel"]}
    candidatos = matcher.rank(alvo, StepAction.CLICK, [elemento(0, text="Falar com o suporte")])
    assert not matcher.is_confident(candidatos, 0.75, 0.05)


def test_empate_e_duvida_mesmo_com_nota_alta() -> None:
    alvo = {"role": "button", "text": "Exportar PDF"}
    candidatos = matcher.rank(
        alvo,
        StepAction.CLICK,
        [elemento(0, text="Exportar PDF A"), elemento(1, text="Exportar PDF B")],
    )
    assert candidatos[0].score >= 0.75
    assert not matcher.is_confident(candidatos, 0.75, 0.05)


def test_nao_digita_em_botao_nem_clica_em_campo() -> None:
    botao = elemento(0, text="Salvar")
    campo = elemento(1, role="textbox", tag="input", label="Salvar")
    assert not matcher.is_compatible(StepAction.FILL, botao)
    assert matcher.is_compatible(StepAction.FILL, campo)
    assert not matcher.is_compatible(StepAction.CLICK, campo)


@pytest.mark.parametrize("texto", ["Pagar boleto", "Enviar declaração", "Excluir", "CONFIRMAR"])
def test_palavras_sem_volta_sao_reconhecidas(texto: str) -> None:
    assert looks_irreversible(texto)


@pytest.mark.parametrize("texto", ["Exportar PDF", "Pesquisar", "Enviado em 05/10", None])
def test_palavras_comuns_nao_viram_alarme(texto: str | None) -> None:
    assert not looks_irreversible(texto)


# Sanitizador: o único caminho até a IA


def test_scrub_remove_o_segredo_sem_diferenciar_maiusculas() -> None:
    assert "HUNTER2" not in scrub("senha HUNTER2 aqui", ["hunter2"]).upper()


def test_scrub_troca_primeiro_o_segredo_maior() -> None:
    assert scrub("abc123", ["abc", "abc123"]) == "[oculto]"


def test_formato_do_valor_nao_revela_o_conteudo() -> None:
    assert value_shape("Loja 07") == "aaaa 99"


def test_pedido_de_reparo_nao_leva_segredo_em_nenhum_campo() -> None:
    segredo = "senha-marcada-xyz"
    corpo = build_repair_payload(
        f"Entrar com {segredo}",
        "click",
        {"text": segredo, "label": segredo, "neighbors": [segredo]},
        [elemento(0, text=f"Olá {segredo}", label=segredo, placeholder=segredo)],
        [segredo],
    )
    assert segredo not in corpo


def test_segredo_de_tres_letras_tambem_e_protegido() -> None:
    assert "abc" not in build_repair_payload("x", "click", {}, [elemento(0, text="abc")], ["abc"])


def test_trava_final_cancela_se_algo_escapar(monkeypatch: pytest.MonkeyPatch) -> None:
    # Se o scrub falhar por qualquer motivo, a última verificação ainda impede o envio
    monkeypatch.setattr("app.services.sanitizer.scrub", lambda texto, _: texto)
    with pytest.raises(SecretLeakError):
        build_repair_payload("x", "click", {}, [elemento(0, text="segredo-abc")], ["segredo-abc"])


# Criptografia e proteção de rede


def test_credencial_cifrada_nao_contem_a_senha() -> None:
    cifrado = encrypt_json({"password": "senha-do-portal"})
    assert "senha-do-portal" not in cifrado
    assert decrypt_json(cifrado)["password"] == "senha-do-portal"


def test_dominio_e_subdominio_permitidos() -> None:
    assert host_matches("portal.exemplo.com", ["exemplo.com"])
    assert host_matches("exemplo.com", ["exemplo.com"])
    assert not host_matches("exemplo.com.golpe.net", ["exemplo.com"])
    assert not host_matches("naoexemplo.com", ["exemplo.com"])


@pytest.mark.parametrize(
    "endereco",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "0.0.0.0",  # noqa: S104
        "224.0.0.1",
    ],
)
def test_endereco_interno_nao_e_publico(endereco: str) -> None:
    assert not is_public_address(endereco)


def test_endereco_publico_e_reconhecido() -> None:
    assert is_public_address("8.8.8.8")


def test_em_producao_a_politica_recusa_a_rede_interna(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.engine.egress_proxy.settings.allow_private_networks", False)
    assert not default_policy("localhost", "127.0.0.1")
    assert default_policy("exemplo.com", "8.8.8.8")


def test_nome_com_um_endereco_interno_entre_os_publicos_e_recusado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DNS pode devolver vários IPs: um único interno recusa o nome inteiro
    respostas = [(2, 1, 6, "", ("8.8.8.8", 80)), (2, 1, 6, "", ("10.0.0.1", 80))]
    monkeypatch.setattr("socket.getaddrinfo", lambda *_a, **_k: respostas)
    assert resolve_allowed("golpe.exemplo", 80, lambda _h, ip: is_public_address(ip)) == []


def test_esquema_diferente_de_http_e_bloqueado() -> None:
    assert not is_request_allowed("file:///etc/passwd", is_navigation=True, allowed_domains=[""])


def test_navegacao_fora_dos_dominios_da_tarefa_e_bloqueada() -> None:
    assert not is_request_allowed(
        "http://outro.com/", is_navigation=True, allowed_domains=["exemplo.com"]
    )
