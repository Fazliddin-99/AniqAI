"""HTTP-обёртка ядра агента. Бот (apps/bot) — тонкий клиент этих эндпоинтов.

Сессии диалогов живут здесь, в памяти (v1). Ключ — tenant:chat_id.
"""

from typing import Literal

from copilot_shared import CreateOperationResponse, OperationDraft
from fastapi import APIRouter
from pydantic import BaseModel

from . import onec_client
from .core import AgentSession, Attachment

router = APIRouter(prefix="/agent", tags=["agent"])

_sessions: dict[str, AgentSession] = {}


def _session(tenant: str, chat_id: int) -> AgentSession:
    key = f"{tenant}:{chat_id}"
    if key not in _sessions:
        _sessions[key] = AgentSession(tenant=tenant)
    return _sessions[key]


class AttachmentIn(BaseModel):
    kind: Literal["image", "pdf"]
    media_type: str
    data_b64: str


class TurnIn(BaseModel):
    tenant: str
    chat_id: int
    text: str = ""
    attachments: list[AttachmentIn] = []


class TurnOut(BaseModel):
    type: Literal["reply", "proposal"]
    reply_text: str | None = None
    proposal: OperationDraft | None = None


class ConfirmIn(BaseModel):
    tenant: str
    chat_id: int
    proposal: OperationDraft
    external_id: str


@router.post("/turn", response_model=TurnOut)
def turn(body: TurnIn) -> TurnOut:
    session = _session(body.tenant, body.chat_id)
    attachments = [Attachment(a.kind, a.media_type, a.data_b64) for a in body.attachments]
    result = session.process_turn(body.text, attachments)
    if result.proposal is not None:
        return TurnOut(type="proposal", proposal=result.proposal)
    return TurnOut(type="reply", reply_text=result.reply_text)


@router.post("/confirm", response_model=CreateOperationResponse)
def confirm(body: ConfirmIn) -> CreateOperationResponse:
    op = body.proposal.model_copy(update={"external_id": body.external_id})
    resp = onec_client.create_operation(op)
    _session(body.tenant, body.chat_id).note_confirmation(resp.draft_id)
    return resp
