"""Telegram-бот приёма документов.

Тонкий слой: скачать вложения → буфер → backend /agent/turn → карточка.
Доступ (кто к какой компании) решает бэкенд по БД; бот шлёт только telegram_user_id.
Запуск: uv run python -m bot.main  (переменные — из корневого .env)
"""

import asyncio
import base64
import os
import uuid

from dotenv import find_dotenv, load_dotenv

# Загрузить .env до чтения BOT_TOKEN (Bot создаётся на уровне модуля).
load_dotenv(find_dotenv(usecwd=True))

import httpx  # noqa: E402
from aiogram import Bot, Dispatcher, F  # noqa: E402
from aiogram.filters import CommandStart  # noqa: E402
from aiogram.types import (  # noqa: E402
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from copilot_shared import OperationDraft  # noqa: E402

from .buffer import Attachment, ChatBuffer  # noqa: E402
from .cards import render_card  # noqa: E402
from .format import md_to_html  # noqa: E402

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
_ACCESS_DENIED = "Доступ не настроен. Обратитесь к администратору."

bot = Bot(token=os.environ["BOT_TOKEN"])
dp = Dispatcher()
# 300с: аналитический ход (несколько отчётов 1С + графики) не укладывается в 120.
_http = httpx.AsyncClient(base_url=BACKEND_URL, timeout=300.0)

# Предложение привязано к конкретному сообщению-карточке: кнопки старой карточки
# не должны действовать на новую версию операции (инцидент «Нет активной операции»
# после исправления даты, 15.08.2026).
_proposals: dict[tuple[int, int], OperationDraft] = {}  # (chat_id, msg_id) -> черновик
_last_card: dict[int, int] = {}              # chat_id -> msg_id последней карточки
_chat_user: dict[int, int] = {}              # chat_id -> telegram_user_id
_created: dict[int, str] = {}                # chat_id -> draft_id последнего черновика
_chat_locks: dict[int, asyncio.Lock] = {}    # ходы одного чата — строго по очереди


async def _send_html(chat_id: int, text: str, **kwargs) -> Message:
    """Отправить текст агента: Markdown → HTML, при ошибке разметки — как есть."""
    try:
        return await bot.send_message(chat_id, md_to_html(text), parse_mode="HTML", **kwargs)
    except Exception:  # noqa: BLE001 — разметка не должна терять сообщение
        return await bot.send_message(chat_id, text, **kwargs)


async def _download(file_id: str) -> str:
    buf = await bot.download(file_id)
    return base64.standard_b64encode(buf.read()).decode()


async def _flush(chat_id: int, text: str, attachments: list[Attachment]) -> None:
    # Пока агент обрабатывает предыдущий ход, следующий ждёт: параллельные ходы
    # одного чата ломали историю сессии на бэкенде (инцидент 15.08.2026).
    async with _chat_locks.setdefault(chat_id, asyncio.Lock()):
        await _flush_locked(chat_id, text, attachments)


async def _flush_locked(chat_id: int, text: str, attachments: list[Attachment]) -> None:
    uid = _chat_user.get(chat_id)
    if uid is None:
        return
    payload = {
        "telegram_user_id": uid,
        "chat_id": chat_id,
        "text": text,
        "attachments": [a.__dict__ for a in attachments],
    }
    try:
        r = await _http.post("/agent/turn", json=payload)
        if r.status_code == 403:
            await bot.send_message(chat_id, _ACCESS_DENIED)
            return
        r.raise_for_status()
        data = r.json()

        if data["type"] == "proposal":
            op = OperationDraft.model_validate(data["proposal"])
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Отправить в 1С", callback_data="confirm"),
                InlineKeyboardButton(text="✏️ Исправить", callback_data="edit"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
            ]])
            sent = await _send_html(chat_id, render_card(op), reply_markup=kb)
            # Новая карточка замещает старую: у прежней отбираем кнопки, чтобы
            # нельзя было отправить устаревшую версию операции.
            prev = _last_card.pop(chat_id, None)
            if prev is not None:
                _proposals.pop((chat_id, prev), None)
                try:
                    await bot.edit_message_reply_markup(chat_id, prev, reply_markup=None)
                except Exception:  # noqa: BLE001 — карточка могла быть уже без кнопок
                    pass
            _proposals[(chat_id, sent.message_id)] = op
            _last_card[chat_id] = sent.message_id
        else:
            await _send_html(chat_id, data.get("reply_text") or "…")
            # Графики аналитики — фотографиями следом за текстом.
            for i, img_b64 in enumerate(data.get("images") or []):
                await bot.send_photo(chat_id, BufferedInputFile(
                    base64.b64decode(img_b64), filename=f"chart{i + 1}.png"))
    except Exception as e:  # noqa: BLE001 — не оставлять «висящее» исключение в задаче буфера
        print(f"[flush error] chat={chat_id}: {e!r}")
        await bot.send_message(chat_id, "Не удалось обработать сообщение. Попробуйте ещё раз "
                                        "или пришлите документ заново.")


_buffer = ChatBuffer(on_flush=_flush)


