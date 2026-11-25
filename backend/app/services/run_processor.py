"""Liga o motor ao banco: percorre as linhas, registra tudo e decide quando parar."""

import json
import logging
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page
from playwright.sync_api import Error as PlaywrightError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_json
from app.core.exceptions import BusinessRuleError
from app.models.enums import (
    ArtifactKind,
    EventStatus,
    HelpKind,
    ItemStatus,
    LogLevel,
    RunStatus,
    VersionSource,
)
from app.models.flow import Flow, Step
from app.models.repair import HelpRequest
from app.models.run import Artifact, Run, RunItem, StepEvent
from app.models.user import User
from app.repositories.credential_repository import CredentialRepository
from app.repositories.run_repository import RunRepository
from app.services import run_lifecycle, storage
from app.services.ai_explorer import BrowserUnavailableError
from app.services.email_service import send_email
from app.services.engine.browser import MAX_DOWNLOAD_BYTES, ItemTabs, host_matches
from app.services.engine.executor import StepOutcome, StepPlan, StepRunner
from app.services.engine.llm_repair import LlmRepairer
from app.services.repair_service import save_new_version
from app.services.sanitizer import scrub
from app.services.templating import render, rule_values, safe_relative_path

logger = logging.getLogger(__name__)

_SOURCE_BY_LAYER = {2: VersionSource.SIMILARITY, 3: VersionSource.LLM}
_SCREENS_FOLDER = ".telas"

_BROWSER_LOST = "a ligação com o navegador caiu: execução de volta à fila"
_SHUTTING_DOWN = "o worker está desligando: execução de volta à fila"
# Quedas do navegador dentro deste prazo: a partir daqui a execução para de voltar à fila e
# termina, para não ficar indo e voltando para sempre
_MAX_BROWSER_LOSSES = 3
_BROWSER_LOSS_WINDOW = timedelta(minutes=30)


class _Paused(Exception):
    """A linha parou esperando uma pessoa."""


class _Canceled(Exception):
    """A execução deixou de ser deste worker: a pessoa cancelou, ou ela voltou para a fila."""


class _Released(Exception):
    """A execução voltou para a fila para outro worker continuar (o worker está desligando)."""


class BrowserLostError(BrowserUnavailableError):
    """A ligação com o navegador caiu no meio da execução. Ela já voltou para a fila (ou
    terminou, depois de várias quedas); quem chama abre o navegador de novo."""


