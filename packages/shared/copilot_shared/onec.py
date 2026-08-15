"""Модели ответов API 1С (`/hs/copilot/v1`). Общие для мока и HTTP-клиента."""

from enum import Enum

from pydantic import BaseModel


class Counterparty(BaseModel):
    ref_1c: str
    name: str
    tin: str | None = None


class ItemRef(BaseModel):
    ref_1c: str
    name: str
    ikpu: str | None = None
    unit: str = "шт"


class Employee(BaseModel):
    """Физлицо-подотчётник. Только для чтения — в 1С не создаётся (ТЗ §5.3.1)."""

    ref_1c: str
    name: str
    position: str | None = None


class OperationStatus(str, Enum):
    DRAFT = "draft"        # черновик создан, не проведён
    POSTED = "posted"      # проведён бухгалтером в 1С
    REJECTED = "rejected"


class Warehouse(BaseModel):
    """Склад. Только для чтения — выбор при нескольких складах в базе (§4.6)."""

    ref_1c: str
    name: str


class RelatedDoc(BaseModel):
    """Сопутствующий документ пары (ТЗ §5.6). Пока это только поступление под ГТД."""

    draft_id: str
    doc_type_1c: str
    doc_number: str
    status: OperationStatus = OperationStatus.DRAFT


class CreateOperationResponse(BaseModel):
    draft_id: str
    doc_type_1c: str = "Поступление товаров и услуг"
    doc_number: str
    status: OperationStatus = OperationStatus.DRAFT
    idempotent_hit: bool = False  # true — вернули существующий черновик, дубль не создан
    related_docs: list[RelatedDoc] = []
