"""Pedidos de "criar tarefa com IA" vindos do painel. Quem navega é o worker (ai_explorer.py)."""

import uuid
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    ServiceNotConfiguredError,
)
from app.models.ai_draft import AiDraft
from app.models.enums import AiDraftStatus
from app.repositories.ai_draft_repository import OPEN_STATUSES, AiDraftRepository
from app.schemas.ai_draft import AiDraftAnswer, AiDraftCreate, AiDraftResponse

MAX_LISTED = 20
MAX_EVENTS_SHOWN = 200


def to_response(draft: AiDraft) -> AiDraftResponse:
    return AiDraftResponse(
        id=draft.id,
        status=draft.status,
        prompt=draft.prompt,
        start_url=draft.start_url,
        name=draft.name,
        step_count=len(draft.steps or []),
        events=(draft.events or [])[-MAX_EVENTS_SHOWN:],
        question=draft.question,
        error=draft.error,
        flow_id=draft.flow_id,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


class AiDraftService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.drafts = AiDraftRepository(session)

    def _get(self, draft_id: uuid.UUID, owner_id: uuid.UUID) -> AiDraft:
        draft = self.drafts.get_owned(draft_id, owner_id)
        if draft is None:
            raise NotFoundError("Este pedido não foi encontrado.")
        return draft

    def create(self, owner_id: uuid.UUID, payload: AiDraftCreate) -> AiDraftResponse:
        if not settings.llm_enabled:
            raise ServiceNotConfiguredError(
                "A IA não está configurada. Preencha LLM_API_KEY e LLM_MODEL no .env do backend."
            )
        if not settings.extension_runner_port:
            raise BusinessRuleError(
                "A IA monta a tarefa no seu Chrome, pela extensão. Coloque EXTENSION_RUNNER_PORT=8765 "
                "no .env do backend e reinicie o worker."
            )
        if self.drafts.has_open(owner_id):
            raise ConflictError("A IA já está montando uma tarefa. Espere ela terminar ou cancele.")

        draft = AiDraft(
            owner_id=owner_id,
            prompt=payload.prompt,
            start_url=payload.start_url,
            name=payload.name,
            status=AiDraftStatus.QUEUED,
            steps=[],
            events=[],
            allowed_hosts=[(urlsplit(payload.start_url).hostname or "").lower()],
        )
        self.drafts.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        return to_response(draft)

    def list(self, owner_id: uuid.UUID) -> list[AiDraftResponse]:
        return [to_response(draft) for draft in self.drafts.list_owned(owner_id, MAX_LISTED)]

    def get(self, draft_id: uuid.UUID, owner_id: uuid.UUID) -> AiDraftResponse:
        return to_response(self._get(draft_id, owner_id))

    def answer(
        self, draft_id: uuid.UUID, owner_id: uuid.UUID, payload: AiDraftAnswer
    ) -> AiDraftResponse:
        draft = self._get(draft_id, owner_id)
        if draft.status != AiDraftStatus.WAITING_ANSWER or draft.question is None:
            raise ConflictError("A IA não está esperando resposta agora.")
        if draft.answer is not None:
            raise ConflictError("Esta dúvida já foi respondida.")
        draft.answer = payload.answer.strip()
        self.session.commit()
        self.session.refresh(draft)
        return to_response(draft)

    def cancel(self, draft_id: uuid.UUID, owner_id: uuid.UUID) -> AiDraftResponse:
        draft = self._get(draft_id, owner_id)
        if draft.status not in OPEN_STATUSES:
            raise ConflictError("Este pedido já terminou.")
        # O worker confere a situação a cada passo e fecha a aba quando vê o cancelamento
        draft.status = AiDraftStatus.CANCELED
        draft.question = None
        self.session.commit()
        self.session.refresh(draft)
        return to_response(draft)
