"""Буферизация сообщений чата.

Пользователи присылают документ несколькими сообщениями подряд («фото → фото →
подпись», альбом, инструкция вдогонку). Копим входящие по чату в окне debounce и
передаём агенту одной репликой. Логика агрегации — чистая и тестируемая; таймер —
тонкая обёртка на asyncio.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class Attachment:
    kind: str          # "image" | "pdf"
    media_type: str
    data_b64: str


@dataclass
class PendingTurn:
    """Накопленные сообщения одного чата до сброса агенту."""

    texts: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)

    def add_text(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.texts.append(text)

    def add_attachment(self, att: Attachment) -> None:
        self.attachments.append(att)

    def build(self) -> tuple[str, list[Attachment]]:
        """Собрать реплику: тексты через перевод строки, вложения в порядке прихода."""
        return "\n".join(self.texts), list(self.attachments)

    def is_empty(self) -> bool:
        return not self.texts and not self.attachments


class ChatBuffer:
    """Per-chat debounce: после последнего сообщения ждёт `delay` секунд, затем flush."""

    def __init__(
        self,
        on_flush: Callable[[int, str, list[Attachment]], Awaitable[None]],
        delay: float = 2.5,
    ) -> None:
        self._on_flush = on_flush
        self._delay = delay
        self._pending: dict[int, PendingTurn] = {}
        self._timers: dict[int, asyncio.Task] = {}

    def add_text(self, chat_id: int, text: str) -> None:
        self._pending.setdefault(chat_id, PendingTurn()).add_text(text)
        self._arm(chat_id)

    def add_attachment(self, chat_id: int, att: Attachment) -> None:
        self._pending.setdefault(chat_id, PendingTurn()).add_attachment(att)
        self._arm(chat_id)

    def _arm(self, chat_id: int) -> None:
        if (t := self._timers.get(chat_id)) is not None:
            t.cancel()
        self._timers[chat_id] = asyncio.create_task(self._wait_and_flush(chat_id))

    async def _wait_and_flush(self, chat_id: int) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        pending = self._pending.pop(chat_id, None)
        self._timers.pop(chat_id, None)
        if pending is None or pending.is_empty():
            return
        text, attachments = pending.build()
        await self._on_flush(chat_id, text, attachments)
