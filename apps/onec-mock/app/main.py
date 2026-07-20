"""Мок 1С. Ведёт себя как HTTP-сервис расширения: ищет справочники, создаёт
непроведённые черновики, поддерживает идемпотентность по Idempotency-Key.

Черновики пишутся в data/real/onec_drafts/ (в .gitignore) — переживают рестарт.
Запуск: uv run uvicorn app.main:app --port 8100 --reload
"""

import json
from pathlib import Path

from copilot_shared import (
    Counterparty,
    CreateOperationResponse,
    Employee,
    ItemRef,
    OperationDraft,
    OperationStatus,
    OperationType,
    RelatedDoc,
)
from fastapi import FastAPI, Header, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
DRAFTS_DIR = REPO_ROOT / "data" / "real" / "onec_drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="1С Copilot API (мок)", version="0.1.0")

# Тип операции → имя документа 1С (для наглядности в ответе).
DOC_TYPE = {
    OperationType.GOODS_RECEIPT: "Поступление товаров и услуг",
    OperationType.SALES_INVOICE: "Реализация товаров и услуг",
    OperationType.EXPENSE_RECEIPT: "Авансовый отчёт",
    OperationType.PAYMENT_ORDER: "Платёжное поручение исходящее",
    OperationType.CUSTOMS_DECLARATION: "ГТД по импорту",
}

# Сид справочников — согласован с data/samples/history.json для связных демо.
_COUNTERPARTIES = [
    Counterparty(ref_1c="CP-001", name='OOO "QURILISH SAVDO"', tin="301234567"),
    Counterparty(ref_1c="CP-002", name='OOO "TEXNO OLAM"', tin="302222333"),
    Counterparty(ref_1c="CP-003", name='OOO "OZIQ-OVQAT DISTRIBUTION"', tin="303333444"),
    Counterparty(ref_1c="CP-004", name='OOO "MEGA TRADE GROUP"', tin="304444555"),
]
_ITEMS = [
    ItemRef(ref_1c="IT-001", name="Цемент М400, мешок 50 кг", ikpu="06810001001000000"),
    ItemRef(ref_1c="IT-002", name="Смартфон Samsung Galaxy A15", ikpu="08517120001000000"),
    ItemRef(ref_1c="IT-003", name="Ноутбук HP 250 G9", ikpu="08471030001000000"),
]
_EMPLOYEES = [
    Employee(ref_1c="EMP-001", name="Каримов Азиз Рустамович", position="Менеджер по снабжению"),
    Employee(ref_1c="EMP-002", name="Юсупова Дилноза Шухратовна", position="Бухгалтер"),
    Employee(ref_1c="EMP-003", name="Каримов Бекзод Алишерович", position="Водитель"),
]


@app.get("/hs/copilot/v1/counterparties", response_model=list[Counterparty])
def find_counterparties(tin: str | None = None, name: str | None = None):
    res = _COUNTERPARTIES
    if tin:
        res = [c for c in res if c.tin == tin]
    if name:
        q = name.lower()
        res = [c for c in res if q in c.name.lower()]
    return res


@app.get("/hs/copilot/v1/items", response_model=list[ItemRef])
def find_items(query: str = ""):
    q = query.lower().strip()
    if not q:
        return _ITEMS
    return [i for i in _ITEMS if q in i.name.lower() or (i.ikpu and q in i.ikpu)]


@app.get("/hs/copilot/v1/employees", response_model=list[Employee])
def find_employees(query: str = ""):
    q = query.lower().strip()
    if not q:
        return _EMPLOYEES
    return [e for e in _EMPLOYEES if q in e.name.lower()]


@app.post("/hs/copilot/v1/operations", response_model=CreateOperationResponse)
def create_operation(
    op: OperationDraft,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = idempotency_key or op.external_id
    if not key:
        raise HTTPException(400, "Idempotency-Key или external_id обязателен")

    path = DRAFTS_DIR / f"{key}.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        resp = CreateOperationResponse.model_validate(saved["response"])
        resp.idempotent_hit = True
        return resp

    draft_id = f"DRAFT-{abs(hash(key)) % 1_000_000:06d}"
    related: list[RelatedDoc] = []
    if op.operation_type is OperationType.CUSTOMS_DECLARATION:
        # ГТД вводится на основании поступления — расширение создаёт пару (ТЗ §5.7).
        receipt_id = f"{draft_id}-R"
        related.append(RelatedDoc(
            draft_id=receipt_id,
            doc_type_1c="Поступление товаров и услуг",
            doc_number=op.doc_number or receipt_id,
            status=OperationStatus.DRAFT,
        ))

    resp = CreateOperationResponse(
        draft_id=draft_id,
        doc_type_1c=DOC_TYPE[op.operation_type],
        doc_number=(op.customs_details.declaration_number
                    if op.customs_details else op.doc_number or draft_id),
        status=OperationStatus.DRAFT,
        related_docs=related,
    )
    path.write_text(
        json.dumps({"operation": op.model_dump(), "response": resp.model_dump()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return resp


@app.get("/hs/copilot/v1/operations/{draft_id}", response_model=CreateOperationResponse)
def get_operation(draft_id: str):
    for path in DRAFTS_DIR.glob("*.json"):
        saved = json.loads(path.read_text(encoding="utf-8"))
        resp = CreateOperationResponse.model_validate(saved["response"])
        if resp.draft_id == draft_id:
            return resp
        # Документ из пары спрашивают по его собственному GUID (ТЗ §6).
        for rel in resp.related_docs:
            if rel.draft_id == draft_id:
                return CreateOperationResponse(
                    draft_id=rel.draft_id,
                    doc_type_1c=rel.doc_type_1c,
                    doc_number=rel.doc_number,
                    status=rel.status,
                )
    raise HTTPException(404, "черновик не найден")
