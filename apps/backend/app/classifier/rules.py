"""Слой 1 — детерминированные правила.

Если каждая позиция ЭСФ уже проводилась от этого же поставщика с этим же ИКПУ
на один и тот же счёт — повторяем историческую проводку без участия LLM.
"""

from ..history import exact_matches
from ..models import (
    DecisionSource,
    Esf,
    HistoricalPosting,
    PostingDecision,
    PostingEntry,
    Routing,
)


def classify_by_rules(esf: Esf, history: list[HistoricalPosting]) -> PostingDecision | None:
    entries: list[PostingEntry] = []
    matched_comments: list[str] = []

    for item in esf.items:
        matches = exact_matches(history, esf.seller_tin, item.catalog_code)
        if not matches:
            return None
        accounts = {(m.debit, m.credit, m.vat_debit) for m in matches}
        if len(accounts) != 1:
            # Поставщик проводил этот же ИКПУ по-разному — пусть решает LLM
            return None
        m = matches[0]
        entries.append(
            PostingEntry(
                debit=m.debit,
                credit=m.credit,
                amount=item.delivery_sum,
                description=f"{item.name} — по образцу прежних поставок {esf.seller_name}",
            )
        )
        if item.vat_sum > 0 and m.vat_debit:
            entries.append(
                PostingEntry(
                    debit=m.vat_debit,
                    credit=m.credit,
                    amount=item.vat_sum,
                    description=f"НДС {item.vat_rate:.0f}% по позиции «{item.name}»",
                )
            )
        matched_comments.append(f"«{item.name}» → Дт {m.debit} (совпадение поставщик+ИКПУ)")

    return PostingDecision(
        entries=entries,
        confidence=1.0,
        explanation="Точное совпадение с историей: " + "; ".join(matched_comments),
        source=DecisionSource.RULE,
        routing=Routing.AUTO,
    )
