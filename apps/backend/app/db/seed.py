"""Быстрый сид демо-компании и первого пользователя (для локального старта без админки).

Запуск: SEED_TELEGRAM_ID=<ваш id> uv run python -m app.db.seed
(база 1С берётся из ONEC_BASE_URL, по умолчанию мок на localhost:8100).
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from . import service  # noqa: E402
from .session import get_session, init_db  # noqa: E402


def main() -> None:
    telegram_id = os.environ.get("SEED_TELEGRAM_ID")
    if not telegram_id:
        raise SystemExit("Задайте SEED_TELEGRAM_ID (ваш числовой Telegram id).")

    init_db()
    db = get_session()
    try:
        existing = [u.telegram_user_id for u in service.list_users(db)]
        if int(telegram_id) in existing:
            print(f"Пользователь {telegram_id} уже есть.")
            return
        companies = service.list_companies(db)
        company = companies[0] if companies else service.create_company(
            db, name="Демо-компания",
            base_url=os.environ.get("ONEC_BASE_URL", "http://localhost:8100"),
            onec_user=os.environ.get("ONEC_USER"),
            onec_password=os.environ.get("ONEC_PASSWORD"))
        service.create_user(db, telegram_user_id=int(telegram_id),
                            company_id=company.id, name="Первый пользователь", role="admin")
        print(f"Готово: компания «{company.name}» (id={company.id}), "
              f"пользователь {telegram_id} добавлен.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
