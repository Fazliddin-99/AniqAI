"""Слой 2 — Claude с few-shot из исторических проводок этой компании."""

import anthropic
from pydantic import BaseModel, Field

from ..history import similar
from ..models import (
    DecisionSource,
    Esf,
    HistoricalPosting,
    PostingDecision,
    PostingEntry,
    Routing,
)

MODEL = "claude-opus-4-8"

SYSTEM = """\
Ты — ассистент бухгалтера в Узбекистане. Твоя задача — определить бухгалтерские
проводки для входящего ЭСФ (электронного счёта-фактуры) по плану счетов НСБУ РУз.

Правила:
- Опирайся в первую очередь на исторические проводки этой компании (few-shot примеры
  ниже): если похожие позиции от этого поставщика уже проводились на определённый счёт,
  используй его.
- Типовая схема для входящего ЭСФ: Дт счёта запасов/затрат (1010 материалы, 2910 товары,
  9420 и т.п.) — Кт 6010 «Счета к оплате поставщикам»; НДС к зачёту — отдельной проводкой
  Дт 4410 — Кт 6010.
- confidence: 0.9+ только если исторические примеры прямо подтверждают выбор счёта;
  0.6–0.9 если выбор следует из типовой схемы и характера товара; ниже 0.6 если данных
  недостаточно или позиции неоднозначны.
- explanation пиши по-русски, коротко и предметно: почему выбран именно этот счёт,
  со ссылкой на примеры («похожие позиции этого поставщика проводились на 1010»).
"""


class LlmEntry(BaseModel):
    debit: str = Field(description="Счёт дебета, план счетов НСБУ РУз")
    credit: str = Field(description="Счёт кредита")
    amount: float = Field(description="Сумма в сумах")
    description: str


class LlmClassification(BaseModel):
    entries: list[LlmEntry]
    confidence: float = Field(description="0..1, честная оценка уверенности")
    explanation: str


def _format_history(examples: list[HistoricalPosting]) -> str:
    if not examples:
        return "(исторических примеров по этому поставщику/товарной группе нет)"
    lines = [
        f"- {p.seller_name} (ИНН {p.seller_tin}), ИКПУ {p.catalog_code}, "
        f"«{p.item_name}»: Дт {p.debit} Кт {p.credit}"
        + (f", НДС Дт {p.vat_debit}" if p.vat_debit else "")
        + (f" — {p.comment}" if p.comment else "")
        for p in examples
    ]
    return "\n".join(lines)


def _format_esf(esf: Esf) -> str:
    items = "\n".join(
        f"- «{i.name}», ИКПУ {i.catalog_code}, кол-во {i.count}, "
        f"сумма без НДС {i.delivery_sum:,.0f} сум, НДС {i.vat_rate:.0f}% = {i.vat_sum:,.0f} сум"
        for i in esf.items
    )
    return (
        f"ЭСФ № {esf.factura_no} от {esf.factura_date}\n"
        f"Поставщик: {esf.seller_name} (ИНН {esf.seller_tin})\n"
        f"Покупатель: {esf.buyer_name} (ИНН {esf.buyer_tin})\n"
        f"Позиции:\n{items}"
    )


def classify_by_llm(esf: Esf, history: list[HistoricalPosting]) -> PostingDecision:
    client = anthropic.Anthropic()

    examples: list[HistoricalPosting] = []
    for item in esf.items:
        for p in similar(history, esf.seller_tin, item.catalog_code, limit=5):
            if p not in examples:
                examples.append(p)

    prompt = (
        f"Исторические проводки компании:\n{_format_history(examples)}\n\n"
        f"Определи проводки для этого ЭСФ:\n{_format_esf(esf)}"
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=LlmClassification,
    )
    result = response.parsed_output

    if result.confidence >= 0.9:
        routing = Routing.AUTO
    elif result.confidence >= 0.6:
        routing = Routing.REVIEW
    else:
        routing = Routing.ESCALATE

    return PostingDecision(
        entries=[PostingEntry(**e.model_dump()) for e in result.entries],
        confidence=result.confidence,
        explanation=result.explanation,
        source=DecisionSource.LLM,
        routing=routing,
    )
