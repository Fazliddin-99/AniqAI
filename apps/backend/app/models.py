"""Контракты данных пайплайна: ЭСФ → решение о проводке → очередь ревью."""

from enum import Enum

from pydantic import BaseModel, Field


class EsfItem(BaseModel):
    """Позиция электронного счёта-фактуры (формат близок к Didox)."""

    name: str
    catalog_code: str = Field(description="ИКПУ — код из tasnif.soliq.uz")
    count: float
    price: float
    delivery_sum: float = Field(description="Сумма без НДС, сум")
    vat_rate: float
    vat_sum: float


class Esf(BaseModel):
    """Входящий ЭСФ."""

    factura_id: str
    factura_no: str
    factura_date: str
    seller_name: str
    seller_tin: str
    buyer_name: str
    buyer_tin: str
    items: list[EsfItem]


class PostingEntry(BaseModel):
    """Одна проводка: дебет/кредит по плану счетов НСБУ РУз."""

    debit: str
    credit: str
    amount: float
    description: str


class DecisionSource(str, Enum):
    RULE = "rule"
    LLM = "llm"


class Routing(str, Enum):
    AUTO = "auto"          # высокая уверенность — автопроводка
    REVIEW = "review"      # средняя — подтверждение в 1 клик
    ESCALATE = "escalate"  # низкая — эскалация с объяснением


class PostingDecision(BaseModel):
    entries: list[PostingEntry]
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    source: DecisionSource
    routing: Routing


class ReviewStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    AUTO_POSTED = "auto_posted"


class ReviewItem(BaseModel):
    id: str
    esf: Esf
    decision: PostingDecision
    status: ReviewStatus


class HistoricalPosting(BaseModel):
    """Историческая проводка из 1С — обучающий пример для классификатора."""

    seller_tin: str
    seller_name: str
    catalog_code: str
    item_name: str
    debit: str
    credit: str
    vat_debit: str | None = None
    comment: str = ""
