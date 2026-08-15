"""HTTP-обёртка ядра агента. Бот шлёт telegram_user_id — бэкенд по БД определяет
компанию и её подключение к 1С, отклоняет неизвестных. Сессии — в памяти (v1)."""

import base64
import os
from typing import Literal

import httpx
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
        # Демо-режим: незнакомый пользователь автоматически заводится в демо-компанию.
        # На проде флаг обязан быть выключен — доступ только по whitelist'у админки.
        if resolved is None and os.environ.get("DEMO_AUTO_REGISTER") == "1":
            company_id = int(os.environ.get("DEMO_COMPANY_ID", "1"))
            if service.get_company(db, company_id) is not None:
                service.create_user(db, telegram_user_id, company_id,
                                    name=f"Демо-пользователь {telegram_user_id}",
                                    role="demo")
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
    images: list[str] = []  # PNG-графики аналитики, base64


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
    return TurnOut(type="reply", reply_text=result.reply_text,
                   images=[base64.b64encode(i).decode() for i in result.images])


@router.post("/confirm", response_model=CreateOperationResponse)
def confirm(body: ConfirmIn) -> CreateOperationResponse:
    session = _session(_resolve(body.telegram_user_id), body.chat_id)
    op = body.proposal.model_copy(update={"external_id": body.external_id})
    try:
        resp = session.onec.create_operation(op)
    except httpx.HTTPStatusError as e:
        # Отказ 1С («тип не реализован», «итоги не сходятся»…) — пользователю
        # дословно, а не молчаливой 500-й.
        detail = "1С не приняла операцию."
        try:
            detail = e.response.json()["error"]["message"]
        except Exception:  # noqa: BLE001 — тело может быть не по формату §6
            pass
        raise HTTPException(e.response.status_code, detail) from e
    session.note_confirmation(resp.draft_id)
    return resp


class PostIn(BaseModel):
    telegram_user_id: int
    chat_id: int
    draft_id: str


@router.post("/post", response_model=CreateOperationResponse)
def post_document(body: PostIn) -> CreateOperationResponse:
    """Провести созданный черновик (ТЗ §6.1). Вызывается ботом только после
    явного нажатия пользователем кнопки «Провести»."""
    session = _session(_resolve(body.telegram_user_id), body.chat_id)
    try:
        resp = session.onec.post_operation(body.draft_id)
    except httpx.HTTPStatusError as e:
        # Текст отказа 1С («не заполнен счёт учёта…») должен дойти до пользователя.
        detail = "Не удалось провести документ."
        try:
            detail = e.response.json()["error"]["message"]
        except Exception:  # noqa: BLE001 — тело может быть не по формату §6
            pass
        raise HTTPException(e.response.status_code, detail) from e
    session.note_posting(body.draft_id)
    return resp
