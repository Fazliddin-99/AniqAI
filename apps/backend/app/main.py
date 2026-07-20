"""API очереди ревью. Запуск: uv run uvicorn app.main:app --reload"""

from dotenv import find_dotenv, load_dotenv

# Загрузить .env до импорта агента/клиента 1С (они читают переменные при импорте).
load_dotenv(find_dotenv(usecwd=True))

import os  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from .admin.router import router as admin_router  # noqa: E402
from .agent.api import router as agent_router  # noqa: E402
from .db.session import init_db  # noqa: E402
from .history import load_history  # noqa: E402
from .models import Esf, PostingEntry, ReviewItem, ReviewStatus  # noqa: E402
from .pipeline import process  # noqa: E402

init_db()

app = FastAPI(title="Accountant Copilot", version="0.1.0")
app.add_middleware(SessionMiddleware,
                   secret_key=os.environ.get("SESSION_SECRET", "dev-insecure-secret"))
app.include_router(agent_router)
app.include_router(admin_router)

# Прототип: состояние в памяти. Этап 1 — Postgres.
_queue: dict[str, ReviewItem] = {}
_history = load_history()


@app.post("/esf", response_model=ReviewItem)
def submit_esf(esf: Esf) -> ReviewItem:
    """Принять ЭСФ, классифицировать, положить в очередь."""
    item = process(esf, _history)
    _queue[item.id] = item
    return item


@app.get("/review-queue", response_model=list[ReviewItem])
def review_queue(status: ReviewStatus | None = None) -> list[ReviewItem]:
    items = list(_queue.values())
    if status is not None:
        items = [i for i in items if i.status == status]
    return items


@app.post("/review/{item_id}/confirm", response_model=ReviewItem)
def confirm(item_id: str, corrected_entries: list[PostingEntry] | None = None) -> ReviewItem:
    """Бухгалтер подтверждает (или исправляет) решение. Исправление — обучающий пример."""
    item = _queue.get(item_id)
    if item is None:
        raise HTTPException(404, "unknown review item")
    if corrected_entries is not None:
        item.decision.entries = corrected_entries
        item.status = ReviewStatus.CORRECTED
        # TODO этап 1: сохранить исправление в историю → retrieval классификатора
    else:
        item.status = ReviewStatus.CONFIRMED
    # TODO этап 2: создать непроведённый черновик документа в 1С через HTTP-сервис
    return item


@app.get("/metrics")
def metrics() -> dict:
    total = len(_queue)
    by_status = {s.value: sum(1 for i in _queue.values() if i.status == s) for s in ReviewStatus}
    auto = by_status[ReviewStatus.AUTO_POSTED.value]
    return {
        "documents_total": total,
        "by_status": by_status,
        "auto_posted_pct": round(100 * auto / total, 1) if total else 0.0,
    }
