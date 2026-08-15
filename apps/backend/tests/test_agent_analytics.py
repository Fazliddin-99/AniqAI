"""Аналитические ветки ядра агента: отчёты в контекст, график в images,
ошибка 1С — в is_error tool result, а не исключение."""

from copilot_shared import CashAccount, CashReport

from app.agent.core import AgentSession
from app.agent.providers.base import (
    LlmResponse,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

PNG_MAGIC = b"\x89PNG"


class ScriptedProvider:
    """Отдаёт заранее заданные ответы модели по очереди."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    def complete(self, *, system, tools, messages, max_tokens):
        self.calls.append(list(messages))
        return self._responses.pop(0)


class StubOnec:
    def get_cash_report(self, date=None):
        return CashReport(date="2026-08-14", total_uzs=100.0, accounts=[
            CashAccount(kind="cash", name="Касса", account="5010",
                        balance=100.0, balance_uzs=100.0)])

    def get_sales_report(self, **kw):
        raise RuntimeError("1С недоступна")


def _tool_use(name, inp, tid="t1"):
    return LlmResponse(stop_reason="tool_use",
                       content=[ToolUseBlock(id=tid, name=name, input=inp)])


def _final(text):
    return LlmResponse(stop_reason="end_turn", content=[TextBlock(text=text)])


def test_report_result_lands_in_context_and_reply():
    provider = ScriptedProvider([
        _tool_use("get_cash_report", {}),
        _final("В кассе 100 сум (по данным 1С на 14.08.2026)."),
    ])
    s = AgentSession(tenant="t", onec=StubOnec(), provider=provider)
    result = s.process_turn("сколько денег в кассе?")
    assert "100" in result.reply_text
    # Результат отчёта попал в контекст вторым вызовом модели.
    last_messages = provider.calls[-1]
    dump = str([getattr(b, "content", b) for m in last_messages for b in m.content])
    assert "total_uzs" in dump


def test_render_chart_produces_image():
    spec = {"chart_type": "line", "title": "Динамика",
            "x_labels": ["июнь", "июль"],
            "series": [{"name": "Выручка", "values": [480.0, 290.0]}]}
    provider = ScriptedProvider([
        _tool_use("render_chart", spec),
        _final("Продажи упали в июле."),
    ])
    s = AgentSession(tenant="t", onec=StubOnec(), provider=provider)
    result = s.process_turn("покажи динамику")
    assert len(result.images) == 1
    assert result.images[0].startswith(PNG_MAGIC)


def test_onec_error_becomes_tool_error_not_exception():
    provider = ScriptedProvider([
        _tool_use("get_sales_report", {"date_from": "2026-01-01", "date_to": "2026-06-30"}),
        _final("Не удалось получить данные из 1С."),
    ])
    s = AgentSession(tenant="t", onec=StubOnec(), provider=provider)
    result = s.process_turn("почему продажи упали?")  # не должно бросить
    assert result.reply_text
    dump = str([getattr(b, "content", b) for m in provider.calls[-1] for b in m.content])
    assert "Ошибка при обращении к 1С" in dump


def test_charts_reset_between_turns():
    spec = {"chart_type": "bar", "title": "t", "x_labels": ["a"],
            "series": [{"name": "s", "values": [1.0]}]}
    provider = ScriptedProvider([
        _tool_use("render_chart", spec),
        _final("график"),
        _final("просто текст"),
    ])
    s = AgentSession(tenant="t", onec=StubOnec(), provider=provider)
    first = s.process_turn("нарисуй")
    second = s.process_turn("а теперь просто ответь")
    assert len(first.images) == 1
    assert second.images == []


def test_repair_history_closes_orphan_tool_use():
    """Испорченная гонкой история (tool_use без tool_result) чинится на входе хода."""
    provider = ScriptedProvider([_final("ок")])
    s = AgentSession(tenant="t", onec=StubOnec(), provider=provider)
    # Симуляция гонки: assistant с tool_use, следом ЧУЖОЙ user-текст без tool_result.
    s.messages = [
        Message("user", [TextBlock(text="вопрос 1")]),
        Message("assistant", [ToolUseBlock(id="tu_lost", name="get_cash_report", input={})]),
        Message("user", [TextBlock(text="вопрос 2, влезший параллельно")]),
    ]
    result = s.process_turn("а теперь ответь")
    assert result.reply_text == "ок"
    sent = provider.calls[-1]
    # Между assistant(tool_use) и текстом должен появиться синтетический tool_result.
    tr = [b for m in sent for b in m.content
          if isinstance(b, ToolResultBlock) and b.tool_use_id == "tu_lost"]
    assert len(tr) == 1 and tr[0].is_error


def test_max_tokens_with_tool_uses_still_runs_tools():
    """stop_reason=max_tokens с целыми tool_use: инструменты исполняются, пары закрыты."""
    provider = ScriptedProvider([
        LlmResponse(stop_reason="max_tokens",
                    content=[ToolUseBlock(id="t9", name="get_cash_report", input={})]),
        _final("готово"),
    ])
    s = AgentSession(tenant="t", onec=StubOnec(), provider=provider)
    result = s.process_turn("сколько денег?")
    assert result.reply_text == "готово"
    sent = provider.calls[-1]
    assert any(isinstance(b, ToolResultBlock) and b.tool_use_id == "t9"
               for m in sent for b in m.content)


def test_concurrent_turns_serialized():
    """Параллельные ходы одной сессии не перемешивают историю (threading.Lock)."""
    import threading as th

    provider = ScriptedProvider([_final("один"), _final("два")])
    s = AgentSession(tenant="t", onec=StubOnec(), provider=provider)
    errors = []

    def run(txt):
        try:
            s.process_turn(txt)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1, t2 = th.Thread(target=run, args=("a",)), th.Thread(target=run, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert not errors
    # Строгая последовательность: user, assistant, user, assistant.
    roles = [m.role for m in s.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
