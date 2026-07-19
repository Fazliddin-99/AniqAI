"""Провайдер Claude. Перевод нейтральных блоков ↔ формат Anthropic — чистые функции."""

import anthropic

from .base import (
    DocumentBlock,
    ImageBlock,
    LlmResponse,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

MODEL = "claude-opus-4-8"


def _block_to_anthropic(b) -> dict:
    if isinstance(b, TextBlock):
        return {"type": "text", "text": b.text}
    if isinstance(b, ImageBlock):
        return {"type": "image",
                "source": {"type": "base64", "media_type": b.media_type, "data": b.data_b64}}
    if isinstance(b, DocumentBlock):
        return {"type": "document",
                "source": {"type": "base64", "media_type": b.media_type, "data": b.data_b64}}
    if isinstance(b, ToolUseBlock):
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    if isinstance(b, ToolResultBlock):
        return {"type": "tool_result", "tool_use_id": b.tool_use_id,
                "content": b.content, "is_error": b.is_error}
    raise TypeError(f"неизвестный блок: {b!r}")


def to_anthropic_messages(messages: list[Message]) -> list[dict]:
    return [{"role": m.role, "content": [_block_to_anthropic(b) for b in m.content]}
            for m in messages]


class AnthropicProvider:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic()

    def complete(self, *, system, tools, messages, max_tokens) -> LlmResponse:
        resp = self._client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            tools=tools,
            messages=to_anthropic_messages(messages),
        )
        content = []
        for b in resp.content:
            if b.type == "text":
                content.append(TextBlock(b.text))
            elif b.type == "tool_use":
                content.append(ToolUseBlock(b.id, b.name, b.input))
        stop = "tool_use" if resp.stop_reason == "tool_use" else "end_turn"
        return LlmResponse(stop_reason=stop, content=content)
