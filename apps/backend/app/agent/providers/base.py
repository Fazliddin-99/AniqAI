"""Провайдер-нейтральное представление диалога и протокол LLM-провайдера.

Ядро агента (core.py) работает только с этими типами. Конкретный провайдер
(Claude / локальная модель через OpenAI-совместимый сервер) переводит их в свой
формат и обратно. Переключение — переменной окружения LLM_PROVIDER.
"""

from dataclasses import dataclass
from typing import Protocol


# --- Нейтральные блоки контента ---

@dataclass
class TextBlock:
    text: str


@dataclass
class ImageBlock:
    media_type: str  # image/jpeg, image/png
    data_b64: str


@dataclass
class DocumentBlock:
    data_b64: str
    media_type: str = "application/pdf"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool = False


ContentBlock = TextBlock | ImageBlock | DocumentBlock | ToolUseBlock | ToolResultBlock


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: list[ContentBlock]


@dataclass
class LlmResponse:
    stop_reason: str  # "end_turn" | "tool_use"
    content: list[ContentBlock]  # TextBlock и/или ToolUseBlock

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.content if isinstance(b, TextBlock)).strip()

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        return [b for b in self.content if isinstance(b, ToolUseBlock)]


class LlmProvider(Protocol):
    """Один метод: получить историю + инструменты, вернуть ответ модели."""

    def complete(
        self,
        *,
        system: str,
        tools: list[dict],
        messages: list[Message],
        max_tokens: int,
    ) -> LlmResponse: ...
