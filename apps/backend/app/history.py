"""Хранилище исторических проводок — обучающая база классификатора.

Пока это JSON-выгрузка из 1С (data/real/history.json, иначе data/samples/history.json).
На этапе 1 заменяется на выгрузку через HTTP-сервис расширения 1С.
"""

import json
from pathlib import Path

from .models import HistoricalPosting

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"


def load_history() -> list[HistoricalPosting]:
    for candidate in (DATA_DIR / "real" / "history.json", DATA_DIR / "samples" / "history.json"):
        if candidate.exists():
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            return [HistoricalPosting.model_validate(p) for p in raw]
    return []


def exact_matches(
    history: list[HistoricalPosting], seller_tin: str, catalog_code: str
) -> list[HistoricalPosting]:
    """Точные совпадения: тот же поставщик и тот же ИКПУ."""
    return [p for p in history if p.seller_tin == seller_tin and p.catalog_code == catalog_code]


def similar(
    history: list[HistoricalPosting], seller_tin: str, catalog_code: str, limit: int = 10
) -> list[HistoricalPosting]:
    """Похожие проводки для few-shot контекста LLM.

    Приоритет: тот же поставщик > тот же ИКПУ > совпадение префикса ИКПУ (группа товаров).
    """

    def score(p: HistoricalPosting) -> int:
        s = 0
        if p.seller_tin == seller_tin:
            s += 4
        if p.catalog_code == catalog_code:
            s += 3
        elif p.catalog_code[:8] == catalog_code[:8]:
            s += 2
        elif p.catalog_code[:5] == catalog_code[:5]:
            s += 1
        return s

    ranked = sorted((p for p in history if score(p) > 0), key=score, reverse=True)
    return ranked[:limit]
