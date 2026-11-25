"""Único caminho de saída de dados para a IA. Nada chega ao LLM sem passar por aqui."""

import json
import re
from collections.abc import Iterable
from typing import Any

from app.core.config import settings
from app.services.engine.snapshot import PageElement

MAX_ELEMENTS = 150
MAX_TEXT = 120
MAX_SCREEN_TEXT = 1500
# O mínimo que ainda deixa a IA navegar quando a tela é enorme
_MIN_ELEMENTS = 40
_MIN_SCREEN_TEXT = 600
_MIN_SECRET_LENGTH = 3


class SecretLeakError(Exception):
    """O conteúdo montado ainda contém um segredo: a chamada à IA é cancelada."""


def _usable(secrets: Iterable[str]) -> list[str]:
    # Valores curtos demais ("1", "sim") apagariam partes comuns do texto sem proteger nada.
    # Do maior para o menor: um segredo pode conter outro.
    return sorted(
        {secret for secret in secrets if secret and len(secret) >= _MIN_SECRET_LENGTH},
        key=len,
        reverse=True,
    )


def scrub(text: str, secrets: Iterable[str]) -> str:
    cleaned = text
    for secret in _usable(secrets):
        cleaned = re.sub(re.escape(secret), "[oculto]", cleaned, flags=re.IGNORECASE)
    return cleaned


# Dados pessoais que aparecem soltos na tela (CPF, CNPJ, cartão, conta) não ajudam a IA a navegar
# e não precisam sair para o serviço externo
_PERSONAL_NUMBERS = re.compile(
    r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"  # CPF
    r"|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"  # CNPJ
    r"|\b(?:\d[ -]?){13,19}\b"  # cartão
    r"|\b\d{9,}\b"  # CPF sem pontos, conta, telefone, protocolo longo
)


def mask_personal_data(text: str) -> str:
    return _PERSONAL_NUMBERS.sub("[número oculto]", text)


def _short(text: str | None, secrets: list[str]) -> str:
    return scrub(text or "", secrets)[:MAX_TEXT]


def value_shape(value: str | None) -> str:
    """Só o formato do valor: "Loja 07" vira "aaaa 99". O conteúdo nunca sai daqui."""
    if not value:
        return ""
    return re.sub(r"[^\W\d]", "a", re.sub(r"\d", "9", value))[:40]


def _assert_clean(payload: str, secrets: list[str]) -> str:
    lowered = payload.lower()
    if any(secret.lower() in lowered for secret in secrets):
        raise SecretLeakError("O conteúdo para a IA ainda contém um valor protegido.")
    return payload


def build_repair_payload(
    intent: str,
    action: str,
    recorded_target: dict[str, Any],
    elements: list[PageElement],
    secrets: Iterable[str],
    already_clicked: Iterable[str] = (),
) -> str:
    """Monta o pedido de reparo. O valor dos campos nunca é coletado (ver snapshot.py)."""
    protected = _usable(secrets)
    data = {
        "objetivo_do_passo": _short(intent, protected),
        "acao": action,
        "elemento_gravado": {
            "papel": recorded_target.get("role"),
            "texto": _short(recorded_target.get("text"), protected),
            "rotulo": _short(recorded_target.get("label"), protected),
            "vizinhos": [_short(item, protected) for item in recorded_target.get("neighbors", [])][
                :5
            ],
        },
        "ja_clicados": [_short(item, protected) for item in already_clicked],
        "elementos_da_pagina": [
            {
                "indice": element.index,
                "papel": element.role,
                "tag": element.tag,
                "texto": _short(element.text, protected),
                "rotulo": _short(element.label, protected),
                "dica": _short(element.placeholder, protected),
            }
            for element in elements[:MAX_ELEMENTS]
        ],
    }
    return _assert_clean(json.dumps(data, ensure_ascii=False), protected)


def build_analysis_payload(steps: list[dict[str, Any]], secrets: Iterable[str]) -> str:
    """Monta o pedido de análise da gravação, com o formato dos valores em vez dos valores."""
    protected = _usable(secrets)
    data = [
        {
            "posicao": step["position"],
            "acao": step["action"],
            "texto": _short(step.get("text"), protected),
            "rotulo": _short(step.get("label"), protected),
            "formato_do_valor": value_shape(step.get("value")),
        }
        for step in steps
    ]
    return _assert_clean(json.dumps(data, ensure_ascii=False), protected)


def _page_address(url: str) -> str:
    """Sem a parte depois do "?": ela costuma levar tokens de sessão."""
    return url.split("?", 1)[0].split("#", 1)[0][:300]


_FIELD_ROLES = {"textbox", "searchbox", "combobox", "listbox", "checkbox", "radio", "switch"}


