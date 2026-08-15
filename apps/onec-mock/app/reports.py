"""Отчётные эндпоинты мока (ТЗ §4.7–4.9) — эталон поведения для 1С-команды.

Все цифры считаются из детерминированного сида analytics_seed. Ключевые
семантики, которые обязана повторить 1С: total по ПОЛНОМУ набору строк даже при
truncated; периоды без продаж — нулями; префиксный поиск счёта; ошибки §6.
"""

from datetime import date

from copilot_shared import (
    AccountReport,
    AccountRow,
    AccountTotals,
    CashAccount,
    CashReport,
    SalesBreakdownRow,
    SalesPeriod,
    SalesReport,
)
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from . import analytics_seed as seed

router = APIRouter(prefix="/hs/copilot/v1/reports")

MAX_LIMIT = 100


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _clamp(limit: int | None, default: int) -> int:
    if not limit or limit <= 0:
        return default
    return min(limit, MAX_LIMIT)


def _month(d: str) -> str:
    return d[:7]


def _months_between(date_from: str, date_to: str) -> list[str]:
    """Все месяцы периода, включая пустые (провалы должны быть видны)."""
    y, m = int(date_from[:4]), int(date_from[5:7])
    end = _month(date_to)
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# --- §4.8 Продажи ---

@router.get("/sales")
def sales_report(date_from: str = "", date_to: str = "",
                 granularity: str = "month", dimension: str = "none",
                 limit: int | None = None):
    if not date_from or not date_to:
        return _err(400, "bad_request", "date_from и date_to обязательны")
    if granularity not in ("month", "day") or dimension not in ("none", "item", "counterparty"):
        return _err(400, "bad_request", "неверный granularity или dimension")
    lim = _clamp(limit, 10)

    periods: list[SalesPeriod] = []
    for month in _months_between(date_from, date_to):
        lines = seed.SALES.get(month, [])
        # granularity=day: детерминированно раскладываем строки месяца по дням
        # 5/12/19/26 — у мока нет подневных данных, а форма ответа должна быть та же.
        buckets: dict[str, list] = {}
        if granularity == "day":
            for i, ln in enumerate(lines):
                buckets[f"{month}-{5 + (i % 4) * 7:02d}"] = buckets.get(
                    f"{month}-{5 + (i % 4) * 7:02d}", []) + [ln]
            if not lines:
                buckets[f"{month}-15"] = []
        else:
            buckets[month] = lines

        for period, plines in sorted(buckets.items()):
            revenue = sum(r for _, _, _, r, _ in plines)
            cost = sum(c for _, _, _, _, c in plines)
            qty = sum(q for _, _, q, _, _ in plines)
            breakdown: list[SalesBreakdownRow] = []
            truncated = False
            if dimension != "none" and plines:
                agg: dict[str, SalesBreakdownRow] = {}
                for item_ref, buyer_ref, q, r, c in plines:
                    ref = item_ref if dimension == "item" else buyer_ref
                    name = (seed.item_name(ref) if dimension == "item"
                            else seed.buyer_name(ref))
                    row = agg.setdefault(ref, SalesBreakdownRow(name=name, ref_1c=ref))
                    row.revenue += r
                    row.cost += c
                    row.qty += q
                full = sorted(agg.values(), key=lambda x: -x.revenue)
                truncated = len(full) > lim
                breakdown = full[:lim]
            periods.append(SalesPeriod(
                period=period, revenue=revenue, cost=cost, qty=qty,
                doc_count=seed.DOC_COUNT.get(month, 0) if granularity == "month" else len(plines),
                breakdown=breakdown, truncated=truncated))

    return SalesReport(date_from=date_from, date_to=date_to,
                       granularity=granularity, dimension=dimension,
                       periods=periods).model_dump()


# --- §4.7 Обороты/остатки по счёту ---

