"""Executa um passo subindo a escada de reparo, da opção mais barata para a mais cara."""

import functools
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
# Uma leitura aberta há mais que isso é o site "escutando" (Google Agenda, Gmail, chats), e não a
# resposta à ação: esperar por ela fazia cada passo gastar o tempo máximo
_BACKGROUND_READ_SECONDS = 1.0
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


# Alvo de um passo de teclado que age onde o cursor está, sem procurar elemento
FOCUSED_TARGET: dict[str, Any] = {"focused": True}
_KEYBOARD_ACTIONS = {StepAction.FILL, StepAction.PRESS}
_KEYS_IN_TEXT = {"\t": "Tab", "\n": "Enter"}
# Só a descrição dos elementos (tipo, id, função, tamanho), nunca o que está escrito neles
_FOCUS_REPORT = """() => {
  const describe = (el) => {
    if (!el) return null
    const box = el.getBoundingClientRect()
    return {
      tag: el.tagName, id: el.id || null, role: el.getAttribute('role'),
      label: el.getAttribute('aria-label'), classes: String(el.className || '').slice(0, 120),
      tabindex: el.getAttribute('tabindex'), editable: el.isContentEditable,
      width: Math.round(box.width), height: Math.round(box.height),
    }
  }
  let active = document.activeElement
  while (active && active.shadowRoot && active.shadowRoot.activeElement) {
    active = active.shadowRoot.activeElement
  }
  // Primeiro o que dá para editar; os botões da página vêm só depois
  const pick = (selector, limit) => [...document.querySelectorAll(selector)].slice(0, limit)
  const editables = [...new Set([
    ...pick('textarea, [contenteditable], [role=textbox], [role=grid], [role=gridcell]', 60),
    ...pick('input', 40),
    ...pick('[tabindex]:not(button):not([role=button]):not([role=tab]):not([role=menuitem])', 40),
  ])].map(describe)
  return {
    visibility: document.visibilityState, hasFocus: document.hasFocus(),
    active: describe(active), editables,
  }
}"""

# Onde o cursor está, somando os iframes: "control" (botão, link, menu: uma tecla clicaria
# nele), "ok" (algum elemento que recebe teclas) ou "nowhere" (solto na página)
_FOCUS_STATE = """() => {
  if (!document.hasFocus()) return 'unfocused'
  let el = document.activeElement
  while (el && el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement
  if (!el || el === document.body || el === document.documentElement) return 'nowhere'
  if (el.tagName === 'IFRAME') return 'iframe'
  const control = el.closest(
    'button, a[href], select, summary, [role=button], [role=link], [role=menuitem], ' +
    '[role=menuitemcheckbox], [role=menuitemradio], [role=tab], [role=option], ' +
    '[role=checkbox], [role=radio], [role=switch]'
  )
  return control ? 'control' : 'ok'
}"""
# O site pode levar o cursor para a grade um instante depois do passo anterior
_FOCUS_WAIT_SECONDS = 3.0


def is_focused_target(targets: list[dict[str, Any]]) -> bool:
    return bool(targets) and targets[0].get("focused") is True


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
    # Para investigar a falha: onde estava o cursor e o que dava para editar. Nunca valores
    diagnostics: dict[str, Any] | None = None


# Fases cronometradas de cada passo, para achar onde a execução perde tempo (log do worker)
PHASES = ("locate", "act", "settle", "check")


