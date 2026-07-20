"""HTTP-обёртка ядра агента. Бот шлёт telegram_user_id — бэкенд по БД определяет
компанию и её подключение к 1С, отклоняет неизвестных. Сессии — в памяти (v1)."""

from typing import Literal

from copilot_shared import CreateOperationResponse, OperationDraft
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import service
from ..db.session import get_session
from .core import AgentSession, Attachment
from .onec_client import OnecClient

router = APIRouter(prefix="/agent", tags=["agent"])

_sessions: dict[str, AgentSession] = {}


def _resolve(telegram_user_id: int) -> service.ResolvedUser:
    db = get_session()
    try:
        resolved = service.resolve_user(db, telegram_user_id)
    finally:
        db.close()
    if resolved is None:
        raise HTTPException(403, "Доступ не настроен")
    return resolved


def _session(resolved: service.ResolvedUser, chat_id: int) -> AgentSession:
    key = f"{resolved.company_id}:{chat_id}"
    if key not in _sessions:
        onec = OnecClient(resolved.onec.base_url, resolved.onec.user, resolved.onec.password)
        _sessions[key] = AgentSession(tenant=str(resolved.company_id), onec=onec)
    return _sessions[key]


class AttachmentIn(BaseModel):
    kind: Literal["image", "pdf"]
    media_type: str
    data_b64: str


class TurnIn(BaseModel):
    telegram_user_id: int
    chat_id: int
    text: str = ""
    attachments: list[AttachmentIn] = []


class TurnOut(BaseModel):
    type: Literal["reply", "proposal"]
    reply_text: str | None = None
    proposal: OperationDraft | None = None


class ConfirmIn(BaseModel):
    telegram_user_id: int
    chat_id: int
    proposal: OperationDraft
    external_id: str


@router.post("/turn", response_model=TurnOut)
def turn(body: TurnIn) -> TurnOut:
    session = _session(_resolve(body.telegram_user_id), body.chat_id)
    attachments = [Attachment(a.kind, a.media_type, a.data_b64) for a in body.attachments]
    result = session.process_turn(body.text, attachments)
    if result.proposal is not None:
        return TurnOut(type="proposal", proposal=result.proposal)
    return TurnOut(type="reply", reply_text=result.reply_text)


@router.post("/confirm", response_model=CreateOperationResponse)
def confirm(body: ConfirmIn) -> CreateOperationResponse:
    session = _session(_resolve(body.telegram_user_id), body.chat_id)
    op = body.proposal.model_copy(update={"external_id": body.external_id})
    resp = session.onec.create_operation(op)
    session.note_confirmation(resp.draft_id)
    return resp
