"""Telegram-бот приёма документов.

Тонкий слой: whitelist → скачать вложения → буфер → backend /agent/turn → карточка.
Запуск: BOT_TOKEN=... BACKEND_URL=http://localhost:8000 uv run python -m bot.main

BOT_WHITELIST="123456:demo,222333:acme" — telegram_user_id:tenant (база 1С).
"""

import base64
import os
import uuid

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from copilot_shared import OperationDraft

from .buffer import Attachment, ChatBuffer
from .cards import render_card

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _parse_whitelist() -> dict[int, str]:
    out: dict[int, str] = {}
    for pair in os.environ.get("BOT_WHITELIST", "").split(","):
        pair = pair.strip()
        if ":" in pair:
            uid, tenant = pair.split(":", 1)
            out[int(uid)] = tenant
    return out


WHITELIST = _parse_whitelist()

bot = Bot(token=os.environ["BOT_TOKEN"])
dp = Dispatcher()
_http = httpx.AsyncClient(base_url=BACKEND_URL, timeout=120.0)

# Активные предложения операций по чату (ждут нажатия кнопки).
_proposals: dict[int, OperationDraft] = {}


def _tenant(user_id: int) -> str | None:
    return WHITELIST.get(user_id)


async def _download(file_id: str) -> str:
    buf = await bot.download(file_id)
    return base64.standard_b64encode(buf.read()).decode()


async def _flush(chat_id: int, text: str, attachments: list[Attachment]) -> None:
    tenant = _chat_tenant.get(chat_id)
    if tenant is None:
        return
    payload = {
        "tenant": tenant,
        "chat_id": chat_id,
        "text": text,
        "attachments": [a.__dict__ for a in attachments],
    }
    r = await _http.post("/agent/turn", json=payload)
    r.raise_for_status()
    data = r.json()

    if data["type"] == "proposal":
        op = OperationDraft.model_validate(data["proposal"])
        _proposals[chat_id] = op
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Отправить в 1С", callback_data="confirm"),
            InlineKeyboardButton(text="✏️ Исправить", callback_data="edit"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ]])
        await bot.send_message(chat_id, render_card(op), reply_markup=kb, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, data.get("reply_text") or "…")


_buffer = ChatBuffer(on_flush=_flush)
_chat_tenant: dict[int, str] = {}


@dp.message(CommandStart())
async def on_start(msg: Message) -> None:
    if _tenant(msg.from_user.id) is None:
        await msg.answer("Доступ не настроен. Обратитесь к администратору.")
        return
    await msg.answer("Пришлите фото или файл документа — заведу операцию в 1С. "
                     "Умею: поступление, реализацию, чек/подотчёт, платёжное поручение.")


@dp.message(F.voice | F.audio)
async def on_voice(msg: Message) -> None:
    await msg.answer("Голосовые сообщения я пока не понимаю. Пришлите, пожалуйста, "
                     "фото/файл документа или напишите текстом.")


@dp.message()
async def on_message(msg: Message) -> None:
    tenant = _tenant(msg.from_user.id)
    if tenant is None:
        await msg.answer("Доступ не настроен. Обратитесь к администратору.")
        return
    _chat_tenant[msg.chat.id] = tenant

    if msg.photo:
        att = Attachment("image", "image/jpeg", await _download(msg.photo[-1].file_id))
        _buffer.add_attachment(msg.chat.id, att)
    if msg.document:
        mime = msg.document.mime_type or ""
        if mime == "application/pdf":
            _buffer.add_attachment(
                msg.chat.id, Attachment("pdf", "application/pdf", await _download(msg.document.file_id)))
        elif mime.startswith("image/"):
            _buffer.add_attachment(
                msg.chat.id, Attachment("image", mime, await _download(msg.document.file_id)))
        else:
            await msg.answer("Такой тип файла я пока не обрабатываю. Пришлите фото или PDF.")
    text = msg.text or msg.caption
    if text:
        _buffer.add_text(msg.chat.id, text)


@dp.callback_query(F.data == "confirm")
async def on_confirm(cb: CallbackQuery) -> None:
    chat_id = cb.message.chat.id
    op = _proposals.pop(chat_id, None)
    if op is None:
        await cb.answer("Нет активной операции")
        return
    payload = {
        "tenant": _chat_tenant.get(chat_id, "demo"),
        "chat_id": chat_id,
        "proposal": op.model_dump(),
        "external_id": f"tg-{chat_id}-{uuid.uuid4().hex[:8]}",
    }
    r = await _http.post("/agent/confirm", json=payload)
    r.raise_for_status()
    resp = r.json()
    await cb.message.edit_reply_markup(reply_markup=None)
    hit = " (уже был создан ранее)" if resp.get("idempotent_hit") else ""
    await bot.send_message(chat_id, f"✅ В 1С создан черновик «{resp['doc_type_1c']}» "
                                    f"№ {resp['doc_number']}{hit}. Проверьте и проведите в базе.")
    await cb.answer()


@dp.callback_query(F.data == "edit")
async def on_edit(cb: CallbackQuery) -> None:
    await cb.answer()
    await bot.send_message(cb.message.chat.id, "Напишите, что исправить (например: «дата 15 июля» "
                                               "или «контрагент другой»).")


@dp.callback_query(F.data == "cancel")
async def on_cancel(cb: CallbackQuery) -> None:
    _proposals.pop(cb.message.chat.id, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Отменено")


def main() -> None:
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
