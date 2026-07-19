"""Оркестрация: ЭСФ → правила → LLM → маршрутизация по confidence."""

import uuid

from .classifier.llm import classify_by_llm
from .classifier.rules import classify_by_rules
from .models import (
    Esf,
    HistoricalPosting,
    PostingDecision,
    ReviewItem,
    ReviewStatus,
    Routing,
)

_ROUTING_TO_STATUS = {
    Routing.AUTO: ReviewStatus.AUTO_POSTED,
    Routing.REVIEW: ReviewStatus.PENDING,
    Routing.ESCALATE: ReviewStatus.PENDING,
}


def classify(esf: Esf, history: list[HistoricalPosting]) -> PostingDecision:
    decision = classify_by_rules(esf, history)
    if decision is not None:
        return decision
    return classify_by_llm(esf, history)


def process(esf: Esf, history: list[HistoricalPosting]) -> ReviewItem:
    decision = classify(esf, history)
    return ReviewItem(
        id=uuid.uuid4().hex[:12],
        esf=esf,
        decision=decision,
        status=_ROUTING_TO_STATUS[decision.routing],
    )
