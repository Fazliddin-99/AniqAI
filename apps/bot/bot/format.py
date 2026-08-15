"""Преобразование Markdown-текста агента в безопасный Telegram-HTML.

Telegram-«Markdown» ломается на произвольном контенте (незакрытые *, _ в названиях),
поэтому шлём parse_mode=HTML: сначала экранируем ВЕСЬ текст, затем переводим
ограниченное подмножество Markdown в теги. Всё, что не распознали, остаётся
видимым текстом — сообщение не может «не отправиться» из-за разметки.
"""

import html
import re

_CODE_BLOCK = re.compile(r"```[a-zA-Z]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_HEADER = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def md_to_html(text: str) -> str:
    """Markdown агента → Telegram-HTML. Безопасно для любого содержимого."""
    out = html.escape(text or "", quote=False)
    out = _CODE_BLOCK.sub(lambda m: f"<pre>{m.group(1).rstrip()}</pre>", out)
    out = _INLINE_CODE.sub(r"<code>\1</code>", out)
    out = _BOLD.sub(r"<b>\1</b>", out)
    out = _HEADER.sub(r"<b>\1</b>", out)
    return out