def _timed(phase: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorate(method: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(method)
        def wrapper(self: "StepRunner", *args: Any, **kwargs: Any) -> Any:
            with self.timing(phase):
                return method(self, *args, **kwargs)

        return wrapper

    return decorate


def _address_of(url: str) -> str:
    """O endereço sem a parte que muda a cada pedido (?rid=..., #...)."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


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
        # Pedidos em andamento e quando começaram: o site ainda pode estar buscando o que vai mostrar
        self._pending_requests: dict[Request, float] = {}
        # Quando começou a última ação. O que o site já fazia antes dela não é resposta a ela
        self._action_started = float("-inf")
        # Endereços que o site já deixou abertos por mais de um segundo: quando ele os abre de
        # novo, é a mesma escuta de fundo, e não a resposta a uma ação
        self._background_reads: set[str] = set()
        self._last_action: StepAction | None = None
        # Segundos gastos em cada fase do passo atual. Só a fase de fora conta: uma espera dentro
        # de um clique entra no clique, sem contar duas vezes
        self.timings: dict[str, float] = {}
        self._phase: str | None = None
        # Escuta a aba e as que ela abrir, nunca o navegador todo: no Chrome da pessoa,
        # as outras abas dela não podem segurar o passo nem virar download
        self._watch(page)

    def _on_request(self, request: Request) -> None:
        if request.resource_type in _TRACKED_REQUESTS:
            self._pending_requests[request] = time.monotonic()

    def _on_request_done(self, request: Request) -> None:
        self._pending_requests.pop(request, None)

    def _mark_action(self) -> None:
        self._action_started = time.monotonic()

    def _waiting_for_site(self) -> bool:
        """O site ainda responde à última ação? Conta o que começou depois dela. Uma leitura que
        passa de um segundo aberta é conexão de fundo; um envio (salvar, enviar) conta até o fim."""
        now = time.monotonic()
        waiting = False
        for request, started in self._pending_requests.items():
            if request.method == "GET":
                address = _address_of(request.url)
                if now - started > _BACKGROUND_READ_SECONDS:
                    self._background_reads.add(address)
                if address in self._background_reads:
                    continue
            if started >= self._action_started:
                waiting = True
        return waiting

    def _watch(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_done)
        page.on("requestfailed", self._on_request_done)
        page.on("download", lambda download: self.downloads.append(download))
        page.on("popup", self._watch)

    @contextmanager
    def timing(self, phase: str) -> Iterator[None]:
        if self._phase is not None:
            yield
            return
        self._phase = phase
        started = time.monotonic()
        try:
            yield
        finally:
            self.timings[phase] = self.timings.get(phase, 0.0) + time.monotonic() - started
            self._phase = None

    def run(self, plan: StepPlan) -> StepOutcome:
        self.timings = {}
        after_capture = self._last_action == StepAction.CAPTURE
        self._last_action = plan.action
        if plan.action == StepAction.NAVIGATE:
            return self._navigate(plan)
        if plan.action == StepAction.CAPTURE:
            return self._capture(plan, after_capture=after_capture)
        if plan.action in _KEYBOARD_ACTIONS and is_focused_target(plan.targets):
            return self._type_into_focus(plan)
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

    def _capture(self, plan: StepPlan, *, after_capture: bool = False) -> StepOutcome:
        """Lê o dado. Sem camadas 2 e 3: um valor parecido com o certo é só um dado errado."""
        optional = bool(plan.postcondition.get("optional"))
        # Um valor antigo na tela é pior do que nenhum: o site precisa ter terminado de responder.
        # Os dados da tela final vêm em sequência, sem ação entre eles: a primeira espera vale para todos.
        if not (optional and after_capture):
            self._settle()
        read = capture.read_table if plan.capture_kind == CaptureKind.TABLE else capture.read_value
        if plan.postcondition.get("type") == postcondition.TEXT_STABLE:
            captured = self._read_when_stable(plan, read)
            if captured is not None:
                return StepOutcome("ok", layer=1, captured=captured)
            return StepOutcome(
                "needs_human",
                help_kind=HelpKind.UNCERTAIN,
                message=f"O texto não parou de mudar a tempo para ser lido: {plan.intent}.",
            )
        # Dado guardado sozinho da tela final: a página já terminou de responder, e esperar
        # por cada um que não veio desta vez deixaria a linha minutos parada
        deadline = time.monotonic() + (0 if optional else settings.element_wait_ms / 1000)
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
        if optional:
            # Um par "rótulo: valor" que só aparece em alguns casos: fica vazio e a tarefa segue
            empty: str | list[dict[str, str]] = [] if plan.capture_kind == CaptureKind.TABLE else ""
            return StepOutcome("ok", layer=1, captured=empty)
        return StepOutcome(
            "needs_human",
            help_kind=HelpKind.UNCERTAIN,
            message=f"Não encontrei o dado desta captura na página: {plan.intent}.",
        )

    def _read_when_stable(self, plan: StepPlan, read: Callable[[Page, dict[str, Any]], Any]) -> Any:
        """Lê só quando o texto fica igual por alguns segundos e o site não mostra mais que está
        trabalhando (por exemplo, o botão de parar a resposta de um chat)."""
        rule = plan.postcondition
        quiet = min(float(rule.get("quiet_seconds", 3)), 60)
        deadline = time.monotonic() + min(float(rule.get("timeout_seconds", 120)), 600)
        busy = rule.get("busy_css")
        last: Any = None
        since = time.monotonic()
        while time.monotonic() < deadline:
            value = next(
                (
                    found
                    for target in plan.targets
                    if (found := read(self.page, target)) is not None
                ),
                None,
            )
            now = time.monotonic()
            if value != last:
                last, since = value, now
            elif value and now - since >= quiet and not self._is_busy(busy):
                return value
            self.page.wait_for_timeout(_POLL_MS * 2)
        return None

    def _is_busy(self, css: str | None) -> bool:
        if not css:
            return False
        try:
            return self.page.locator(css).first.is_visible()
        except PlaywrightError:
            return False

    def _navigate(self, plan: StepPlan) -> StepOutcome:
        host = (urlsplit(plan.url or "").hostname or "").lower()
        if not host_matches(host, plan.allowed_domains):
            return StepOutcome(
                "failed",
                message="Este endereço não está entre os domínios permitidos desta tarefa.",
            )

        before = self._state_before(plan)
        try:
            self._mark_action()
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

    @_timed("locate")
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
            self._mark_action()
            element.click()
            self._settle()
            return True
        except PlaywrightError:
            return False

    @_timed("settle")
    def _settle(self) -> None:
        """A pós-condição é quem decide se o passo deu certo: aqui só se decide quanto esperar."""
        postcondition.wait_until_quiet(
            self.page,
            busy=self._waiting_for_site,
            quiet_seconds=_QUIET_SECONDS,
            max_seconds=_SETTLE_MAX_SECONDS,
        )

    @_timed("act")
    def _act(self, element: Locator, plan: StepPlan) -> None:
        self._mark_action()
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
        kind = element.evaluate("el => el.isContentEditable ? 'editor' : el.tagName")
        # Tab e Enter no texto viram as teclas: "B1 + Enter" na Caixa de Nome do Excel, por
        # exemplo. Numa caixa de texto grande (textarea), a quebra de linha continua sendo texto
        first, *rest = re.split(r"([\t\n])", value) if kind != "TEXTAREA" else [value]
        if kind != "editor":
            element.fill(first)
        else:
            # Editores de texto só entendem teclas: é assim que criam cada linha
            element.click()
            self.page.keyboard.press("ControlOrMeta+A")
            self.page.keyboard.press("Delete")
            self.page.keyboard.type(first, delay=_TYPING_DELAY_MS)
        for piece in rest:
            if piece in _KEYS_IN_TEXT:
                self.page.keyboard.press(_KEYS_IN_TEXT[piece])
            elif piece:
                self.page.keyboard.type(piece, delay=_TYPING_DELAY_MS)

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

    def _type_into_focus(self, plan: StepPlan) -> StepOutcome:
        """Digita onde o cursor já está. Planilhas como o Excel Online desenham a grade como
        imagem e recebem as teclas num editor escondido: não há campo para mirar."""
        self._bring_to_front_if_hidden()
        self._settle()
        if plan.irreversible:
            self.before_irreversible()
        if plan.action == StepAction.FILL:
            # Tab e quebra de linha no texto viram as teclas: numa planilha, andam de célula
            pieces = [
                (_KEYS_IN_TEXT.get(piece), piece)
                for piece in re.split(r"([\t\n])", plan.value or "")
                if piece
            ]
        else:
            pieces = [(plan.value or "Enter", "")]
        for key, text in pieces:
            # Cada Tab pode levar o cursor para fora da grade: confere antes de cada tecla
            state = self._wait_for_focus()
            if state != "ok":
                message = (
                    "O cursor estava num botão, e não onde digitar. A linha parou para não "
                    f"clicar em nada sem querer: {plan.intent}."
                    if state == "control"
                    else "O cursor não estava em nenhum lugar onde digitar, e o texto se "
                    f"perderia. A linha parou: {plan.intent}."
                )
                return StepOutcome("failed", message=message, diagnostics=self._focus_report())
            self._mark_action()
            if key:
                self.page.keyboard.press(key)
            else:
                self.page.keyboard.type(text, delay=_TYPING_DELAY_MS)
        self._settle()
        return StepOutcome("ok", layer=1)

    def _bring_to_front_if_hidden(self) -> None:
        """Numa aba escondida o Chrome pausa o desenho da página, e o Excel só leva o cursor
        para a grade quando desenha. A aba do Ditto vem para a frente antes de digitar."""
        try:
            if self.page.evaluate("document.visibilityState") != "visible":
                self.page.bring_to_front()
                self.page.wait_for_timeout(_POLL_MS * 5)
        except PlaywrightError:
            pass

    def _focus_state(self) -> str:
        states = set()
        for frame in self.page.frames:
            try:
                states.add(frame.evaluate(_FOCUS_STATE))
            except PlaywrightError:
                continue
        if "control" in states:
            return "control"
        return "ok" if "ok" in states else "nowhere"

    def _wait_for_focus(self) -> str:
        deadline = time.monotonic() + _FOCUS_WAIT_SECONDS
        state = self._focus_state()
        while state == "nowhere" and time.monotonic() < deadline:
            self.page.wait_for_timeout(_POLL_MS)
            state = self._focus_state()
        return state

    def _focus_report(self) -> dict[str, Any]:
        frames = []
        for frame in self.page.frames:
            try:
                frames.append({"url": frame.url[:200], **frame.evaluate(_FOCUS_REPORT)})
            except PlaywrightError:
                frames.append({"url": frame.url[:200], "erro": "não deu para ler"})
        return {"frames": frames}

    def _state_before(self, plan: StepPlan) -> postcondition.PageState:
        """A foto da página antes do passo só serve à regra "a página mudou": tirar nas outras
        custaria uma ida e volta ao Chrome por quadro, à toa."""
        if plan.postcondition.get("type") != postcondition.PAGE_CHANGED:
            return postcondition.PageState("")
        with self.timing("check"):
            return postcondition.capture_state(self.page)

    def _perform(self, element: Locator, plan: StepPlan) -> tuple[bool, Download | None]:
        before = self._state_before(plan)
        if plan.irreversible:
            self.before_irreversible()
        try:
            kind = plan.postcondition.get("type")
            if kind == postcondition.DOWNLOAD:
                return self._perform_download(element, plan)

            # Só a regra "o campo ficou com o valor" confere o próprio elemento preenchido
            filled = element.element_handle() if kind == postcondition.FIELD_VALUE else None
            self._act(element, plan)
            self._settle()
            with self.timing("check"):
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
