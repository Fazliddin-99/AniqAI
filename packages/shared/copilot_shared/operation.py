"""Контракт хозяйственной операции — то, что агент собирает и отправляет в 1С.

Один источник правды для бота, ядра агента (input_schema tool'а create_operation)
и мока 1С. Схема намеренно закрытая: OperationType — enum, поэтому классификация
физически ограничена возможностями v1.
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class OperationType(str, Enum):
    """Типы операций, которые бот умеет заводить в v1. Всё вне списка — не поддержано."""

    GOODS_RECEIPT = "goods_receipt"              # поступление товаров/услуг (входящий СФ, накладная)
    SALES_INVOICE = "sales_invoice"              # реализация (исходящий счёт)
    EXPENSE_RECEIPT = "expense_receipt"          # чек подотчётного лица → Авансовый отчёт
    PAYMENT_ORDER = "payment_order"              # платёжное поручение (исходящее)
    CUSTOMS_DECLARATION = "customs_declaration"  # ГТД по импорту (+ поступление, парой)


class ItemKind(str, Enum):
    """Вид позиции. Определяет табличную часть документа: Товары или Услуги/Прочее."""

    GOODS = "goods"
    SERVICE = "service"


class PartyRef(BaseModel):
    """Контрагент. ref_1c заполняется, если find_counterparty нашёл его в базе."""

    name: str = Field(description="Наименование контрагента")
    tin: str | None = Field(default=None, description="ИНН/СТИР (9 цифр) или ПИНФЛ")
    ref_1c: str | None = Field(default=None, description="Код/GUID в справочнике 1С")


class EmployeeRef(BaseModel):
    """Физлицо-сотрудник. В 1С не создаётся никогда — только резолвится (см. ТЗ §5.3.1)."""

    name: str = Field(description="ФИО подотчётного лица")
    ref_1c: str | None = Field(default=None, description="GUID физлица в 1С")


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
    kind: ItemKind = Field(
        default=ItemKind.GOODS,
        description="goods — товар (закладка Товары), service — услуга (закладка Услуги/Прочее)",
    )


class Totals(BaseModel):
    sum: float = Field(description="Итого без НДС, сум")
    vat_sum: float = 0.0


class ExpenseDetails(BaseModel):
    """Специфика чека подотчётника (Авансовый отчёт)."""

    accountable_person: EmployeeRef = Field(
        description="Подотчётное лицо. Обязательно: агент уточняет его у пользователя"
    )


class CustomsSection(BaseModel):
    """Раздел ГТД — группа товаров с одинаковым порядком расчёта таможенных платежей."""

    customs_value: float = Field(description="Таможенная стоимость товаров раздела, сум")
    duty_rate: float | None = Field(default=None, description="Ставка пошлины, % (справочно)")
    duty_sum: float = Field(description="Сумма пошлины по разделу, сум")
    fee_sum: float = Field(default=0.0, description="Таможенный сбор по разделу, сум")
    vat_sum: float = Field(description="НДС, уплаченный на таможне по разделу, сум")
    item_indexes: list[int] = Field(
        description="Индексы позиций items (с нуля), входящих в раздел"
    )


class CustomsDetails(BaseModel):
    """Специфика ГТД по импорту."""

    declaration_number: str = Field(description="Номер ГТД")
    declaration_date: str | None = Field(default=None, description="Дата ГТД, ГГГГ-ММ-ДД")
    customs_office: PartyRef = Field(description="Таможня — элемент справочника Контрагенты")
    deposit_contract: str | None = Field(
        default=None, description="Договор расчётов по таможенным платежам («Депозит»)"
    )
    vat_deduction: bool = Field(default=True, description="Отразить вычет в книге покупок")
    vat_deduction_term: str = Field(
        default="current_document",
        description="Срок вычета НДС: current_document | current_month | 12_months | 36_months",
    )
    sections: list[CustomsSection] = Field(min_length=1)


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

    currency: str = Field(default="UZS", description="Код валюты документа")
    exchange_rate: float | None = Field(
        default=None, description="Курс к суму на doc_date; null — 1С возьмёт свой"
    )

    # Блоки, специфичные для типа операции. Для остальных типов — None.
    expense_details: ExpenseDetails | None = None
    customs_details: CustomsDetails | None = None

    # Проставляется ботом, не моделью — идемпотентность и трассировка источника.
    external_id: str | None = None
    source_channel: str = "telegram"

    @model_validator(mode="after")
    def _check_type_details(self) -> "OperationDraft":
        """Ловим рассинхрон типа и блока до похода в 1С — там это стоило бы 422."""
        if self.operation_type is OperationType.EXPENSE_RECEIPT and self.expense_details is None:
            raise ValueError("expense_receipt требует expense_details с подотчётным лицом")

        if self.operation_type is OperationType.CUSTOMS_DECLARATION:
            if self.customs_details is None:
                raise ValueError("customs_declaration требует customs_details")
            self._check_customs_sections(self.customs_details)

        return self

    def _check_customs_sections(self, customs: CustomsDetails) -> None:
        """Разделы ГТД должны разбивать items на непересекающиеся группы без остатка.

        Иначе 1С не сможет распределить пошлину: товар без раздела не получит
        таможенных расходов, а товар в двух разделах получит их дважды.
        """
        seen: set[int] = set()
        for section in customs.sections:
            for idx in section.item_indexes:
                if not 0 <= idx < len(self.items):
                    raise ValueError(f"item_indexes: индекс {idx} вне диапазона items")
                if idx in seen:
                    raise ValueError(f"item_indexes: позиция {idx} попала в несколько разделов")
                seen.add(idx)

        missing = set(range(len(self.items))) - seen
        if missing:
            raise ValueError(f"item_indexes: позиции {sorted(missing)} не входят ни в один раздел")