def _account_rows(account: str, date_from: str, date_to: str,
                  group_by: str) -> tuple[AccountTotals, list[AccountRow]]:
    """Полный (до limit) набор строк и итог по счёту за период."""
    months = _months_between(date_from, date_to)
    rows: dict[str, AccountRow] = {}

    def add(key: str, name: str, ref: str | None, kind: str | None = None,
            **kw: float) -> None:
        row = rows.setdefault(key, AccountRow(name=name, ref_1c=ref, kind=kind))
        for f, v in kw.items():
            setattr(row, f, getattr(row, f) + v)

    if account.startswith("4010"):
        # ДЗ покупателей: открытие = сид + движения до date_from, обороты за период.
        for ref, _name in seed.BUYERS:
            opening = seed.RECEIVABLES_OPENING.get(ref, 0.0)
            for m in seed.months():
                if m >= _month(date_from):
                    break
                d, k = seed.receivables_movement(m, ref)
                opening += d - k
            if group_by == "month":
                # Помесячный разрез — только обороты (остатки мок не разносит).
                for m in months:
                    d, k = seed.receivables_movement(m, ref)
                    add(m, m, None, turnover_debit=d, turnover_credit=k)
            else:
                td = tk = 0.0
                for m in months:
                    d, k = seed.receivables_movement(m, ref)
                    td += d
                    tk += k
                add(ref, seed.buyer_name(ref), ref, kind="Контрагенты",
                    opening_debit=round(opening, 2), turnover_debit=round(td, 2),
                    turnover_credit=round(tk, 2),
                    closing_debit=round(opening + td - tk, 2))
    elif account.startswith("6010"):
        # КЗ поставщикам: закупки = 60% выручки месяца (70/30 между двумя),
        # оплаты = 95% закупок прошлого месяца. Детерминированно.
        for i, (ref, name) in enumerate(seed.SUPPLIERS):
            share = 0.7 if i == 0 else 0.3
            opening = 30_000_000.0 * share
            for m in seed.months():
                if m >= _month(date_from):
                    break
                buy = seed.month_revenue(m) * 0.6 * share
                ms = seed.months()
                prev = ms[ms.index(m) - 1] if ms.index(m) > 0 else None
                pay = (seed.month_revenue(prev) * 0.6 * share * 0.95) if prev else 0.0
                opening += buy - pay
            td = tk = 0.0
            for m in months:
                tk += seed.month_revenue(m) * 0.6 * share
                ms = seed.months()
                if m in ms and ms.index(m) > 0:
                    td += seed.month_revenue(ms[ms.index(m) - 1]) * 0.6 * share * 0.95
            add(ref, name, ref, kind="Контрагенты", opening_credit=round(opening, 2),
                turnover_debit=round(td, 2), turnover_credit=round(tk, 2),
                closing_credit=round(opening + tk - td, 2))
    elif account.startswith("9010") or account.startswith("9110"):
        is_rev = account.startswith("9010")
        for m in months:
            for item_ref, buyer_ref, q, r, c in seed.SALES.get(m, []):
                val = r if is_rev else c
                fld = "turnover_credit" if is_rev else "turnover_debit"
                if group_by == "month":
                    add(m, m, None, **{fld: val})
                elif group_by == "subconto2":
                    add(buyer_ref, seed.buyer_name(buyer_ref), buyer_ref,
                        kind="Контрагенты", **{fld: val})
                else:  # none/subconto1 — номенклатура
                    add(item_ref, seed.item_name(item_ref), item_ref,
                        kind="Номенклатура", **{fld: val})
    elif account.startswith("94"):
        for m in months:
            for acc, article, s in seed.EXPENSES.get(m, []):
                if not acc.startswith(account):
                    continue
                if group_by == "month":
                    add(m, m, None, turnover_debit=s)
                else:
                    add(article, article, None, kind="Статьи затрат", turnover_debit=s)
    elif account[:2] in ("50", "51", "52"):
        for a in seed.CASH_ACCOUNTS:
            if a["account"].startswith(account) or account.startswith(str(a["account"])):
                add(a["account"], a["name"], None,
                    closing_debit=a["balance_uzs"])
    else:
        raise KeyError(account)

    full = sorted(rows.values(),
                  key=lambda r: (r.name if group_by == "month"
                                 else -(r.turnover_debit + r.turnover_credit
                                        + r.closing_debit + r.closing_credit)))
    if group_by == "month":
        full = list(full)  # хронологический порядок для месяцев
    total = AccountTotals()
    for r in full:
        for f in ("opening_debit", "opening_credit", "turnover_debit",
                  "turnover_credit", "closing_debit", "closing_credit"):
            setattr(total, f, round(getattr(total, f) + getattr(r, f), 2))
    return total, full


@router.get("/account")
def account_report(account: str = "", date_from: str = "", date_to: str = "",
                   group_by: str = "none", limit: int | None = None):
    if not account or not date_from or not date_to:
        return _err(400, "bad_request", "account, date_from и date_to обязательны")
    if group_by not in ("none", "subconto1", "subconto2", "month"):
        return _err(400, "bad_request", f"неверный group_by: {group_by}")
    lim = _clamp(limit, 20)
    try:
        total, full = _account_rows(account, date_from, date_to, group_by)
    except KeyError:
        return _err(404, "account_not_found", f"счёт {account} не найден")
    rows = [] if group_by == "none" else full[:lim]
    name = seed.ACCOUNT_NAMES.get(account) or next(
        (v for k, v in seed.ACCOUNT_NAMES.items() if k.startswith(account)), account)
    return AccountReport(
        account=account, account_name=name,
        date_from=date_from, date_to=date_to, group_by=group_by,
        total=total, rows=rows,
        truncated=group_by != "none" and len(full) > lim).model_dump()


# --- §4.9 Деньги ---

@router.get("/cash")
def cash_report(date_: str | None = Query(default=None, alias="date")):
    d = date_ or date.today().isoformat()
    accounts = [CashAccount(**a) for a in seed.CASH_ACCOUNTS]
    return CashReport(date=d, total_uzs=round(sum(a.balance_uzs for a in accounts), 2),
                      accounts=accounts).model_dump()
