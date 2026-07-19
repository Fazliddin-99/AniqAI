"""Фабрика LLM-провайдера. LLM_PROVIDER=anthropic (по умолчанию) | openai."""

import os

from .base import (
    DocumentBlock,
    ImageBlock,
    LlmProvider,
    LlmResponse,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

__all__ = [
    "get_provider",
    "LlmProvider",
    "LlmResponse",
    "Message",
    "TextBlock",
    "ImageBlock",
    "DocumentBlock",
    "ToolUseBlock",
    "ToolResultBlock",
]


def get_provider() -> LlmProvider:
    name = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if name in ("openai", "local", "vllm", "ollama"):
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    raise ValueError(f"неизвестный LLM_PROVIDER: {name!r} (ожидается anthropic|openai)")