def _most_useful(elements: list[PageElement], limit: int = MAX_ELEMENTS) -> list[PageElement]:
    """Num site com barra lateral cheia de links (como o histórico de um chat), cortar pela ordem
    da página deixava a caixa de texto de fora, e a IA perguntava à pessoa onde ela estava.
    Campos vêm primeiro, depois o conteúdo, e por último menus e barras laterais."""

    def rank(element: PageElement) -> int:
        if element.role in _FIELD_ROLES:
            return 0
        return 2 if element.in_menu else 1

    chosen = sorted(elements, key=rank)[:limit]
    return sorted(chosen, key=lambda element: element.index)


def build_explorer_payload(
    *,
    prompt: str,
    url: str,
    title: str,
    done: list[str],
    last_result: str,
    answers: list[dict[str, str]],
    captured: list[str],
    steps_left: int,
    elements: list[PageElement],
    options: dict[int, list[str]],
    screen_data: list[Any],
    screen_text: str = "",
    spreadsheet: bool = False,
    questions_left: int = 0,
    secrets: Iterable[str] = (),
) -> str:
    """Monta o pedido da IA que cria tarefas. O valor dos campos nunca é coletado (snapshot.py).

    O pacote tem teto (LLM_MAX_PAYLOAD_CHARS): numa página enorme, como o Google Agenda, saem
    primeiro os elementos menos úteis (menus, depois conteúdo; campos por último), depois os
    dados da tela e por fim parte do texto da tela."""
    protected = _usable(secrets)
    budget = settings.llm_max_payload_chars
    limit, data_limit, text_limit = MAX_ELEMENTS, len(screen_data), MAX_SCREEN_TEXT
    while True:
        payload = _explorer_json(
            prompt=prompt,
            url=url,
            title=title,
            done=done,
            last_result=last_result,
            answers=answers,
            captured=captured,
            steps_left=steps_left,
            elements=_most_useful(elements, limit),
            options=options,
            screen_data=screen_data[:data_limit],
            screen_text=screen_text[:text_limit],
            spreadsheet=spreadsheet,
            questions_left=questions_left,
            protected=protected,
        )
        if len(payload) <= budget:
            return _assert_clean(payload, protected)
        if limit > _MIN_ELEMENTS:
            limit = max(_MIN_ELEMENTS, int(limit * 0.75))
        elif data_limit > 0:
            data_limit = data_limit // 2
        elif text_limit > _MIN_SCREEN_TEXT:
            text_limit = _MIN_SCREEN_TEXT
        else:
            # O mínimo útil já passa do teto: manda assim mesmo e a IA diz se não couber
            return _assert_clean(payload, protected)


def _explorer_json(
    *,
    prompt: str,
    url: str,
    title: str,
    done: list[str],
    last_result: str,
    answers: list[dict[str, str]],
    captured: list[str],
    steps_left: int,
    elements: list[PageElement],
    options: dict[int, list[str]],
    screen_data: list[Any],
    screen_text: str,
    spreadsheet: bool,
    questions_left: int,
    protected: list[str],
) -> str:
    data = {
        "pedido_da_pessoa": scrub(prompt, protected)[:2000],
        "endereco_atual": _short(_page_address(url), protected),
        "titulo_da_pagina": _short(title, protected),
        # Sem o texto da tela a IA só vê botões e campos, e passa a supor o resultado de cada passo
        "texto_da_tela": mask_personal_data(scrub(screen_text, protected))[:MAX_SCREEN_TEXT],
        "planilha_excel_aberta": spreadsheet,
        "perguntas_restantes": questions_left,
        "passos_ja_feitos": [_short(item, protected) for item in done[-30:]],
        "resultado_do_ultimo_passo": _short(last_result, protected),
        "respostas_da_pessoa": [
            {
                "pergunta": _short(item["pergunta"], protected),
                "resposta": _short(item["resposta"], protected),
            }
            for item in answers[-10:]
        ],
        "dados_ja_guardados": [_short(item, protected) for item in captured],
        "passos_que_ainda_cabem": steps_left,
        "elementos_da_pagina": [
            {
                "indice": element.index,
                "papel": element.role,
                "tag": element.tag,
                "texto": _short(element.text, protected),
                "rotulo": _short(element.label, protected),
                "dica": _short(element.placeholder, protected),
                "tipo": element.input_type,
                **({"no_menu": True} if element.in_menu else {}),
                **({"pergunta": _short(element.group, protected)} if element.group else {}),
                **(
                    {"opcoes": [_short(item, protected) for item in options[element.index]]}
                    if element.index in options
                    else {}
                ),
            }
            for element in elements
        ],
        "dados_na_tela": [
            (
                {
                    "indice": item.index,
                    "tipo": "tabela",
                    "colunas": [_short(column, protected) for column in item.columns],
                    "linhas": item.rows,
                    "primeira_linha": [_short(cell, protected) for cell in item.sample],
                }
                if item.kind == "table"
                else {
                    "indice": item.index,
                    "tipo": "valor",
                    "rotulo": _short(item.anchor, protected),
                    "exemplo": _short(item.sample, protected),
                }
            )
            for item in screen_data
        ],
    }
    return json.dumps(data, ensure_ascii=False)