class RunProcessor:
    def __init__(
        self,
        session: Session,
        run: Run,
        browser: Browser,
        repairer: LlmRepairer | None = None,
        stop: threading.Event | None = None,
    ) -> None:
        self.session = session
        self.run = run
        self.browser = browser
        self.repairer = repairer
        self.stop = stop
        self.flow: Flow = session.get(Flow, run.flow_id)
        self.owner: User = session.get(User, run.owner_id)
        self.steps: list[Step] = list(self.flow.steps)
        self.total = len(run.items)
        self.credentials = {
            credential.domain: decrypt_json(credential.encrypted_payload)
            for credential in CredentialRepository(session).list_for_domains(
                run.owner_id, self.flow.allowed_domains
            )
        }
        # Usuários e senhas dos portais: nunca chegam à IA nem a uma captura
        self.credential_secrets = [
            secret for credential in self.credentials.values() for secret in credential.values()
        ]

    def process(self) -> None:
        try:
            self._process_items()
            # Ninguém cancelou enquanto a última linha rodava? A trava vale até o commit
            self._lock_running()
        except (_Paused, _Canceled, _Released):
            self.session.commit()
            return

        run_lifecycle.finalize(self.session, self.run)
        self.session.commit()
        self._notify_if_problem()

    def _process_items(self) -> None:
        failures_in_a_row = 0
        for item in self.run.items:
            if item.status not in {ItemStatus.PENDING, ItemStatus.RUNNING}:
                continue
            if self.stop is not None and self.stop.is_set():
                self._release(_SHUTTING_DOWN)
                raise _Released

            self._process_item(item)
            failures_in_a_row = failures_in_a_row + 1 if item.status == ItemStatus.FAILED else 0
            if failures_in_a_row >= settings.circuit_breaker_failures:
                self._trip_circuit_breaker()
                return

    def _trip_circuit_breaker(self) -> None:
        # Várias tentativas erradas seguidas podem bloquear a conta da pessoa no portal
        for item in self.run.items:
            if item.status == ItemStatus.PENDING:
                item.status = ItemStatus.SKIPPED
        run_lifecycle.add_log(
            self.session,
            self.run,
            LogLevel.FAILURE,
            f"{settings.circuit_breaker_failures} falhas seguidas: execução parada para não bloquear a conta no portal",
        )

    def _ensure_still_running(self) -> None:
        """Antes de cada passo: avisa que está vivo e confere se a execução continua sendo
        deste worker. Cancelada, ou devolvida à fila, ela para aqui."""
        RunRepository(self.session).touch_heartbeat(self.run.id, datetime.now(UTC))
        self.session.commit()
        self.session.refresh(self.run, ["status"])
        status = self.run.status
        # Devolve a conexão ao banco: o passo seguinte pode demorar
        self.session.commit()
        if status != RunStatus.RUNNING:
            raise _Canceled

    def _lock_running(self) -> None:
        """Trava a execução antes de gravar um resultado. Se ela foi cancelada nesse meio
        tempo, nada do que esta linha mudou é gravado por cima do cancelamento."""
        if RunRepository(self.session).lock_status(self.run.id) != RunStatus.RUNNING:
            self.session.rollback()
            raise _Canceled

    def _release(self, message: str) -> None:
        """Devolve a execução à fila sem refazer o que já terminou."""
        self._lock_running()
        for item in RunRepository(self.session).items_of(self.run.id):
            requeue_item_after_crash(item)
        self.run.status = RunStatus.QUEUED
        run_lifecycle.add_log(self.session, self.run, LogLevel.INFO, message)
        self.session.commit()

    def _handle_browser_loss(self, error: Exception) -> None:
        logger.warning(
            "A ligação com o navegador caiu na execução %s: %s", self.run.id, type(error).__name__
        )
        since = datetime.now(UTC) - _BROWSER_LOSS_WINDOW
        losses = RunRepository(self.session).count_log_since(self.run.id, _BROWSER_LOST, since)
        if losses + 1 >= _MAX_BROWSER_LOSSES:
            # Já voltou para a fila várias vezes: termina aqui
            self._lock_running()
            for item in RunRepository(self.session).items_of(self.run.id):
                requeue_item_after_crash(item)
            run_lifecycle.skip_open_items(self.session, self.run)
            run_lifecycle.add_log(
                self.session,
                self.run,
                LogLevel.FAILURE,
                "a ligação com o navegador caiu várias vezes seguidas: execução interrompida",
            )
            run_lifecycle.finalize(self.session, self.run)
            self.session.commit()
            self._notify_if_problem()
        else:
            self._release(_BROWSER_LOST)
        raise BrowserLostError from error

    def _process_item(self, item: RunItem) -> None:
        self._ensure_still_running()

        # Repetir uma linha que já tocou em um passo sem volta poderia pagar ou enviar duas vezes
        if item.irreversible_done:
            run_lifecycle.fail_item(
                item, "Esta linha já passou por um passo sem volta. Confira no portal."
            )
            return

        item.status = ItemStatus.RUNNING
        item.error_message = None
        item.output = {}
        self.session.commit()

        started = time.monotonic()
        values = {**rule_values(self.flow.variables, self.run.timezone), **item.input}
        try:
            tabs = ItemTabs(self.browser, self.flow.allowed_domains)
        except PlaywrightError as error:
            # Sem aba não há o que tentar: a ligação com o navegador (ou com a extensão) caiu
            self._handle_browser_loss(error)
        try:
            runner = self._new_runner(tabs.current, item)
            for step in self.steps:
                page = tabs.current
                runner.page = page
                if not self._run_step(page, runner, item, step, values):
                    return
            self._finish_item(item, started)
        except BusinessRuleError as error:
            run_lifecycle.fail_item(item, error.detail)
            self._log_failure(item, error.detail)
        except PlaywrightError as error:
            if not self.browser.is_connected():
                self._handle_browser_loss(error)
            # A mensagem do navegador pode conter valores digitados: só o tipo vai para o log
            logger.warning(
                "Falha do navegador na linha %s: %s", item.position, type(error).__name__
            )
            message = "O navegador não conseguiu concluir esta linha."
            run_lifecycle.fail_item(item, message)
            self._log_failure(item, message)
        finally:
            _close_tabs(tabs)

    def _new_runner(self, page: Page, item: RunItem) -> StepRunner:
        def mark_irreversible() -> None:
            item.irreversible_done = True
            self.session.commit()

        kwargs = {
            "consume_llm_call": self._consume_llm_call,
            "before_irreversible": mark_irreversible,
        }
        if self.repairer is not None:
            kwargs["repairer"] = self.repairer
        return StepRunner(page, **kwargs)

    def _consume_llm_call(self) -> bool:
        available = settings.llm_enabled or self.repairer is not None
        if not available or self.run.llm_calls >= settings.llm_max_calls_per_run:
            return False
        self.run.llm_calls += 1
        self.session.commit()
        return True

    def _run_step(
        self, page: Page, runner: StepRunner, item: RunItem, step: Step, values: dict[str, str]
    ) -> bool:
        """Devolve False quando a linha termina aqui, com falha."""
        self._ensure_still_running()
        self._pause_if_needs_confirmation(item, step)

        started = time.monotonic()
        plan = self._build_plan(page, item, step, values)
        # O passo pode levar minutos: a conexão com o banco não fica presa esperando o navegador
        self.session.commit()
        outcome = runner.run(plan)
        duration = int((time.monotonic() - started) * 1000)
        _log_step_timing(item, step, duration, runner.timings)

        if outcome.status == "ok":
            self._record_success(item, step, outcome, duration, values)
            return True

        if not self.browser.is_connected():
            # O passo não falhou por causa do site: o navegador sumiu no meio dele
            self._handle_browser_loss(RuntimeError("navegador desconectado"))

        # Os detalhes só ficam guardados junto com a tela, para a limpeza apagar os dois juntos
        if self._screenshot(page, item) and outcome.diagnostics:
            self._save_diagnostics(item, outcome.diagnostics)
        item.problem_step_position = step.position

        # Depois de um passo sem volta a linha não pode recomeçar, então não adianta perguntar
        if outcome.status == "needs_human" and not item.irreversible_done:
            self._record_event(item, step, EventStatus.WAITING_HUMAN, None, duration)
            self._open_help(item, step, outcome)
            raise _Paused

        message = outcome.message or f"Este passo não foi concluído: {step.intent}."
        self._record_event(item, step, EventStatus.FAILED, None, duration)
        run_lifecycle.fail_item(item, message)
        self._log_failure(item, message)
        return False

    def _pause_if_needs_confirmation(self, item: RunItem, step: Step) -> None:
        if (
            not step.irreversible
            or step.auto_confirm
            or str(step.id) in self.run.confirmed_step_ids
        ):
            return
        item.problem_step_position = step.position
        outcome = StepOutcome(
            "needs_human",
            help_kind=HelpKind.CONFIRM,
            message=f"O passo {step.position} não tem volta. A resposta vale para todas as linhas desta execução.",
        )
        self._open_help(item, step, outcome)
        raise _Paused

    def _credential_for(self, page: Page) -> dict[str, str]:
        """O acesso salvo para o site em que a página está agora, nunca o de outro site: a
        senha do banco não pode ser digitada na página de login de um terceiro."""
        host = (urlsplit(page.url).hostname or "").lower()
        matches = [
            (domain, credential)
            for domain, credential in self.credentials.items()
            if host_matches(host, [domain])
        ]
        if not matches:
            return {}
        # Com "empresa.com" e "login.empresa.com" salvos, vale o mais específico
        return max(matches, key=lambda match: len(match[0]))[1]

    def _build_plan(
        self, page: Page, item: RunItem, step: Step, values: dict[str, str]
    ) -> StepPlan:
        if step.credential_field:
            value = self._credential_for(page).get(step.credential_field)
            if not value:
                host = urlsplit(page.url).hostname or "este portal"
                raise BusinessRuleError(
                    f"Falta salvar o acesso a {host}. O Ditto só digita uma senha no site "
                    "para o qual ela foi salva."
                )
        else:
            value = render(step.value_template, values) if step.value_template is not None else None

        versions = sorted(
            step.versions, key=lambda version: (version.is_current, version.version), reverse=True
        )
        # Nada disso pode chegar à IA: senhas dos portais e os dados da linha
        secrets = [*self.credential_secrets, *values.values()]

        return StepPlan(
            position=step.position,
            action=step.action,
            intent=step.intent,
            postcondition=step.postcondition,
            value=value,
            url=render(step.url_template, values) if step.url_template else None,
            irreversible=step.irreversible,
            targets=[version.target for version in versions],
            allowed_domains=self.flow.allowed_domains,
            secrets=secrets,
            capture_kind=step.capture_kind,
            has_recorded_login=any(item.credential_field for item in self.flow.steps),
        )

    def _record_event(
        self, item: RunItem, step: Step, status: EventStatus, layer: int | None, duration: int
    ) -> None:
        self.session.add(
            StepEvent(
                run_item_id=item.id,
                step_id=step.id,
                status=status,
                layer=layer,
                duration_ms=duration,
            )
        )

    def _record_success(
        self, item: RunItem, step: Step, outcome: StepOutcome, duration: int, values: dict[str, str]
    ) -> None:
        self._record_event(item, step, EventStatus.OK, outcome.layer, duration)

        if outcome.new_target is not None:
            self._save_repair(item, step, outcome)
        elif outcome.target_index:
            self._promote_old_version(step, outcome.target_index)
        if outcome.download is not None:
            self._save_download(item, step, outcome, values)
        if outcome.captured is not None:
            self._save_capture(item, step, outcome.captured, values)
        self.session.commit()

    def _save_capture(
        self,
        item: RunItem,
        step: Step,
        captured: str | list[dict[str, str]],
        values: dict[str, str],
    ) -> None:
        # Se o portal exibir uma senha salva na tela, ela não vai parar na planilha
        secrets = self.credential_secrets
        if isinstance(captured, str):
            clean: str | list[dict[str, str]] = scrub(captured, secrets)
            values[step.capture_key] = clean
        else:
            clean = [{name: scrub(cell, secrets) for name, cell in row.items()} for row in captured]
        # Cópia nova: o SQLAlchemy só percebe a mudança em um JSON quando o objeto é outro
        item.output = {**item.output, step.capture_key: clean}

    def _save_repair(self, item: RunItem, step: Step, outcome: StepOutcome) -> None:
        save_new_version(
            self.session,
            step,
            outcome.new_target,
            _SOURCE_BY_LAYER[outcome.layer],
            owner_id=self.run.owner_id,
            run_id=self.run.id,
            layer=outcome.layer,
            score=outcome.score,
            explanation=outcome.explanation,
        )
        item.problem_step_position = step.position
        item.resolved_layer = outcome.layer
        self.session.flush()
        self.session.refresh(step, ["versions"])
        tag = f"{item.position:02d}/{self.total}"
        run_lifecycle.add_log(
            self.session,
            self.run,
            LogLevel.SEARCH,
            f"[{tag}] passo {step.position} reparado: {outcome.explanation}",
        )

    def _promote_old_version(self, step: Step, index: int) -> None:
        """O site voltou ao layout antigo: o caminho que funcionou volta a ser o atual."""
        versions = sorted(
            step.versions, key=lambda version: (version.is_current, version.version), reverse=True
        )
        for version in versions:
            version.is_current = False
        versions[index].is_current = True

    def _save_download(
        self, item: RunItem, step: Step, outcome: StepOutcome, values: dict[str, str]
    ) -> None:
        suggested = f"{item.position:03d}-{outcome.download.suggested_filename}"
        relative = safe_relative_path(step.save_as, values, suggested)
        key = f"{self.run.owner_id}/{self.run.id}/{relative}"
        # O navegador entrega o arquivo no disco; dali ele vai para o destino configurado (pasta
        # ou bucket), só depois de passar no limite de tamanho
        with tempfile.TemporaryDirectory(prefix="ditto-download-") as folder:
            downloaded = Path(folder) / "arquivo"
            outcome.download.save_as(downloaded)
            if downloaded.stat().st_size > MAX_DOWNLOAD_BYTES:
                raise BusinessRuleError("O arquivo baixado passa do tamanho permitido.")
            size = storage.save_file(key, downloaded)

        self.session.add(
            Artifact(
                owner_id=self.run.owner_id,
                run_item_id=item.id,
                kind=ArtifactKind.FILE,
                file_name=relative.rsplit("/", 1)[-1],
                storage_key=key,
                size_bytes=size,
            )
        )

    def _save_diagnostics(self, item: RunItem, diagnostics: dict[str, Any]) -> None:
        """Fica ao lado da tela da falha, só para investigar. Não aparece no painel, e é apagado
        junto com a tela (veja diagnostics_key_for)."""
        key = diagnostics_key_for(self._screenshot_key(item))
        storage.save_bytes(key, json.dumps(diagnostics, ensure_ascii=False, indent=1).encode())

    def _screenshot_key(self, item: RunItem) -> str:
        return f"{self.run.owner_id}/{self.run.id}/{_SCREENS_FOLDER}/linha-{item.position}.png"

    def _screenshot(self, page: Page, item: RunItem) -> bool:
        """Só para investigar problemas. Campos de senha saem cobertos. Devolve se guardou."""
        try:
            content = page.screenshot(mask=[page.locator("input[type=password]")], timeout=5000)
        except PlaywrightError:
            return False
        for old_key in RunRepository(self.session).replace_screenshot(item.id):
            storage.delete(old_key)
        key = self._screenshot_key(item)
        size = storage.save_bytes(key, content)
        self.session.add(
            Artifact(
                owner_id=self.run.owner_id,
                run_item_id=item.id,
                kind=ArtifactKind.SCREENSHOT,
                file_name=f"tela-linha-{item.position}.png",
                content_type="image/png",
                storage_key=key,
                size_bytes=size,
            )
        )
        return True

    def _open_help(self, item: RunItem, step: Step, outcome: StepOutcome) -> None:
        title = {
            HelpKind.CONFIRM: f"Posso seguir com este passo: {step.intent}?",
            HelpKind.CHOOSE: f"Qual destes é o caminho para: {step.intent}?",
            HelpKind.CAPTCHA: "O portal pediu um CAPTCHA",
            HelpKind.UNCERTAIN: "Não encontrei como seguir",
        }[outcome.help_kind]

        # Cancelada enquanto o passo rodava: não abre pedido nem manda e-mail
        self._lock_running()
        item.status = ItemStatus.WAITING_HUMAN
        self.run.status = RunStatus.WAITING_HUMAN
        self.session.add(
            HelpRequest(
                owner_id=self.run.owner_id,
                run_id=self.run.id,
                run_item_id=item.id,
                step_id=step.id,
                kind=outcome.help_kind,
                title=title[:300],
                message=f"{outcome.message} Parei na linha {item.position} de {self.total}.",
                options=outcome.options,
                expires_at=datetime.now(UTC) + timedelta(hours=settings.help_timeout_hours),
            )
        )
        tag = f"{item.position:02d}/{self.total}"
        run_lifecycle.add_log(
            self.session, self.run, LogLevel.INFO, f"[{tag}] esperando você: {title}"
        )
        self.session.commit()
        self._alert_owner(
            f"O Ditto precisa de você: {self.flow.name}",
            f"{title}\n\n{outcome.message}\n\nResponda em {settings.panel_url}/painel/reparos",
        )

    def _finish_item(self, item: RunItem, started: float) -> None:
        self._lock_running()
        item.duration_ms = int((time.monotonic() - started) * 1000)
        item.finished_at = datetime.now(UTC)
        item.status = ItemStatus.REPAIRED if item.resolved_layer else ItemStatus.SUCCEEDED
        seconds = item.duration_ms / 1000
        tag = f"{item.position:02d}/{self.total}"
        run_lifecycle.add_log(
            self.session, self.run, LogLevel.OK, f"[{tag}] {item.label}  ({seconds:.0f} s)"
        )
        self.session.commit()

    def _log_failure(self, item: RunItem, message: str) -> None:
        # A falha só vale se a execução ainda está rodando: senão a linha fica como o
        # cancelamento deixou
        self._lock_running()
        tag = f"{item.position:02d}/{self.total}"
        run_lifecycle.add_log(self.session, self.run, LogLevel.FAILURE, f"[{tag}] {message}")
        self.session.commit()

    def _alert_owner(self, subject: str, text: str) -> None:
        # Quem desligou os alertas continua vendo os pedidos no painel
        if self.owner.email_alerts:
            send_email(self.owner.email, subject, text)

    def _notify_if_problem(self) -> None:
        if self.run.status in {RunStatus.FAILED, RunStatus.PARTIAL}:
            self._alert_owner(
                f"Execução com problemas: {self.flow.name}",
                f"Veja o que aconteceu em {settings.panel_url}/painel/execucoes/{self.run.id}",
            )


