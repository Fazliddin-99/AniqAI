"""Контракт хозяйственной операции — то, что агент собирает и отправляет в 1С.

Один источник правды для бота, ядра агента (input_schema tool'а create_operation)
и мока 1С. Схема намеренно закрытая: OperationType — enum, поэтому классификация
физически ограничена возможностями v1.
"""

from enum import Enum

from pydantic import BaseModel, Field


class OperationType(str, Enum):
    """Типы операций, которые бот умеет заводить в v1. Всё вне списка — не поддержано."""

    GOODS_RECEIPT = "goods_receipt"      # поступление товаров/услуг (входящий СФ, накладная)
    SALES_INVOICE = "sales_invoice"      # реализация (исходящий счёт)
    EXPENSE_RECEIPT = "expense_receipt"  # чек/квитанция, подотчёт
    PAYMENT_ORDER = "payment_order"      # платёжное поручение (исходящее)


class PartyRef(BaseModel):
    """Контрагент. ref_1c заполняется, если find_counterparty нашёл его в базе."""

    name: str = Field(description="Наименование контрагента")
    tin: str | None = Field(default=None, description="ИНН/СТИР (9 цифр) или ПИНФЛ")
    ref_1c: str | None = Field(default=None, description="Код/GUID в справочнике 1С")


class OperationItem(BaseModel):
    """Позиция документа."""

    name: str
    ikpu: str | None = Field(default=None, description="ИКПУ — код tasnif.soliq.uz, 17 цифр")
    qty: float = 1.0
    price: float = Field(default=0.0, description="Цена за единицу, сум")
    sum: float = Field(description="Сумма без НДС, сум")
    vat_rate: float = Field(default=12.0, description="Ставка НДС, %")
    vat_sum: float = 0.0
    item_ref_1c: str | None = Field(default=None, description="Код номенклатуры в 1С")


class Totals(BaseModel):
    sum: float = Field(description="Итого без НДС, сум")
    vat_sum: float = 0.0


class OperationDraft(BaseModel):
    """Собранная операция — вход tool'а create_operation и тело POST /operations."""

    operation_type: OperationType
    confidence: float = Field(ge=0.0, le=1.0, description="Уверенность классификации, 0..1")
    counterparty: PartyRef
    doc_number: str | None = Field(default=None, description="Номер первичного документа")
    doc_date: str | None = Field(default=None, description="Дата документа, ГГГГ-ММ-ДД")
    items: list[OperationItem] = Field(default_factory=list)
    totals: Totals
    user_comment: str = Field(default="", description="Свободный комментарий пользователя")
    explanation: str = Field(description="Почему выбран этот тип операции, по-русски")

    # Проставляется ботом, не моделью — идемпотентность и трассировка источника.
    external_id: str | None = None
    source_channel: str = "telegram"
