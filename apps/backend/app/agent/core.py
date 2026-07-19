"""Ядро агента-приёмщика: диалоговый цикл tool use с сохранением истории по чату.

Синхронный код — бот (async/aiogram) вызывает process_turn через asyncio.to_thread.
"""

import json
from dataclasses import dataclass, field
from typing import Literal

import anthropic
from copilot_shared import OperationDraft
from pydantic import ValidationError

from . import onec_client
from .prompt import SYSTEM
from .tools import ALL_TOOLS

MODEL = "claude-opus-4-8"
MAX_TOOL_ITERATIONS = 6


@dataclass
class Attachment:
    kind: Literal["image", "pdf"]
    media_type: str  # image/jpeg, image/png, application/pdf
    data_b64: str


@dataclass
class TurnResult:
    """Итог хода агента. Ровно одно из полей содержательно."""

    reply_text: str | None = None          # вопрос / отказ / инфо — отправить пользователю
    proposal: OperationDraft | None = None  # если задано — бот рисует карточку подтверждения


@dataclass
class AgentSession:
    """История диалога одного чата. tenant — компания (база 1С)."""

    tenant: str
    messages: list[dict] = field(default_factory=list)
    _client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic)

    def _user_content(self, text: str, attachments: list[Attachment]) -> list[dict]:
        blocks: list[dict] = []
        for a in attachments:
            if a.kind == "image":
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": a.media_type, "data": a.data_b64},
                })
            else:
                blocks.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": a.data_b64},
                })
        if text:
            blocks.append({"type": "text", "text": text})
        if not blocks:
            blocks.append({"type": "text", "text": "(пустое сообщение)"})
        return blocks

    def _run_tool(self, name: str, tool_input: dict) -> tuple[str, bool, OperationDraft | None]:
        """Вернуть (текст результата, is_error, proposal|None)."""
        try:
            if name == "find_counterparty":
                res = onec_client.find_counterparties(
                    tin=tool_input.get("tin"), name=tool_input.get("name"))
                return json.dumps([c.model_dump() for c in res], ensure_ascii=False), False, None
            if name == "find_item":
                res = onec_client.find_items(query=tool_input.get("query", ""))
                return json.dumps([i.model_dump() for i in res], ensure_ascii=False), False, None
            if name == "create_operation":
                draft = OperationDraft.model_validate(tool_input)
                return "Операция собрана и показана пользователю на подтверждение.", False, draft
        except ValidationError as e:
            return f"Ошибка валидации операции, исправь поля: {e}", True, None
        except Exception as e:  # noqa: BLE001 — вернуть модели, а не падать
            return f"Ошибка при обращении к 1С: {e}", True, None
        return f"Неизвестный инструмент: {name}", True, None

    def process_turn(self, text: str, attachments: list[Attachment] | None = None) -> TurnResult:
        self.messages.append({"role": "user", "content": self._user_content(text, attachments or [])})

        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self._client.messages.create(
                model=MODEL,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=SYSTEM,
                tools=ALL_TOOLS,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                text_out = "\n".join(b.text for b in resp.content if b.type == "text").strip()
                return TurnResult(reply_text=text_out or "…")

            tool_results = []
            proposal: OperationDraft | None = None
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                content, is_error, draft = self._run_tool(block.name, block.input)
                if draft is not None:
                    proposal = draft
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                })
            self.messages.append({"role": "user", "content": tool_results})

            if proposal is not None:
                return TurnResult(proposal=proposal)

        return TurnResult(reply_text="Не удалось собрать операцию за несколько шагов. "
                                     "Уточните, пожалуйста, что нужно сделать.")

    def note_confirmation(self, draft_id: str) -> None:
        """Записать в историю факт подтверждения — чтобы follow-up имел контекст."""
        self.messages.append({
            "role": "user",
            "content": [{"type": "text", "text": f"[Система: пользователь подтвердил, "
                                                 f"в 1С создан черновик {draft_id}.]"}],
        })
