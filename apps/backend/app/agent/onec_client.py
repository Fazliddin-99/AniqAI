"""HTTP-клиент к API 1С (`/hs/copilot/v1`). Экземпляр — на подключение компании."""

import httpx
from copilot_shared import (
    Counterparty,
    CreateOperationResponse,
    Employee,
    ItemRef,
    OperationDraft,
)


class OnecClient:
    def __init__(self, base_url: str, user: str | None = None, password: str | None = None) -> None:
        self.base_url = base_url
        self._auth = (user, password) if user else None

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, auth=self._auth, timeout=15.0)

    def find_counterparties(self, tin: str | None = None,
                            name: str | None = None) -> list[Counterparty]:
        params = {k: v for k, v in {"tin": tin, "name": name}.items() if v}
        with self._client() as c:
            r = c.get("/hs/copilot/v1/counterparties", params=params)
            r.raise_for_status()
            return [Counterparty.model_validate(x) for x in r.json()]

    def find_items(self, query: str) -> list[ItemRef]:
        with self._client() as c:
            r = c.get("/hs/copilot/v1/items", params={"query": query})
            r.raise_for_status()
            return [ItemRef.model_validate(x) for x in r.json()]

    def find_employees(self, query: str) -> list[Employee]:
        with self._client() as c:
            r = c.get("/hs/copilot/v1/employees", params={"query": query})
            r.raise_for_status()
            return [Employee.model_validate(x) for x in r.json()]

    def create_operation(self, op: OperationDraft) -> CreateOperationResponse:
        headers = {"Idempotency-Key": op.external_id} if op.external_id else {}
        with self._client() as c:
            r = c.post("/hs/copilot/v1/operations", json=op.model_dump(), headers=headers)
            r.raise_for_status()
            return CreateOperationResponse.model_validate(r.json())
