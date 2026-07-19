"""HTTP-клиент к API 1С (`/hs/copilot/v1`). В dev смотрит на мок (onec-mock)."""

import os

import httpx
from copilot_shared import (
    Counterparty,
    CreateOperationResponse,
    ItemRef,
    OperationDraft,
)

BASE_URL = os.environ.get("ONEC_BASE_URL", "http://localhost:8100")
_USER = os.environ.get("ONEC_USER")
_PASS = os.environ.get("ONEC_PASSWORD")


def _client() -> httpx.Client:
    auth = (_USER, _PASS) if _USER else None
    return httpx.Client(base_url=BASE_URL, auth=auth, timeout=15.0)


def find_counterparties(tin: str | None = None, name: str | None = None) -> list[Counterparty]:
    params = {k: v for k, v in {"tin": tin, "name": name}.items() if v}
    with _client() as c:
        r = c.get("/hs/copilot/v1/counterparties", params=params)
        r.raise_for_status()
        return [Counterparty.model_validate(x) for x in r.json()]


def find_items(query: str) -> list[ItemRef]:
    with _client() as c:
        r = c.get("/hs/copilot/v1/items", params={"query": query})
        r.raise_for_status()
        return [ItemRef.model_validate(x) for x in r.json()]


def create_operation(op: OperationDraft) -> CreateOperationResponse:
    headers = {"Idempotency-Key": op.external_id} if op.external_id else {}
    with _client() as c:
        r = c.post("/hs/copilot/v1/operations", json=op.model_dump(), headers=headers)
        r.raise_for_status()
        return CreateOperationResponse.model_validate(r.json())
