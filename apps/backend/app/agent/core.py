"""Ядро агента-приёмщика: диалоговый цикл tool use с сохранением истории по чату.

Не зависит от конкретной LLM — работает через провайдер (providers.get_provider).
Синхронный код — бот (async/aiogram) вызывает process_turn через asyncio.to_thread.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from copilot_shared import OperationDraft
from pydantic import ValidationError

from . import charts
from .onec_client import OnecClient
from .prompt import SYSTEM
from .providers import (
    DocumentBlock,
    ImageBlock,
    LlmProvider,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    get_provider,
)
from .tools import ALL_TOOLS

# Аналитический ход длиннее документного: обзор продаж + два разреза + график
# + запас на повторы. Документные ходы укладываются с запасом.
MAX_TOOL_ITERATIONS = 10


@dataclass
class Attachment:
    kind: Literal["image", "pdf"]
    media_type: str  # image/jpeg, image/png, application/pdf
    data_b64: str


@dataclass
class TurnResult:
    """Итог хода агента. reply_text|proposal взаимоисключающие; images (PNG)
    сопровождают reply_text, когда агент построил графики."""

    reply_text: str | None = None
    proposal: OperationDraft | None = None
    images: list[bytes] = field(default_factory=list)


@dataclass
class AgentSession:
    """История диалога одного чата. tenant — компания (база 1С); onec — её подключение."""

    tenant: str
    onec: OnecClient
    messages: list[Message] = field(default_factory=list)
    provider: LlmProvider = field(default_factory=get_provider)
    _charts: list[bytes] = field(default_factory=list)  # PNG текущего хода
    # Ходы одной сессии строго последовательны: параллельные /agent/turn на один чат
    # перемешивали self.messages и ломали пары tool_use/tool_result (инцидент 15.08.2026).
    _turn_lock: threading.Lock = field(default_factory=threading.Lock)

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
            if name == "get_account_report":
                rep = self.onec.get_account_report(
                    account=tool_input.get("account", ""),
                    date_from=tool_input.get("date_from", ""),
                    date_to=tool_input.get("date_to", ""),
                    group_by=tool_input.get("group_by"),
                    limit=tool_input.get("limit"))
                return rep.model_dump_json(), False, None
            if name == "get_sales_report":
                rep = self.onec.get_sales_report(
                    date_from=tool_input.get("date_from", ""),
                    date_to=tool_input.get("date_to", ""),
                    granularity=tool_input.get("granularity"),
                    dimension=tool_input.get("dimension"),
                    limit=tool_input.get("limit"))
                return rep.model_dump_json(), False, None
            if name == "get_cash_report":
                rep = self.onec.get_cash_report(date=tool_input.get("date"))
                return rep.model_dump_json(), False, None
            if name == "render_chart":
                png = charts.render(charts.ChartSpec.model_validate(tool_input))
                self._charts.append(png)
                return "График построен и будет отправлен пользователю вместе с ответом.", False, None
            if name == "find_warehouse":
                try:
                    res = self.onec.find_warehouses(query=tool_input.get("query", ""))
                except Exception:  # noqa: BLE001 — эндпоинт мог быть ещё не задеплоен в 1С
                    return ("Список складов недоступен — оставь warehouse_ref пустым, "
                            "1С подставит склад по умолчанию."), False, None
                return json.dumps([w.model_dump() for w in res], ensure_ascii=False), False, None
            if name == "find_employee":
                res = self.onec.find_employees(query=tool_input.get("query", ""))
                if not res:
                    # Явная подсказка: физлиц создавать нельзя, обходного пути нет (ТЗ §5.3.1).
                    return ("Сотрудник не найден. Создавать физлиц нельзя — уточни ФИО "
                            "у пользователя или сообщи, что такого подотчётника нет в базе."), False, None
                return json.dumps([e.model_dump() for e in res], ensure_ascii=False), False, None
            if name == "create_operation":
                draft = OperationDraft.model_validate(tool_input)
                # Жёсткая проверка склада (требование пользователя): при нескольких
                # складах промпту недостаточно доверия — принудительно возвращаем агента
                # спросить пользователя, иначе документ уйдёт с пустым складом.
                has_goods = any(it.kind.value == "goods" for it in draft.items)
                if has_goods and draft.warehouse_ref is None:
                    try:
                        ws = self.onec.find_warehouses()
                    except Exception:  # noqa: BLE001 — эндпоинта может не быть, тогда фолбэк 1С
                        ws = []
                    if len(ws) > 1:
                        listing = "; ".join(f"{w.name} ({w.ref_1c})" for w in ws[:15])
                        return ("Операция НЕ создана: складов в базе несколько, а warehouse_ref "
                                "пуст. Спроси у пользователя, на какой склад принять, и повтори "
                                f"create_operation с выбранным GUID. Склады: {listing}"), True, None
                return "Операция собрана и показана пользователю на подтверждение.", False, draft
        except ValidationError as e:
            return f"Ошибка валидации операции, исправь поля: {e}", True, None
        except Exception as e:  # noqa: BLE001 — вернуть модели, а не падать
            return f"Ошибка при обращении к 1С: {e}", True, None
        return f"Неизвестный инструмент: {name}", True, None

    def _repair_history(self) -> None:
        """Закрыть незакрытые tool_use синтетическими tool_result.

        История могла оборваться между append'ами (гонка, max_tokens, исключение) —
        Anthropic отвергает всю сессию 400-й, если после assistant с tool_use нет
        парных tool_result. Чиним на входе каждого хода, а не падаем навсегда.
        """
        repaired: list[Message] = []
        for idx, m in enumerate(self.messages):
            repaired.append(m)
            if m.role != "assistant":
                continue
            tu_ids = [b.id for b in m.content if isinstance(b, ToolUseBlock)]
            if not tu_ids:
                continue
            nxt = self.messages[idx + 1] if idx + 1 < len(self.messages) else None
            answered: set[str] = set()
            if nxt is not None and nxt.role == "user":
                answered = {b.tool_use_id for b in nxt.content
                            if isinstance(b, ToolResultBlock)}
            missing = [t for t in tu_ids if t not in answered]
            if not missing:
                continue
            stubs = [ToolResultBlock(t, "[прервано: результат не получен]", True)
                     for t in missing]
            if answered:  # частично отвеченное сообщение — дополнить его
                nxt.content = stubs + nxt.content
            else:         # вставить недостающий ответ отдельным сообщением
                repaired.append(Message("user", stubs))
        self.messages = repaired

    def process_turn(self, text: str, attachments: list[Attachment] | None = None) -> TurnResult:
        with self._turn_lock:
            return self._process_turn(text, attachments)

    def _process_turn(self, text: str, attachments: list[Attachment] | None) -> TurnResult:
        self._repair_history()
        self.messages.append(Message("user", self._user_content(text, attachments or [])))
        self._charts = []
        # Аналитика относительна дате («в этом месяце») — модель не должна гадать.
        system = SYSTEM + f"\nСегодня: {date.today().isoformat()}."

        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self.provider.complete(
                system=system, tools=ALL_TOOLS, messages=self.messages, max_tokens=4096)
            self.messages.append(Message("assistant", resp.content))

            # Ориентируемся на фактические tool_use, а не на stop_reason: при
            # stop_reason=max_tokens в контенте могут быть целые tool_use, и вернуть
            # ответ, не исполнив их, значит оставить историю с незакрытыми парами.
            if not resp.tool_uses:
                return TurnResult(reply_text=resp.text or "…", images=self._charts)

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

        return TurnResult(reply_text="Не удалось собрать ответ за несколько шагов. "
                                     "Уточните, пожалуйста, что нужно сделать.",
                          images=self._charts)

    def note_confirmation(self, draft_id: str) -> None:
        """Записать в историю факт подтверждения — чтобы follow-up имел контекст."""
        self.messages.append(Message("user", [TextBlock(
            f"[Система: пользователь подтвердил, в 1С создан черновик {draft_id}.]")]))

    def note_posting(self, draft_id: str) -> None:
        """Записать в историю факт проведения документа пользователем."""
        self.messages.append(Message("user", [TextBlock(
            f"[Система: пользователь нажал «Провести», документ {draft_id} проведён в 1С.]")]))
