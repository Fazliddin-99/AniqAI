"""Модели отчётных эндпоинтов 1С (ТЗ §4.7–4.9) — аналитика для директора.

Общие для мока, клиента бэкенда и тестов. Цифры из этих ответов — единственный
источник чисел в ответах агента (правило «никаких сгенерированных чисел»).
"""

from pydantic import BaseModel, Field


# --- §4.7 Обороты и остатки по счёту ---

class AccountTotals(BaseModel):
    opening_debit: float = 0.0
    opening_credit: float = 0.0
    turnover_debit: float = 0.0
    turnover_credit: float = 0.0
    closing_debit: float = 0.0
    closing_credit: float = 0.0


class AccountRow(AccountTotals):
    """Строка разреза (субконто или месяц). Для month ref_1c всегда null."""

    name: str
    ref_1c: str | None = None
    kind: str | None = None  # вид субконто; 1С может не отдавать (необязательное)


class AccountReport(BaseModel):
    organization: str | None = None  # из настройки 1С; «все организации» если не задана
    account: str
    account_name: str
    date_from: str
    date_to: str
    group_by: str = "none"
    total: AccountTotals
    rows: list[AccountRow] = Field(default_factory=list)
    truncated: bool = False


# --- §4.8 Продажи по периодам ---

class SalesBreakdownRow(BaseModel):
    name: str
    ref_1c: str | None = None
    revenue: float = 0.0
    cost: float = 0.0
    qty: float = 0.0


class SalesPeriod(BaseModel):
    period: str  # "2026-06" или "2026-06-15" при granularity=day
    revenue: float = 0.0  # без НДС, кредитовый оборот 9010
    cost: float = 0.0     # дебетовый оборот 9110
    qty: float = 0.0
    doc_count: int = 0
    breakdown: list[SalesBreakdownRow] = Field(default_factory=list)
    truncated: bool = False


class SalesReport(BaseModel):
    organization: str | None = None  # из настройки 1С; «все организации» если не задана
    date_from: str
    date_to: str
    granularity: str = "month"
    dimension: str = "none"
    periods: list[SalesPeriod] = Field(default_factory=list)


# --- §4.9 Денежные средства ---

class CashAccount(BaseModel):
    kind: str  # bank | cash
    name: str
    account: str  # 5010 / 5110 / 5210
    currency: str = "UZS"
    balance: float = 0.0      # в валюте счёта
    balance_uzs: float = 0.0  # в сумах по курсу на дату


class CashReport(BaseModel):
    organization: str | None = None  # из настройки 1С; «все организации» если не задана
    date: str
    total_uzs: float = 0.0
    accounts: list[CashAccount] = Field(default_factory=list)
