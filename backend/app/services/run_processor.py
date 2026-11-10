"""Liga o motor ao banco: percorre as linhas, registra tudo e decide quando parar."""

import logging
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page
from playwright.sync_api import Error as PlaywrightError
from sqlalchemy import select
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
from app.services.email_service import send_email
from app.services.engine.browser import host_matches, new_guarded_context
from app.services.engine.executor import StepOutcome, StepPlan, StepRunner
from app.services.engine.llm_repair import LlmRepairer
from app.services.repair_service import save_new_version
from app.services.sanitizer import scrub
from app.services.templating import render, rule_values, safe_relative_path

logger = logging.getLogger(__name__)

_SOURCE_BY_LAYER = {2: VersionSource.SIMILARITY, 3: VersionSource.LLM}
_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024


class _Paused(Exception):
    """A linha parou esperando uma pessoa."""


class _Canceled(Exception):
    """A pessoa cancelou a execução enquanto ela rodava."""


class RunProcessor:
    def __init__(
        self, session: Session, run: Run, browser: Browser, repairer: LlmRepairer | None = None
    ) -> None:
        self.session = session
        self.run = run
        self.browser = browser
        self.repairer = repairer
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

    def process(self) -> None:
        failures_in_a_row = 0
        try:
            for item in self.run.items:
                if item.status not in {ItemStatus.PENDING, ItemStatus.RUNNING}:
                    continue

                self._process_item(item)
                failures_in_a_row = failures_in_a_row + 1 if item.status == ItemStatus.FAILED else 0
                if failures_in_a_row >= settings.circuit_breaker_failures:
                    self._trip_circuit_breaker()
                    break
        except _Paused:
            self.session.commit()
            return
        except _Canceled:
            self.session.commit()
            return

        run_lifecycle.finalize(self.session, self.run)
        self.session.commit()
        self._notify_if_problem()

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

    def _ensure_not_canceled(self) -> None:
        self.session.commit()
        self.session.refresh(self.run, ["status"])
        if self.run.status == RunStatus.CANCELED:
            raise _Canceled

    def _process_item(self, item: RunItem) -> None:
        self._ensure_not_canceled()

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
        context = new_guarded_context(self.browser, self.flow.allowed_domains)
        try:
            page = context.new_page()
            runner = self._new_runner(page, item)
            for step in self.steps:
                # Um clique pode ter aberto outra janela: o próximo passo acontece nela
                page = context.pages[-1] if context.pages else page
                runner.page = page
                if not self._run_step(page, runner, item, step, values):
                    return
            self._finish_item(item, started)
        except BusinessRuleError as error:
            run_lifecycle.fail_item(item, error.detail)
            self._log_failure(item, error.detail)
        except PlaywrightError as error:
            # A mensagem do navegador pode conter valores digitados: só o tipo vai para o log
            logger.warning(
                "Falha do navegador na linha %s: %s", item.position, type(error).__name__
            )
            message = "O navegador não conseguiu concluir esta linha."
            run_lifecycle.fail_item(item, message)
            self._log_failure(item, message)
        finally:
            context.close()

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
        self._ensure_not_canceled()
        self._pause_if_needs_confirmation(item, step)

        started = time.monotonic()
        plan = self._build_plan(page, item, step, values)
        outcome = runner.run(plan)
        duration = int((time.monotonic() - started) * 1000)

        if outcome.status == "ok":
            self._record_success(item, step, outcome, duration, values)
            return True

        self._screenshot(page, item)
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
        host = (urlsplit(page.url).hostname or "").lower()
        for domain, credential in self.credentials.items():
            if host_matches(host, [domain]):
                return credential
        # Uma única credencial na tarefa serve mesmo se o login estiver em outro subdomínio
        return next(iter(self.credentials.values()), {})

    def _build_plan(
        self, page: Page, item: RunItem, step: Step, values: dict[str, str]
    ) -> StepPlan:
        if step.credential_field:
            value = self._credential_for(page).get(step.credential_field)
            if not value:
                raise BusinessRuleError("Falta salvar o acesso a este portal.")
        else:
            value = render(step.value_template, values) if step.value_template is not None else None

        versions = sorted(
            step.versions, key=lambda version: (version.is_current, version.version), reverse=True
        )
        # Nada disso pode chegar à IA: senhas dos portais e os dados da linha
        secrets = [
            secret for credential in self.credentials.values() for secret in credential.values()
        ]
        secrets.extend(values.values())

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
        secrets = [
            secret for credential in self.credentials.values() for secret in credential.values()
        ]
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
        path = storage.path_for_write(key)
        outcome.download.save_as(path)

        size = path.stat().st_size
        if size > _MAX_DOWNLOAD_BYTES:
            storage.delete(key)
            raise BusinessRuleError("O arquivo baixado passa do tamanho permitido.")

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

    def _screenshot(self, page: Page, item: RunItem) -> None:
        """Só para investigar problemas. Campos de senha saem cobertos."""
        try:
            content = page.screenshot(mask=[page.locator("input[type=password]")], timeout=5000)
        except PlaywrightError:
            return
        for old_key in RunRepository(self.session).replace_screenshot(item.id):
            storage.delete(old_key)
        key = f"{self.run.owner_id}/{self.run.id}/.telas/linha-{item.position}.png"
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

    def _open_help(self, item: RunItem, step: Step, outcome: StepOutcome) -> None:
        title = {
            HelpKind.CONFIRM: f"Posso seguir com este passo: {step.intent}?",
            HelpKind.CHOOSE: f"Qual destes é o caminho para: {step.intent}?",
            HelpKind.CAPTCHA: "O portal pediu um CAPTCHA",
            HelpKind.UNCERTAIN: "Não encontrei como seguir",
        }[outcome.help_kind]

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


def items_of(session: Session, run: Run) -> list[RunItem]:
    return list(session.scalars(select(RunItem).where(RunItem.run_id == run.id)))