@dp.message(CommandStart())
async def on_start(msg: Message) -> None:
    await msg.answer("Пришлите фото или файл документа — заведу операцию в 1С. "
                     "Умею: поступление, реализацию, чек/подотчёт, платёжное поручение.")


@dp.message(F.voice | F.audio)
async def on_voice(msg: Message) -> None:
    await msg.answer("Голосовые сообщения я пока не понимаю. Пришлите, пожалуйста, "
                     "фото/файл документа или напишите текстом.")


@dp.message()
async def on_message(msg: Message) -> None:
    _chat_user[msg.chat.id] = msg.from_user.id

    if msg.photo:
        _buffer.add_attachment(
            msg.chat.id, Attachment("image", "image/jpeg", await _download(msg.photo[-1].file_id)))
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
    op = _proposals.pop((chat_id, cb.message.message_id), None)
    if op is None:
        await cb.answer("Эта карточка устарела — используйте последнюю", show_alert=True)
        return
    _last_card.pop(chat_id, None)

    def _restore() -> None:
        """Вернуть предложение — при ошибке карточка должна остаться рабочей."""
        _proposals[(chat_id, cb.message.message_id)] = op
        _last_card[chat_id] = cb.message.message_id

    payload = {
        "telegram_user_id": cb.from_user.id,
        "chat_id": chat_id,
        "proposal": op.model_dump(),
        "external_id": f"tg-{chat_id}-{uuid.uuid4().hex[:8]}",
    }
    try:
        r = await _http.post("/agent/confirm", json=payload)
        if r.status_code == 403:
            await cb.message.edit_reply_markup(reply_markup=None)
            await bot.send_message(chat_id, _ACCESS_DENIED)
            await cb.answer()
            return
        if r.status_code in (400, 404, 422):
            # 1С отказала с причиной — показать её и оставить карточку живой.
            reason = r.json().get("detail", "причина не указана")
            _restore()
            await bot.send_message(chat_id, f"⚠️ 1С не приняла операцию: {reason}")
            await cb.answer()
            return
        r.raise_for_status()
        resp = r.json()
    except Exception as e:  # noqa: BLE001 — молчаливый провал кнопки недопустим
        print(f"[confirm error] chat={chat_id}: {e!r}")
        _restore()
        await bot.send_message(chat_id, "Не удалось отправить в 1С (сбой связи). "
                                        "Нажмите «Отправить» ещё раз.")
        await cb.answer()
        return
    await cb.message.edit_reply_markup(reply_markup=None)
    hit = " (уже был создан ранее)" if resp.get("idempotent_hit") else ""
    # Проведение — только по явной кнопке (решение владельца, ТЗ §6.1).
    _created[chat_id] = resp["draft_id"]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📮 Провести в 1С", callback_data="post"),
        InlineKeyboardButton(text="Оставить черновиком", callback_data="keep_draft"),
    ]])
    await bot.send_message(chat_id, f"✅ В 1С создан черновик «{resp['doc_type_1c']}» "
                                    f"№ {resp['doc_number']}{hit}.", reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data == "post")
async def on_post(cb: CallbackQuery) -> None:
    chat_id = cb.message.chat.id
    draft_id = _created.pop(chat_id, None)
    if draft_id is None:
        await cb.answer("Нет документа для проведения")
        return
    payload = {"telegram_user_id": cb.from_user.id, "chat_id": chat_id, "draft_id": draft_id}
    try:
        r = await _http.post("/agent/post", json=payload)
        if r.status_code in (404, 422):
            # 1С отказала с человекочитаемой причиной — показать её пользователю.
            reason = r.json().get("detail", "причина не указана")
            _created[chat_id] = draft_id  # вернуть — можно исправить в 1С и повторить
            await bot.send_message(chat_id, f"⚠️ 1С не провела документ: {reason}\n"
                                            "Документ остался черновиком.")
            await cb.answer()
            return
        r.raise_for_status()
        resp = r.json()
        await cb.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(chat_id, f"📮 Документ № {resp['doc_number']} проведён в 1С.")
    except Exception as e:  # noqa: BLE001 — ошибка проведения не должна ронять хендлер
        print(f"[post error] chat={chat_id}: {e!r}")
        _created[chat_id] = draft_id  # вернуть — пользователь сможет повторить
        await bot.send_message(chat_id, "Не удалось провести документ — он остался черновиком. "
                                        "Проверьте его в 1С или попробуйте ещё раз.")
    await cb.answer()


@dp.callback_query(F.data == "keep_draft")
async def on_keep_draft(cb: CallbackQuery) -> None:
    _created.pop(cb.message.chat.id, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Останется черновиком")


@dp.callback_query(F.data == "edit")
async def on_edit(cb: CallbackQuery) -> None:
    await cb.answer()
    await bot.send_message(cb.message.chat.id, "Напишите, что исправить (например: «дата 15 июля» "
                                               "или «контрагент другой»).")


@dp.callback_query(F.data == "cancel")
async def on_cancel(cb: CallbackQuery) -> None:
    chat_id = cb.message.chat.id
    _proposals.pop((chat_id, cb.message.message_id), None)
    if _last_card.get(chat_id) == cb.message.message_id:
        _last_card.pop(chat_id, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Отменено")


def main() -> None:
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