def requeue_item_after_crash(item: RunItem) -> None:
    """Uma linha interrompida volta para a fila, a menos que já tenha tocado em um passo sem volta."""
    if item.status != ItemStatus.RUNNING:
        return
    if item.irreversible_done:
        run_lifecycle.fail_item(
            item, "A linha foi interrompida depois de um passo sem volta. Confira no portal."
        )
    else:
        item.status = ItemStatus.PENDING


_PHASE_NAMES = {
    "locate": "achar",
    "act": "agir",
    "settle": "esperar a página",
    "check": "conferir",
}


def _log_step_timing(
    item: RunItem, step: Step, duration_ms: int, timings: dict[str, float]
) -> None:
    """Uma linha por passo no log do worker: onde a execução gastou o tempo. Só tempos e o
    número do passo, nenhum valor digitado."""
    measured = sum(timings.values())
    parts = [
        f"{_PHASE_NAMES[phase]} {timings[phase]:.1f}s" for phase in _PHASE_NAMES if phase in timings
    ]
    parts.append(f"outros {max(duration_ms / 1000 - measured, 0):.1f}s")
    logger.info(
        "Linha %s, passo %s (%s): %.1fs no total; %s",
        item.position,
        step.position,
        step.action.value if hasattr(step.action, "value") else step.action,
        duration_ms / 1000,
        ", ".join(parts),
    )


def diagnostics_key_for(screenshot_key: str) -> str | None:
    """Onde ficam os detalhes da falha que acompanham uma tela. None se não for uma tela."""
    folder, _, name = screenshot_key.rpartition("/")
    if not folder.endswith(f"/{_SCREENS_FOLDER}") or not name.endswith(".png"):
        return None
    return f"{folder}/{name.removesuffix('.png')}-foco.json"


def _close_tabs(tabs: ItemTabs) -> None:
    try:
        tabs.close()
    except PlaywrightError:
        # Com o navegador fora do ar, não há aba para fechar
        logger.info("As abas da linha já estavam fechadas.")
