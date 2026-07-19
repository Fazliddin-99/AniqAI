"""Провайдер для локальной модели через OpenAI-совместимый сервер (vLLM / Ollama).

Добавлен по явному запросу — путь к локальной LLM без облака. Рекомендуемая модель:
Qwen2.5-VL (32B/72B) — зрение + tool calling + приличный русский. Запуск, например:
    vllm serve Qwen/Qwen2.5-VL-32B-Instruct --port 8001
    LLM_PROVIDER=openai LOCAL_LLM_URL=http://localhost:8001/v1 \
    LOCAL_LLM_MODEL=Qwen/Qwen2.5-VL-32B-Instruct uv run uvicorn app.main:app

Ограничение: PDF локальные vision-модели напрямую не читают — их нужно рендерить
в изображения постранично (пока не реализовано). Картинки поддерживаются.
"""

import json
import os

from .base import (
    DocumentBlock,
    ImageBlock,
    LlmResponse,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


def to_openai_messages(system: str, messages: list[Message]) -> list[dict]:
    """Нейтральная история → формат OpenAI chat.

    tool_result-блоки становятся отдельными сообщениями role=tool (так требует
    OpenAI API), поэтому одно нейтральное сообщение может дать несколько.
    """
    out: list[dict] = [{"role": "system", "content": system}]

    for m in messages:
        tool_results = [b for b in m.content if isinstance(b, ToolResultBlock)]
        other = [b for b in m.content if not isinstance(b, ToolResultBlock)]

        if m.role == "assistant":
            text = "\n".join(b.text for b in other if isinstance(b, TextBlock))
            tool_calls = [
                {"id": b.id, "type": "function",
                 "function": {"name": b.name, "arguments": json.dumps(b.input, ensure_ascii=False)}}
                for b in other if isinstance(b, ToolUseBlock)
            ]
            msg: dict = {"role": "assistant", "content": text or None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
            continue

        # role == user
        if other:
            parts: list[dict] = []
            for b in other:
                if isinstance(b, TextBlock):
                    parts.append({"type": "text", "text": b.text})
                elif isinstance(b, ImageBlock):
                    parts.append({"type": "image_url",
                                  "image_url": {"url": f"data:{b.media_type};base64,{b.data_b64}"}})
                elif isinstance(b, DocumentBlock):
                    raise NotImplementedError(
                        "PDF пока не поддержан локальным провайдером — нужен рендер страниц "
                        "в изображения. Пришлите документ как фото или используйте Claude.")
            out.append({"role": "user", "content": parts})
        for tr in tool_results:
            out.append({"role": "tool", "tool_call_id": tr.tool_use_id, "content": tr.content})

    return out


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["input_schema"]}}
            for t in tools]


class OpenAIProvider:
    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Для локального провайдера установите: uv add openai") from e
        self._client = OpenAI(
            base_url=os.environ.get("LOCAL_LLM_URL", "http://localhost:8001/v1"),
            api_key=os.environ.get("LOCAL_LLM_KEY", "not-needed"),
        )
        self._model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-VL-32B-Instruct")

    def complete(self, *, system, tools, messages, max_tokens) -> LlmResponse:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=to_openai_messages(system, messages),
            tools=to_openai_tools(tools),
        )
        choice = resp.choices[0]
        content = []
        if choice.message.content:
            content.append(TextBlock(choice.message.content))
        for tc in (choice.message.tool_calls or []):
            content.append(ToolUseBlock(tc.id, tc.function.name, json.loads(tc.function.arguments)))
        stop = "tool_use" if choice.message.tool_calls else "end_turn"
        return LlmResponse(stop_reason=stop, content=content)
