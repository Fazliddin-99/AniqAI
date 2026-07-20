"""Ядро агента-приёмщика: диалоговый цикл tool use с сохранением истории по чату.

Не зависит от конкретной LLM — работает через провайдер (providers.get_provider).
Синхронный код — бот (async/aiogram) вызывает process_turn через asyncio.to_thread.
"""

import json
from dataclasses import dataclass, field
from typing import Literal

from copilot_shared import OperationDraft
from pydantic import ValidationError

from .onec_client import OnecClient
from .prompt import SYSTEM
from .providers import (
    DocumentBlock,
    ImageBlock,
    LlmProvider,
    Message,
    TextBlock,
    ToolResultBlock,
    get_provider,
)
from .tools import ALL_TOOLS

MAX_TOOL_ITERATIONS = 6


@dataclass
class Attachment:
    kind: Literal["image", "pdf"]
    media_type: str  # image/jpeg, image/png, application/pdf
    data_b64: str


@dataclass
class TurnResult:
    """Итог хода агента. Ровно одно из полей содержательно."""

    reply_text: str | None = None
    proposal: OperationDraft | None = None


@dataclass
class AgentSession:
    """История диалога одного чата. tenant — компания (база 1С); onec — её подключение."""

    tenant: str
    onec: OnecClient
    messages: list[Message] = field(default_factory=list)
    provider: LlmProvider = field(default_factory=get_provider)

    def _user_content(self, text: str, attachments: list[Attachment]) -> list:
        blocks: list = []
        for a in attachments:
            if a.kind == "image":
                blocks.append(ImageBlock(media_type=a.media_type, data_b64=a.data_b64))
            else:
                blocks.append(DocumentBlock(data_b64=a.data_b64))
        if text:
            blocks.append(TextBlock(text=text))
        if not blocks:
            blocks.append(TextBlock(text="(пустое сообщение)"))
        return blocks

    def _run_tool(self, name: str, tool_input: dict) -> tuple[str, bool, OperationDraft | None]:
        """Вернуть (текст результата, is_error, proposal|None)."""
        try:
            if name == "find_counterparty":
                res = self.onec.find_counterparties(
                    tin=tool_input.get("tin"), name=tool_input.get("name"))
                return json.dumps([c.model_dump() for c in res], ensure_ascii=False), False, None
            if name == "find_item":
                res = self.onec.find_items(query=tool_input.get("query", ""))
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
        self.messages.append(Message("user", self._user_content(text, attachments or [])))

        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self.provider.complete(
                system=SYSTEM, tools=ALL_TOOLS, messages=self.messages, max_tokens=4096)
            self.messages.append(Message("assistant", resp.content))

            if resp.stop_reason != "tool_use":
                return TurnResult(reply_text=resp.text or "…")

            tool_results: list = []
            proposal: OperationDraft | None = None
            for tu in resp.tool_uses:
                content, is_error, draft = self._run_tool(tu.name, tu.input)
                if draft is not None:
                    proposal = draft
                tool_results.append(ToolResultBlock(tu.id, content, is_error))
            self.messages.append(Message("user", tool_results))

            if proposal is not None:
                return TurnResult(proposal=proposal)

        return TurnResult(reply_text="Не удалось собрать операцию за несколько шагов. "
                                     "Уточните, пожалуйста, что нужно сделать.")

    def note_confirmation(self, draft_id: str) -> None:
        """Записать в историю факт подтверждения — чтобы follow-up имел контекст."""
        self.messages.append(Message("user", [TextBlock(
            f"[Система: пользователь подтвердил, в 1С создан черновик {draft_id}.]")]))
