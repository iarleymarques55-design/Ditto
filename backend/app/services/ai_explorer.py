"""Worker: a IA monta uma tarefa no Chrome da pessoa, um passo por vez, a partir de um pedido
escrito. O resultado é uma gravação comum, que segue para análise e revisão como as da extensão.

As travas não dependem da IA: senha nunca é digitada, botão que parece não ter volta, valor
que não veio do pedido e domínio novo só passam com a resposta da pessoa no painel."""

import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Download, Locator, Page
from playwright.sync_api import Error as PlaywrightError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_draft import AiDraft
from app.models.enums import AiDraftStatus, StepAction
from app.repositories.ai_draft_repository import OPEN_STATUSES, AiDraftRepository
from app.schemas.flow import RecordedStep, RecordingCreate
from app.services import sanitizer
from app.services.engine import capture, postcondition
from app.services.engine.browser import ItemTabs, host_matches
from app.services.engine.llm_explorer import ExplorerDecision, LlmExplorer
from app.services.engine.safety import looks_irreversible
from app.services.engine.screen_data import ScreenData, collect_screen_data, select_options
from app.services.engine.snapshot import (
    PageElement,
    frame_locator_for,
    has_captcha,
    has_login_form,
    take_snapshot_with_frames,
)
from app.services.flow_service import FlowService
from app.services.templating import slugify

logger = logging.getLogger(__name__)

_LOAD_WAIT_MS = 3000
_POLL_MS = 150
_QUIET_SECONDS = 0.5
_SETTLE_MAX_SECONDS = 4
_DOWNLOAD_WAIT_SECONDS = 3
_ANSWER_POLL_SECONDS = 1.0
_HEARTBEAT_SECONDS = 30
_MAX_LLM_FAILURES = 3
_MAX_EVENTS = 300
_ALLOWED_KEYS = {"Enter", "Tab", "Escape"}
_TYPING_DELAY_MS = 10
_PREVIEW_CELLS = 6
# Os mesmos alvos que a extensão grava no Excel Online (extension/recorder.js)
_NAME_BOX = {
    "css": "#FormulaBar-NameBox-input",
    "tag": "input",
    "role": "combobox",
    "label": "Caixa de Nome",
}
_FORMULA_BAR = {
    "css": "#formulaBarTextDivId_textElement",
    "tag": "div",
    "role": "textbox",
    "label": "formula bar",
}

YES_CLICK = "Pode clicar"
NO_CLICK = "Não clique"
YES_TYPE = "Pode digitar"
NO_TYPE = "Não, é outro valor"
YES_CELLS = "Pode escrever"
NO_CELLS = "Não escreva"
YES_HOST = "Liberar"
NO_HOST = "Não liberar"
LOGGED_IN = "Já entrei"
NO_LOGIN = "Não precisa de login"
SOLVED = "Já resolvi"
SAVE_PARTIAL = "Salvar assim"
STOP = "Parar"

_DONE = object()


class _Canceled(Exception):
    """A pessoa cancelou no painel."""


class _Failed(Exception):
    """A criação não tem como seguir. A mensagem aparece no painel."""


def _same(answer: str, option: str) -> bool:
    return answer.strip().casefold() == option.casefold()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _name_of(element: PageElement) -> str:
    return element.text or element.label or element.placeholder or element.name or element.role


