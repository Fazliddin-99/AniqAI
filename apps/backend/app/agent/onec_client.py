"""HTTP-клиент к API 1С (`/hs/copilot/v1`). Экземпляр — на подключение компании."""

from urllib.parse import quote

import httpx
from copilot_shared import (
    AccountReport,
    CashReport,
    Counterparty,
    CreateOperationResponse,
    Employee,
    ItemRef,
    OperationDraft,
    SalesReport,
    Warehouse,
)


def _qs(**params: str | None) -> str:
    """Query string с пробелами как %20: HTTP-сервис 1С не декодирует «+» в пробел."""
    pairs = [f"{k}={quote(v, safe='')}" for k, v in params.items() if v]
    return ("?" + "&".join(pairs)) if pairs else ""


class OnecClient:
    def __init__(self, base_url: str, user: str | None = None, password: str | None = None) -> None:
        self.base_url = base_url
        # Пустой пароль (публикация 1С с пользователем без пароля) — валидный случай.
        self._auth = (user, password or "") if user else None

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, auth=self._auth, timeout=15.0)

    def find_counterparties(self, tin: str | None = None,
                            name: str | None = None) -> list[Counterparty]:
        with self._client() as c:
            r = c.get("/hs/copilot/v1/counterparties" + _qs(tin=tin, name=name))
            r.raise_for_status()
            return [Counterparty.model_validate(x) for x in r.json()]

    def find_items(self, query: str) -> list[ItemRef]:
        with self._client() as c:
            r = c.get("/hs/copilot/v1/items" + _qs(query=query))
            r.raise_for_status()
            return [ItemRef.model_validate(x) for x in r.json()]

    def find_warehouses(self, query: str = "") -> list[Warehouse]:
        with self._client() as c:
            r = c.get("/hs/copilot/v1/warehouses" + _qs(query=query))
            r.raise_for_status()
            return [Warehouse.model_validate(x) for x in r.json()]

    def find_employees(self, query: str) -> list[Employee]:
        with self._client() as c:
            r = c.get("/hs/copilot/v1/employees" + _qs(query=query))
            r.raise_for_status()
            return [Employee.model_validate(x) for x in r.json()]

    def _report_client(self) -> httpx.Client:
        # Отчёты (ОСВ по большому счёту) на реальной базе бывают медленными.
        return httpx.Client(base_url=self.base_url, auth=self._auth, timeout=60.0)

    def get_account_report(self, account: str, date_from: str, date_to: str,
                           group_by: str | None = None,
                           limit: int | None = None) -> AccountReport:
        qs = _qs(account=account, date_from=date_from, date_to=date_to,
                 group_by=group_by, limit=str(limit) if limit else None)
        with self._report_client() as c:
            r = c.get("/hs/copilot/v1/reports/account" + qs)
            r.raise_for_status()
            return AccountReport.model_validate(r.json())

    def get_sales_report(self, date_from: str, date_to: str,
                         granularity: str | None = None,
                         dimension: str | None = None,
                         limit: int | None = None) -> SalesReport:
        qs = _qs(date_from=date_from, date_to=date_to, granularity=granularity,
                 dimension=dimension, limit=str(limit) if limit else None)
        with self._report_client() as c:
            r = c.get("/hs/copilot/v1/reports/sales" + qs)
            r.raise_for_status()
            return SalesReport.model_validate(r.json())

    def get_cash_report(self, date: str | None = None) -> CashReport:
        with self._report_client() as c:
            r = c.get("/hs/copilot/v1/reports/cash" + _qs(date=date))
            r.raise_for_status()
            return CashReport.model_validate(r.json())

    def post_operation(self, draft_id: str) -> CreateOperationResponse:
        """Провести созданный сервисом документ (ТЗ §6.1) — только после явного
        подтверждения пользователя кнопкой в боте."""
        with self._client() as c:
            # content=b"" — явный Content-Length: 0, иначе IIS отвечает 411.
            r = c.post(f"/hs/copilot/v1/operations/{draft_id}/post", content=b"")
            r.raise_for_status()
            return CreateOperationResponse.model_validate(r.json())

    def create_operation(self, op: OperationDraft) -> CreateOperationResponse:
        headers = {"Idempotency-Key": op.external_id} if op.external_id else {}
        with self._client() as c:
            r = c.post("/hs/copilot/v1/operations", json=op.model_dump(), headers=headers)
            r.raise_for_status()
            return CreateOperationResponse.model_validate(r.json())
