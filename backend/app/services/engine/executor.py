"""Executa um passo subindo a escada de reparo, da opção mais barata para a mais cara."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Download, Locator, Page, Request
from playwright.sync_api import Error as PlaywrightError

from app.core.config import settings
from app.models.enums import CaptureKind, HelpKind, StepAction
from app.services.engine import capture, matcher, postcondition
from app.services.engine import locator as layer_one
from app.services.engine.browser import host_matches
from app.services.engine.llm_repair import LlmRepairer
from app.services.engine.safety import looks_irreversible
from app.services.engine.snapshot import (
    PageElement,
    has_captcha,
    has_login_form,
    locator_for,
    take_snapshot,
)
from app.services.llm_client import LlmUnavailableError
from app.services.sanitizer import SecretLeakError

MAX_LLM_ROUNDS = 3
MAX_OPTIONS = 3
_LOAD_WAIT_MS = 3000
_POLL_MS = 150
_PRELUDE_WAIT_MS = 1000
_SELECT_BY_VALUE_WAIT_MS = 500
_TYPING_DELAY_MS = 10
_QUIET_SECONDS = 0.5
_SETTLE_MAX_SECONDS = 4
_TRACKED_REQUESTS = {"document", "xhr", "fetch"}
_LOGIN_MESSAGE = (
    "O site pediu login, e esta gravação não tem esse passo. A repetição começa sem a sua sessão: "
    "saia da conta no navegador e grave a tarefa de novo, começando pelo login."
)


class _ValueNotAvailableError(Exception):
    """O campo foi encontrado, mas o valor desta linha não existe nele: é dado errado, não layout novo."""


@dataclass
class StepPlan:
    """O passo já com os valores da linha. O motor não conhece banco nem planilha."""

    position: int
    action: StepAction
    intent: str
    postcondition: dict[str, Any]
    value: str | None
    url: str | None
    irreversible: bool
    # Da versão atual para as mais antigas
    targets: list[dict[str, Any]]
    allowed_domains: list[str]
    secrets: list[str] = field(default_factory=list)
    capture_kind: CaptureKind | None = None
    # A tarefa tem um login gravado: um formulário de senha na tela é esperado
    has_recorded_login: bool = False


@dataclass
class StepOutcome:
    status: str  # "ok", "needs_human" ou "failed"
    layer: int | None = None
    new_target: dict[str, Any] | None = None
    target_index: int | None = None
    score: float | None = None
    explanation: str = ""
    help_kind: HelpKind | None = None
    message: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    download: Download | None = None
    captured: str | list[dict[str, str]] | None = None


class StepRunner:
    def __init__(
        self,
        page: Page,
        *,
        repairer: LlmRepairer | None = None,
        consume_llm_call: Callable[[], bool] = lambda: False,
        before_irreversible: Callable[[], None] = lambda: None,
    ) -> None:
        self.page = page
        self.repairer = repairer or LlmRepairer()
        self.consume_llm_call = consume_llm_call
        # Chamado antes de tocar em um passo sem volta, para a marca sobreviver a uma queda do worker
        self.before_irreversible = before_irreversible
        # Um download pode começar em uma janela nova, aberta pelo próprio clique
        self.downloads: list[Download] = []
        # Pedidos em andamento: o site ainda pode estar buscando o que vai mostrar
        self._pending_requests: set[Request] = set()
        page.context.on("request", self._on_request)
        page.context.on("requestfinished", self._on_request_done)
        page.context.on("requestfailed", self._on_request_done)
        for open_page in page.context.pages:
            self._watch_downloads(open_page)
        page.context.on("page", self._watch_downloads)

    def _on_request(self, request: Request) -> None:
        if request.resource_type in _TRACKED_REQUESTS:
            self._pending_requests.add(request)

    def _on_request_done(self, request: Request) -> None:
        self._pending_requests.discard(request)

    def _watch_downloads(self, page: Page) -> None:
        page.on("download", lambda download: self.downloads.append(download))

    def run(self, plan: StepPlan) -> StepOutcome:
        if plan.action == StepAction.NAVIGATE:
            return self._navigate(plan)
        if plan.action == StepAction.CAPTURE:
            return self._capture(plan)
        try:
            return self._climb_repair_ladder(plan)
        except _ValueNotAvailableError:
            return StepOutcome(
                "failed",
                message=f"O valor desta linha não está entre as opções deste passo: {plan.intent}.",
            )

    def _climb_repair_ladder(self, plan: StepPlan) -> StepOutcome:
        outcome = self._layer_one(plan)
        if outcome is not None:
            return outcome

        if has_captcha(self.page):
            return StepOutcome(
                "needs_human",
                help_kind=HelpKind.CAPTCHA,
                message="O portal pediu um CAPTCHA, e o Ditto não tenta contornar.",
            )

        # Sem como verificar o resultado, um reparo poderia ser salvo errado
        if plan.postcondition.get("type", postcondition.NONE) not in postcondition.VERIFIABLE_TYPES:
            return self._ask_human(plan, [])

        candidates = matcher.rank(plan.targets[0], plan.action, take_snapshot(self.page))

        # Clicar no botão errado em "Pagar" não tem conserto: sem tentativas por conta própria
        if plan.irreversible:
            return self._ask_human(plan, candidates)

        outcome = self._layer_two(plan, candidates)
        if outcome is not None:
            return outcome

        outcome = self._layer_three(plan)
        if outcome is not None:
            return outcome

        return self._ask_human(plan, candidates)

    def _capture(self, plan: StepPlan) -> StepOutcome:
        """Lê o dado. Sem camadas 2 e 3: um valor parecido com o certo é só um dado errado."""
        # Um valor antigo na tela é pior do que nenhum: o site precisa ter terminado de responder
        self._settle()
        read = capture.read_table if plan.capture_kind == CaptureKind.TABLE else capture.read_value
        deadline = time.monotonic() + settings.element_wait_ms / 1000
        while True:
            for target in plan.targets:
                captured = read(self.page, target)
                if captured is not None:
                    return StepOutcome("ok", layer=1, captured=captured)
            if time.monotonic() >= deadline:
                break
            self.page.wait_for_timeout(_POLL_MS)

        if has_captcha(self.page):
            return StepOutcome(
                "needs_human",
                help_kind=HelpKind.CAPTCHA,
                message="O portal pediu um CAPTCHA, e o Ditto não tenta contornar.",
            )
        if self._blocked_by_login(plan):
            return StepOutcome("needs_human", help_kind=HelpKind.UNCERTAIN, message=_LOGIN_MESSAGE)
        return StepOutcome(
            "needs_human",
            help_kind=HelpKind.UNCERTAIN,
            message=f"Não encontrei o dado desta captura na página: {plan.intent}.",
        )

    def _navigate(self, plan: StepPlan) -> StepOutcome:
        host = (urlsplit(plan.url or "").hostname or "").lower()
        if not host_matches(host, plan.allowed_domains):
            return StepOutcome(
                "failed",
                message="Este endereço não está entre os domínios permitidos desta tarefa.",
            )

        before = postcondition.capture_state(self.page)
        try:
            self.page.goto(plan.url, wait_until="domcontentloaded")
        except PlaywrightError:
            return StepOutcome("failed", message="O portal não abriu ou o endereço foi bloqueado.")
        self._settle()

        # Um redirecionamento pode ter levado para fora dos domínios da tarefa
        final_host = (urlsplit(self.page.url).hostname or "").lower()
        if not host_matches(final_host, plan.allowed_domains):
            return StepOutcome(
                "failed", message="O portal redirecionou para um domínio não permitido."
            )

        passed = postcondition.check(
            self.page,
            plan.postcondition,
            action=plan.action,
            locator=None,
            value=plan.value,
            before=before,
        )
        if passed:
            return StepOutcome("ok", layer=1)
        return StepOutcome("failed", message="A página abriu, mas não ficou como o esperado.")

    def _layer_one(self, plan: StepPlan) -> StepOutcome | None:
        """Espera o elemento aparecer antes de concluir que o site mudou: página lenta não é reparo."""
        tried: set[int] = set()
        deadline = time.monotonic() + settings.element_wait_ms / 1000
        first_pass = True

        while True:
            for index, target in enumerate(plan.targets):
                # Caminhos com menu abrem coisas na tela: só tentam uma vez
                if index in tried or (target.get("prelude") and not first_pass):
                    continue
                element = self._locate_with_prelude(target)
                if element is None:
                    continue

                tried.add(index)
                passed, download = self._perform(element, plan)
                if passed:
                    return StepOutcome("ok", layer=1, target_index=index, download=download)

                # Já tocou no botão: não pode tentar de novo em um passo sem volta
                if plan.irreversible:
                    return StepOutcome(
                        "failed",
                        message=f"Um passo sem volta foi acionado, mas não deu o resultado esperado: {plan.intent}. Confira no portal.",
                    )

            first_pass = False
            if len(tried) == len(plan.targets) or time.monotonic() >= deadline:
                return None
            self.page.wait_for_timeout(_POLL_MS)

    def _layer_two(self, plan: StepPlan, candidates: list[matcher.Candidate]) -> StepOutcome | None:
        confident = matcher.is_confident(
            candidates, settings.similarity_threshold, settings.similarity_margin
        )
        if not confident:
            return None

        best = candidates[0]
        passed, download = self._perform(locator_for(self.page, best.element), plan)
        if not passed:
            return None

        return StepOutcome(
            "ok",
            layer=2,
            new_target=best.element.to_target(),
            score=best.score,
            explanation=f'Encontrei "{best.element.text or best.element.label}", {best.score:.0%} parecido com o gravado.',
            download=download,
        )

    def _layer_three(self, plan: StepPlan) -> StepOutcome | None:
        prelude: list[dict[str, Any]] = []

        for _ in range(MAX_LLM_ROUNDS):
            if not self.consume_llm_call():
                return None

            elements = take_snapshot(self.page)
            try:
                decision = self.repairer.decide(
                    intent=plan.intent,
                    action=plan.action.value,
                    target=plan.targets[0],
                    elements=elements,
                    secrets=plan.secrets,
                    already_clicked=[
                        item.get("text") or item.get("label") or "" for item in prelude
                    ],
                )
            except (LlmUnavailableError, SecretLeakError):
                return None

            if decision is None or self._is_unsafe(plan, decision.element):
                return None

            element = locator_for(self.page, decision.element)
            if decision.is_final:
                if not matcher.is_compatible(plan.action, decision.element):
                    return None
                passed, download = self._perform(element, plan)
                if not passed:
                    return None
                return StepOutcome(
                    "ok",
                    layer=3,
                    new_target=decision.element.to_target(prelude),
                    explanation=decision.explanation,
                    download=download,
                )

            if not matcher.is_compatible(StepAction.CLICK, decision.element) or not self._click(
                element
            ):
                return None
            prelude.append(decision.element.to_target())

        return None

    def _is_unsafe(self, plan: StepPlan, element: PageElement) -> bool:
        """A IA pode ser enganada pelo texto da página: elemento com cara de sem volta só se o passo já era esse."""
        chosen = f"{element.text} {element.label}"
        recorded = f"{plan.targets[0].get('text', '')} {plan.intent}"
        return looks_irreversible(chosen) and not looks_irreversible(recorded)

    def _blocked_by_login(self, plan: StepPlan) -> bool:
        return not plan.has_recorded_login and has_login_form(self.page)

    def _ask_human(self, plan: StepPlan, candidates: list[matcher.Candidate]) -> StepOutcome:
        if self._blocked_by_login(plan):
            return StepOutcome("needs_human", help_kind=HelpKind.UNCERTAIN, message=_LOGIN_MESSAGE)
        options = [
            {
                "id": str(candidate.element.index),
                "text": candidate.element.text
                or candidate.element.label
                or candidate.element.placeholder,
                "score": round(candidate.score, 2),
                "target": candidate.element.to_target(),
            }
            for candidate in candidates[:MAX_OPTIONS]
            if candidate.score >= settings.candidate_floor
            and (candidate.element.text or candidate.element.label or candidate.element.placeholder)
        ]
        if options:
            return StepOutcome(
                "needs_human",
                help_kind=HelpKind.CHOOSE,
                options=options,
                message="Achei opções parecidas e não tenho certeza. O que você escolher vira o novo caminho.",
            )
        return StepOutcome(
            "needs_human",
            help_kind=HelpKind.UNCERTAIN,
            message=f"Não encontrei como fazer este passo nesta página: {plan.intent}.",
        )

    def _locate_with_prelude(self, target: dict[str, Any]) -> Locator | None:
        for step_before in target.get("prelude", []):
            element = layer_one.locate(self.page, step_before)
            if element is None or not self._click(element):
                return None
        element = layer_one.locate(self.page, target)
        # Um menu que acabou de abrir pode levar um instante para mostrar a opção
        if element is None and target.get("prelude"):
            self.page.wait_for_timeout(_PRELUDE_WAIT_MS)
            element = layer_one.locate(self.page, target)
        return element

    def _click(self, element: Locator) -> bool:
        try:
            element.click()
            self._settle()
            return True
        except PlaywrightError:
            return False

    def _settle(self) -> None:
        """Espera a página parar de mudar. Um site com animação sem fim só custa o tempo máximo."""
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=_LOAD_WAIT_MS)
            deadline = time.monotonic() + _SETTLE_MAX_SECONDS
            state = postcondition.capture_state(self.page).fingerprint
            quiet_since = time.monotonic()
            while time.monotonic() < deadline:
                self.page.wait_for_timeout(_POLL_MS)
                current = postcondition.capture_state(self.page).fingerprint
                if current != state or self._pending_requests:
                    state = current
                    quiet_since = time.monotonic()
                elif time.monotonic() - quiet_since >= _QUIET_SECONDS:
                    return
        except PlaywrightError:
            pass  # a pós-condição é quem decide se o passo deu certo

    def _act(self, element: Locator, plan: StepPlan) -> None:
        if plan.action == StepAction.CLICK:
            element.click()
        elif plan.action == StepAction.FILL:
            self._fill(element, plan.value or "")
        elif plan.action == StepAction.SELECT:
            self._select(element, plan.value or "")
        elif plan.action == StepAction.CHECK:
            element.check()
        elif plan.action == StepAction.PRESS:
            element.press(plan.value or "Enter")

    def _fill(self, element: Locator, value: str) -> None:
        if not element.evaluate("el => el.isContentEditable"):
            element.fill(value)
            return
        # Editores de texto só entendem teclas: é assim que criam cada linha
        element.click()
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.press("Delete")
        self.page.keyboard.type(value, delay=_TYPING_DELAY_MS)

    def _select(self, element: Locator, value: str) -> None:
        try:
            element.select_option(label=value, timeout=_LOAD_WAIT_MS)
            return
        except PlaywrightError:
            pass
        try:
            element.select_option(value=value, timeout=_SELECT_BY_VALUE_WAIT_MS)
        except PlaywrightError as error:
            raise _ValueNotAvailableError from error

    def _perform(self, element: Locator, plan: StepPlan) -> tuple[bool, Download | None]:
        before = postcondition.capture_state(self.page)
        if plan.irreversible:
            self.before_irreversible()
        try:
            if plan.postcondition.get("type") == postcondition.DOWNLOAD:
                return self._perform_download(element, plan)

            filled = element.element_handle()
            self._act(element, plan)
            self._settle()
            passed = postcondition.check(
                self.page,
                plan.postcondition,
                action=plan.action,
                locator=element,
                value=plan.value,
                before=before,
                filled=filled,
            )
            return passed, None
        except PlaywrightError:
            return False, None

    def _perform_download(self, element: Locator, plan: StepPlan) -> tuple[bool, Download | None]:
        self.downloads.clear()
        self._act(element, plan)

        deadline = time.monotonic() + settings.postcondition_timeout_ms / 1000
        while not self.downloads and time.monotonic() < deadline:
            self.page.wait_for_timeout(_POLL_MS)
        if not self.downloads:
            return False, None
        download = self.downloads[0]

        extension = plan.postcondition.get("extension", "").lower().lstrip(".")
        if extension and not download.suggested_filename.lower().endswith(f".{extension}"):
            return False, None
        return True, download