class AiExplorer:
    def __init__(
        self,
        session: Session,
        draft: AiDraft,
        browser: Browser,
        llm: LlmExplorer | None = None,
    ) -> None:
        self.session = session
        self.draft = draft
        self.browser = browser
        self.llm = llm or LlmExplorer()
        self.drafts = AiDraftRepository(session)
        # Lista compartilhada com o filtro da aba: liberar um domínio vale na hora
        self.allowed: list[str] = [host for host in draft.allowed_hosts if host]
        self.blocked: list[str] = []
        self.done: list[str] = []
        self.answers: list[dict[str, str]] = []
        self.login_checked: set[str] = set()
        # Onde está cada elemento da última leitura, inclusive dentro de iframes
        self.locators: dict[int, Locator] = {}
        self.last_heartbeat = 0.0

    # ---------- banco ----------

    def _save(self, **values: Any) -> None:
        values["heartbeat_at"] = datetime.now(UTC)
        updated = self.drafts.update_if_open(self.draft.id, values)
        self.session.commit()
        self.session.refresh(self.draft)
        self.last_heartbeat = time.monotonic()
        if not updated:
            raise _Canceled

    def _check_open(self) -> None:
        self.session.refresh(self.draft)
        if self.draft.status not in OPEN_STATUSES:
            raise _Canceled
        if time.monotonic() - self.last_heartbeat >= _HEARTBEAT_SECONDS:
            self._save()

    def _event_entry(self, kind: str, text: str) -> list[dict[str, Any]]:
        entry = {"at": datetime.now(UTC).isoformat(), "kind": kind, "text": text[:300]}
        return [*(self.draft.events or []), entry][-_MAX_EVENTS:]

    def _event(self, kind: str, text: str) -> None:
        self._save(events=self._event_entry(kind, text))

    def _add_step(self, step: dict[str, Any], description: str) -> str | None:
        """Devolve um erro para a IA quando o passo não serve como gravação."""
        try:
            RecordedStep.model_validate(step)
        except ValidationError:
            logger.info("Passo descartado no rascunho %s", self.draft.id)
            return "erro: esse passo não pôde ser anotado. Tente outro caminho."
        self.done.append(description)
        self._save(
            steps=[*(self.draft.steps or []), step],
            events=self._event_entry("step", description),
        )
        return None

    def _ask(self, text: str, options: list[str]) -> str:
        self._save(
            status=AiDraftStatus.WAITING_ANSWER,
            question={"text": text[:400], "options": options[:4]},
            answer=None,
            events=self._event_entry("question", text),
        )
        deadline = time.monotonic() + settings.ai_draft_answer_timeout_seconds
        while time.monotonic() < deadline:
            time.sleep(_ANSWER_POLL_SECONDS)
            self._check_open()
            answer = self.draft.answer
            if answer is not None:
                self._save(
                    status=AiDraftStatus.RUNNING,
                    question=None,
                    answer=None,
                    events=self._event_entry("info", f"Você respondeu: {answer}"),
                )
                self.answers.append({"pergunta": text, "resposta": answer})
                return answer
        raise _Failed(
            "Ninguém respondeu à dúvida da IA a tempo. Peça de novo quando puder acompanhar."
        )

    def _stop_by_person(self) -> None:
        self._save(status=AiDraftStatus.CANCELED, question=None)
        raise _Canceled

    # ---------- navegador ----------

    def _settle(self, page: Page) -> None:
        """Espera a página parar de mudar. Uma animação sem fim só custa o tempo máximo."""
        try:
            page.wait_for_load_state("domcontentloaded", timeout=_LOAD_WAIT_MS)
            deadline = time.monotonic() + _SETTLE_MAX_SECONDS
            state = postcondition.capture_state(page).fingerprint
            quiet_since = time.monotonic()
            while time.monotonic() < deadline:
                page.wait_for_timeout(_POLL_MS)
                current = postcondition.capture_state(page).fingerprint
                if current != state:
                    state = current
                    quiet_since = time.monotonic()
                elif time.monotonic() - quiet_since >= _QUIET_SECONDS:
                    return
        except PlaywrightError:
            pass

    def _fingerprint(self, page: Page) -> str:
        try:
            return postcondition.capture_state(page).fingerprint
        except PlaywrightError:
            return ""

    def _click(self, page: Page, locator: Locator) -> Download | None:
        downloads: list[Download] = []

        # O Playwright só aceita funções Python como ouvinte, e não métodos embutidos
        def on_download(download: Download) -> None:
            downloads.append(download)

        page.on("download", on_download)
        try:
            before = self._fingerprint(page)
            locator.click()
            self._settle(page)
            # Um clique que baixa um arquivo costuma deixar a página igual
            if not downloads and self._fingerprint(page) == before:
                deadline = time.monotonic() + _DOWNLOAD_WAIT_SECONDS
                while not downloads and time.monotonic() < deadline:
                    page.wait_for_timeout(_POLL_MS)
        finally:
            page.remove_listener("download", on_download)
        return downloads[0] if downloads else None

    # ---------- passos ----------

    def _mentioned(self, value: str) -> bool:
        wanted = _normalize(value)
        sources = [self.draft.prompt, *(item["resposta"] for item in self.answers)]
        return any(wanted in _normalize(source) for source in sources)

    def _capture_names(self) -> set[str]:
        return {
            slugify(step["capture_name"])
            for step in self.draft.steps or []
            if step.get("action") == StepAction.CAPTURE.value and step.get("capture_name")
        }

    def _unique_capture_name(self, wanted: str) -> str:
        used = self._capture_names()
        name = wanted.strip()[:100] or "Dado"
        candidate, number = name, 2
        while slugify(candidate) in used:
            candidate = f"{name} {number}"
            number += 1
        return candidate

    def _capture(self, page: Page, decision: ExplorerDecision, data: list[ScreenData]) -> str:
        wants_table = decision.acao == "capturar_tabela"
        item = next((entry for entry in data if entry.index == decision.dado), None)
        if item is None or (item.kind == "table") != wants_table:
            return "erro: esse índice não está em dados_na_tela com esse tipo."

        target = item.to_target()
        if wants_table:
            rows = capture.read_table(page, target)
            if not rows:
                return "erro: não consegui ler essa tabela de novo. Escolha outra."
            name = self._unique_capture_name(decision.nome_do_dado or "Tabela")
            text = f'Guardar a tabela "{name}" ({len(rows)} linhas)'
        else:
            if capture.read_value(page, target) is None:
                return "erro: não consegui ler esse valor de novo. Escolha outro."
            name = self._unique_capture_name(decision.nome_do_dado or item.anchor)
            text = f'Guardar o dado "{name}"'

        step = {
            "action": StepAction.CAPTURE.value,
            "url": page.url,
            "target": target,
            "capture_name": name,
            "capture_kind": "table" if wants_table else "value",
        }
        return self._add_step(step, decision.descricao or text) or f"ok: {text.lower()}"

    def _open_address(self, page: Page, decision: ExplorerDecision) -> str:
        url = (decision.endereco or "").strip()
        host = _host_of(url)
        if urlsplit(url).scheme not in {"http", "https"} or not host:
            return "erro: endereço inválido. Use um endereço completo com https://."
        if not host_matches(host, self.allowed):
            answer = self._ask(
                f"A IA quer abrir {host}, que não estava no seu pedido. Posso liberar esse site?",
                [YES_HOST, NO_HOST],
            )
            if not _same(answer, YES_HOST):
                return f"A pessoa não liberou {host}. Siga sem ele."
            self._allow(host)
        page.goto(url, wait_until="domcontentloaded")
        self._settle(page)
        step = {"action": StepAction.NAVIGATE.value, "url": url}
        return self._add_step(step, decision.descricao or f"Abrir {host}") or f"ok: abriu {host}"

    def _allow(self, host: str) -> None:
        if host not in self.allowed:
            self.allowed.append(host)
        self._save(allowed_hosts=list(self.allowed))

    def _act_on_element(
        self, page: Page, decision: ExplorerDecision, elements: list[PageElement]
    ) -> str:
        element = next((entry for entry in elements if entry.index == decision.indice), None)
        if element is None:
            return "erro: esse índice não está em elementos_da_pagina."
        name = _name_of(element)
        locator = self.locators[element.index]
        step: dict[str, Any] = {"url": page.url, "target": element.to_target()}
        value = (decision.valor or "").strip()

        if decision.acao == "clicar":
            if looks_irreversible(f"{element.text} {element.label}"):
                answer = self._ask(
                    f'O botão "{name}" pode não ter volta (pagar, enviar, excluir...). Posso clicar?',
                    [YES_CLICK, NO_CLICK],
                )
                if not _same(answer, YES_CLICK):
                    return "A pessoa não quis esse clique. Se o pedido já foi cumprido, conclua."
            download = self._click(page, locator)
            step["action"] = StepAction.CLICK.value
            if download is not None:
                extension = download.suggested_filename.rsplit(".", 1)[-1].lower()
                if extension.isalnum() and len(extension) <= 10:
                    step["downloaded_extension"] = extension
                try:
                    download.delete()
                except PlaywrightError:
                    pass
            text = decision.descricao or f'Clicar em "{name}"'
            return self._add_step(step, text) or (
                "ok: um arquivo foi baixado" if download else "ok: clique feito"
            )

        if decision.acao == "digitar":
            if element.input_type == "password":
                return "erro: senhas não são digitadas pela IA. Peça para a pessoa entrar na conta."
            if not value:
                return "erro: falta o valor a digitar."
            if not self._mentioned(value):
                answer = self._ask(
                    f'Vou digitar "{value}" em "{name}". Está certo?', [YES_TYPE, NO_TYPE]
                )
                if not _same(answer, YES_TYPE):
                    return "A pessoa não confirmou esse valor. Pergunte qual é o valor certo."
            locator.fill(value)
            step |= {"action": StepAction.FILL.value, "value": value}
            text = decision.descricao or f'Digitar "{value}" em "{name}"'
        elif decision.acao == "escolher":
            if not value:
                return "erro: falta a opção a escolher."
            locator.select_option(label=value)
            step |= {"action": StepAction.SELECT.value, "value": value}
            text = decision.descricao or f'Escolher "{value}" em "{name}"'
        elif decision.acao == "marcar":
            locator.check()
            step["action"] = StepAction.CHECK.value
            text = decision.descricao or f'Marcar "{name}"'
        else:
            key = value if value in _ALLOWED_KEYS else "Enter"
            locator.press(key)
            step |= {"action": StepAction.PRESS.value, "value": key}
            text = decision.descricao or f'Apertar {key} em "{name}"'

        self._settle(page)
        return self._add_step(step, text) or "ok: feito"

    def _spreadsheet_frame(self, page: Page) -> Any:
        for frame in page.frames:
            try:
                if frame.locator(_NAME_BOX["css"]).count() == 1:
                    return frame
            except PlaywrightError:
                continue
        return None

    def _write_cells(self, page: Page, decision: ExplorerDecision) -> str:
        """Cada célula vira os dois passos que a extensão grava: ir até ela pela Caixa de Nome e
        escrever o valor na Barra de fórmulas. É o único jeito que o Excel Online aceita."""
        cells = decision.celulas
        if not cells:
            return "erro: falta a lista de células."
        frame = self._spreadsheet_frame(page)
        if frame is None:
            return "erro: não achei a Caixa de Nome do Excel nesta tela. Espere a planilha abrir."
        room = (200 - len(self.draft.steps or [])) // 2
        if room < len(cells):
            return f"erro: só cabem mais {max(room, 0)} células nesta tarefa."

        if not all(self._mentioned(cell.valor) for cell in cells if cell.valor):
            preview = ", ".join(f'{cell.celula} "{cell.valor}"' for cell in cells[:_PREVIEW_CELLS])
            rest = len(cells) - _PREVIEW_CELLS
            more = f" e mais {rest}" if rest > 0 else ""
            answer = self._ask(
                f"Vou escrever {len(cells)} células na planilha: {preview}{more}. Pode?",
                [YES_CELLS, NO_CELLS],
            )
            if not _same(answer, YES_CELLS):
                return "A pessoa não aprovou essas células. Pergunte o que ela quer na planilha."
            # Aprovado uma vez: escrever de novo os mesmos valores não pergunta outra vez
            approved = "; ".join(cell.valor for cell in cells)
            self.answers.append({"pergunta": "Células aprovadas", "resposta": approved})

        name_box = frame.locator(_NAME_BOX["css"])
        formula_bar = frame.locator(_FORMULA_BAR["css"])
        for cell in cells:
            self._check_open()
            name_box.fill(cell.celula)
            name_box.press("Enter")
            formula_bar.click()
            page.keyboard.press("ControlOrMeta+A")
            page.keyboard.press("Delete")
            page.keyboard.type(cell.valor, delay=_TYPING_DELAY_MS)
            page.keyboard.press("Enter")
            base = {
                "action": StepAction.FILL.value,
                "url": page.url,
                "spreadsheet_cell": cell.celula,
            }
            # O Enter no fim do valor é o que a repetição aperta depois de escrever
            address = {
                **base,
                "spreadsheet_part": "address",
                "target": _NAME_BOX,
                "value": cell.celula + "\n",
            }
            value = {
                **base,
                "spreadsheet_part": "value",
                "target": _FORMULA_BAR,
                "value": cell.valor + "\n",
            }
            error = self._add_step(address, f"Ir para a célula {cell.celula}") or self._add_step(
                value, f'{cell.celula}: escrever "{cell.valor}"'
            )
            if error:
                return error
        self._settle(page)
        return f"ok: {len(cells)} células escritas."

    def _finish(self, suggested_name: str | None) -> None:
        steps = self.draft.steps or []
        if not any(step.get("action") != StepAction.NAVIGATE.value for step in steps):
            raise _Failed(
                "A IA terminou sem fazer nenhum passo. Descreva o pedido com mais detalhes."
            )
        name = (self.draft.name or suggested_name or "Tarefa criada com IA").strip()[:160]
        try:
            recording = RecordingCreate(
                name=name,
                start_url=self.draft.start_url,
                allowed_hosts=self.allowed,
                steps=steps,
            )
        except ValidationError as error:
            logger.warning("Rascunho %s não virou gravação: %s", self.draft.id, error.error_count())
            raise _Failed(
                "Os passos anotados não formaram uma tarefa válida. Tente de novo."
            ) from error

        self._check_open()
        flow = FlowService(self.session).create_from_recording(self.draft.owner_id, recording)
        self._save(
            status=AiDraftStatus.DONE,
            flow_id=flow.id,
            name=name,
            question=None,
            events=self._event_entry("info", "Pronto. A tarefa foi para a revisão."),
        )

    def _apply(
        self,
        page: Page,
        decision: ExplorerDecision,
        elements: list[PageElement],
        data: list[ScreenData],
    ) -> object:
        if decision.acao == "concluir":
            self._finish(decision.nome_da_tarefa)
            return _DONE
        if decision.acao == "desistir":
            raise _Failed(f"A IA parou: {decision.motivo or 'não encontrou como seguir.'}")
        if decision.acao == "perguntar":
            question = decision.pergunta or "Como devo seguir?"
            answer = self._ask(question, decision.opcoes)
            return f"A pessoa respondeu: {answer}"
        if decision.acao in {"capturar_tabela", "capturar_valor"}:
            return self._capture(page, decision, data)
        if decision.acao == "abrir_endereco":
            return self._open_address(page, decision)
        if decision.acao == "escrever_celulas":
            try:
                return self._write_cells(page, decision)
            except PlaywrightError as error:
                return f"erro: a planilha não aceitou ({type(error).__name__}). Tente de novo."
        try:
            return self._act_on_element(page, decision, elements)
        except PlaywrightError as error:
            return f"erro: a ação falhou ({type(error).__name__}). Tente outro elemento."

    # ---------- obstáculos ----------

    def _handle_blocked(self, page: Page) -> str | None:
        if not self.blocked:
            return None
        url = self.blocked[-1]
        self.blocked.clear()
        host = _host_of(url)
        if not host or host_matches(host, self.allowed):
            return None
        answer = self._ask(
            f"O site tentou abrir {host}, que não estava no endereço inicial. Posso liberar?",
            [YES_HOST, NO_HOST],
        )
        if not _same(answer, YES_HOST):
            return f"A navegação para {host} foi bloqueada. Siga sem ela."
        self._allow(host)
        page.goto(url, wait_until="domcontentloaded")
        self._settle(page)
        return f"ok: {host} liberado e aberto."

    def _handle_obstacles(self, page: Page) -> str | None:
        if has_captcha(page):
            answer = self._ask(
                "Apareceu um desafio de segurança (CAPTCHA). Resolva na aba do Ditto e clique em "
                f"{SOLVED}.",
                [SOLVED, STOP],
            )
            if _same(answer, STOP):
                self._stop_by_person()
            self._settle(page)
            return "A pessoa resolveu o desafio."

        address = page.url.split("?", 1)[0]
        if has_login_form(page) and address not in self.login_checked:
            self.login_checked.add(address)
            answer = self._ask(
                "Esta página pede login. A IA não digita senhas: entre na sua conta na aba do "
                f"Ditto e clique em {LOGGED_IN}.",
                [LOGGED_IN, NO_LOGIN, STOP],
            )
            if _same(answer, STOP):
                self._stop_by_person()
            self._settle(page)
            return "A pessoa entrou na conta." if _same(answer, LOGGED_IN) else None
        return None

    # ---------- laço ----------

    def _decide(self, page: Page, last_result: str, steps_left: int) -> tuple:
        elements: list[PageElement] = []
        options: dict[int, list[str]] = {}
        frame_options: dict[Any, dict[int, list[str]]] = {}
        self.locators = {}
        for element, frame, local in take_snapshot_with_frames(page):
            if frame not in frame_options:
                frame_options[frame] = select_options(frame)
            if local in frame_options[frame]:
                options[element.index] = frame_options[frame][local]
            self.locators[element.index] = frame_locator_for(frame, local)
            elements.append(element)
        data = collect_screen_data(page)
        payload = sanitizer.build_explorer_payload(
            prompt=self.draft.prompt,
            url=page.url,
            title=page.title(),
            done=self.done,
            last_result=last_result,
            answers=self.answers,
            captured=sorted(self._capture_names()),
            steps_left=steps_left,
            elements=elements,
            options=options,
            screen_data=data,
        )
        return self.llm.decide(payload), elements, data

    def _loop(self, tabs: ItemTabs) -> None:
        last_result = "A página inicial acabou de abrir."
        failures = 0
        for steps_left in range(settings.ai_draft_max_steps, 0, -1):
            self._check_open()
            page = tabs.current
            self._settle(page)
            last_result = self._handle_blocked(page) or self._handle_obstacles(page) or last_result

            decision, elements, data = self._decide(page, last_result, steps_left)
            if decision is None:
                failures += 1
                if failures >= _MAX_LLM_FAILURES:
                    raise _Failed(
                        "A IA não respondeu. Confira LLM_API_KEY e LLM_MODEL no .env e tente de novo."
                    )
                last_result = "erro: sua resposta anterior veio fora do formato JSON combinado."
                continue
            failures = 0
            result = self._apply(page, decision, elements, data)
            if result is _DONE:
                return
            last_result = str(result)

        answer = self._ask(
            f"A IA chegou ao limite de {settings.ai_draft_max_steps} passos. Salvo o que foi "
            "feito até aqui para você revisar?",
            [SAVE_PARTIAL, STOP],
        )
        if _same(answer, SAVE_PARTIAL):
            self._finish(None)
        else:
            self._stop_by_person()

    def run(self) -> None:
        tabs: ItemTabs | None = None
        try:
            self._save(
                status=AiDraftStatus.RUNNING,
                events=self._event_entry("info", "Abri uma aba no seu Chrome."),
            )
            tabs = ItemTabs(self.browser, self.allowed, on_blocked=self.blocked.append)
            page = tabs.current
            page.goto(self.draft.start_url, wait_until="domcontentloaded")
            self._settle(page)
            host = _host_of(self.draft.start_url)
            error = self._add_step(
                {"action": StepAction.NAVIGATE.value, "url": self.draft.start_url}, f"Abrir {host}"
            )
            if error:
                raise _Failed("O endereço inicial não pôde ser aberto.")
            self._loop(tabs)
        except _Canceled:
            logger.info("Rascunho %s cancelado.", self.draft.id)
        except _Failed as failure:
            self._fail(str(failure))
        except PlaywrightError:
            logger.warning("Rascunho %s: o navegador parou.", self.draft.id, exc_info=True)
            self._fail("A aba do Ditto foi fechada ou o Chrome parou de responder.")
        finally:
            if tabs is not None:
                tabs.close()

    def _fail(self, message: str) -> None:
        try:
            self._save(
                status=AiDraftStatus.FAILED,
                error=message[:400],
                question=None,
                events=self._event_entry("error", message),
            )
        except _Canceled:
            pass


def claim_next_draft(session: Session, owner_id: uuid.UUID) -> AiDraft | None:
    draft = AiDraftRepository(session).claim_queued(owner_id)
    if draft is None:
        session.rollback()
        return None
    draft.status = AiDraftStatus.RUNNING
    draft.heartbeat_at = datetime.now(UTC)
    session.commit()
    return draft
