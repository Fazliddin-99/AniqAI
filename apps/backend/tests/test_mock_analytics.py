"""Инварианты сида и отчётных эндпоинтов мока (эталон для 1С, ТЗ §4.7–4.9).

Пакет мока тоже называется `app` и конфликтует с пакетом бэкенда — импортируем
его через importlib под отдельным именем `onec_mock_app`.
"""

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PKG_DIR = Path(__file__).resolve().parents[3] / "apps" / "onec-mock" / "app"
_spec = importlib.util.spec_from_file_location(
    "onec_mock_app", _PKG_DIR / "__init__.py",
    submodule_search_locations=[str(_PKG_DIR)])
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["onec_mock_app"] = _pkg
_spec.loader.exec_module(_pkg)
mock_app = importlib.import_module("onec_mock_app.main").app

client = TestClient(mock_app)


def test_sales_july_drop():
    """Демо-история: июль 2026 существенно ниже июня (-40%)."""
    r = client.get("/hs/copilot/v1/reports/sales",
                   params={"date_from": "2026-06-01", "date_to": "2026-07-31"})
    assert r.status_code == 200
    periods = {p["period"]: p for p in r.json()["periods"]}
    assert periods["2026-07"]["revenue"] < 0.7 * periods["2026-06"]["revenue"]


def test_sales_empty_months_are_zero():
    r = client.get("/hs/copilot/v1/reports/sales",
                   params={"date_from": "2024-01-01", "date_to": "2024-03-31"})
    periods = r.json()["periods"]
    assert [p["period"] for p in periods] == ["2024-01", "2024-02", "2024-03"]
    assert all(p["revenue"] == 0 for p in periods)


def test_sales_breakdown_totals_and_truncation():
    r = client.get("/hs/copilot/v1/reports/sales",
                   params={"date_from": "2026-06-01", "date_to": "2026-06-30",
                           "dimension": "item", "limit": 2})
    p = r.json()["periods"][0]
    assert p["truncated"] is True  # в июне 3 товара, limit=2
    assert sum(b["revenue"] for b in p["breakdown"]) <= p["revenue"]


def test_account_total_covers_full_set_when_truncated():
    full = client.get("/hs/copilot/v1/reports/account",
                      params={"account": "4010", "date_from": "2026-01-01",
                              "date_to": "2026-07-31", "group_by": "subconto1"}).json()
    cut = client.get("/hs/copilot/v1/reports/account",
                     params={"account": "4010", "date_from": "2026-01-01",
                             "date_to": "2026-07-31", "group_by": "subconto1",
                             "limit": 2}).json()
    assert cut["truncated"] is True
    assert cut["total"] == full["total"]  # total не зависит от limit
    s = sum(r["turnover_debit"] for r in full["rows"])
    assert abs(s - full["total"]["turnover_debit"]) < 1


def test_account_month_groups_sum_to_total():
    rep = client.get("/hs/copilot/v1/reports/account",
                     params={"account": "9010", "date_from": "2026-01-01",
                             "date_to": "2026-07-31", "group_by": "month"}).json()
    s = sum(r["turnover_credit"] for r in rep["rows"])
    assert abs(s - rep["total"]["turnover_credit"]) < 1


def test_account_prefix_includes_subaccounts():
    rep = client.get("/hs/copilot/v1/reports/account",
                     params={"account": "94", "date_from": "2026-07-01",
                             "date_to": "2026-07-31", "group_by": "subconto1"}).json()
    names = [r["name"] for r in rep["rows"]]
    assert "Услуги банка" in names  # 9430 попал по префиксу «94»


def test_mega_trade_is_top_debtor():
    """Демо-история: у MEGA TRADE крупнейшая ДЗ."""
    rep = client.get("/hs/copilot/v1/reports/account",
                     params={"account": "4010", "date_from": "2026-01-01",
                             "date_to": "2026-08-31", "group_by": "subconto1"}).json()
    assert rep["rows"][0]["name"] == 'OOO "MEGA TRADE GROUP"'


@pytest.mark.parametrize("params,status,code", [
    ({"date_from": "2026-01-01", "date_to": "2026-02-01"}, 400, "bad_request"),
    ({"account": "9999", "date_from": "2026-01-01", "date_to": "2026-02-01"},
     404, "account_not_found"),
])
def test_account_errors(params, status, code):
    r = client.get("/hs/copilot/v1/reports/account", params=params)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code


def test_cash_totals():
    rep = client.get("/hs/copilot/v1/reports/cash",
                     params={"date": "2026-08-14"}).json()
    assert rep["date"] == "2026-08-14"
    assert abs(rep["total_uzs"] - sum(a["balance_uzs"] for a in rep["accounts"])) < 1
    kinds = {a["kind"] for a in rep["accounts"]}
    assert kinds == {"bank", "cash"}
