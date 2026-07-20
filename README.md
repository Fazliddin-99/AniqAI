# Accountant Copilot

ИИ-конвейер бухгалтерской рутины для «1С:Бухгалтерия для Узбекистана».
Приём документов (ЭСФ/Didox, Telegram, сканы) → классификация проводок с confidence →
очередь ревью → черновики документов в 1С. Бухгалтер — ревьюер, не оператор ввода.

Проект для конкурса [PAIA](https://awards.gov.uz/en/paia), трек Industry and Business AI.
План и календарь — в [PLAN.md](PLAN.md).

## Структура

| Путь | Что это |
|------|---------|
| `apps/backend/` | Оркестратор: пайплайн ЭСФ, классификатор, **ядро агента** (`app/agent`), API |
| `apps/bot/` | Telegram-бот приёма документов (фича 1) |
| `apps/onec-mock/` | Мок HTTP-сервиса 1С для dev — заменяет расширение до его готовности |
| `apps/web/` | Веб-приложение: очередь ревью, дашборд метрик |
| `packages/shared/` | Общие контракты (`copilot_shared`): операция, модели API 1С |
| `onec/` | Расширение конфигурации 1С (BSL) — разворачивается через /setup-1c-framework |
| `data/samples/` | Синтетические примеры ЭСФ и справочников (в git) |
| `data/real/` | Реальные выгрузки и черновики мока (в .gitignore, никогда в git) |

## Фича 1 — Telegram-приём документов

Дизайн: [docs/feature-01-telegram-intake.md](docs/feature-01-telegram-intake.md).

Настройка (один раз): `.env.example` → `.env` в корне, заполнить `ANTHROPIC_API_KEY`,
`BOT_TOKEN` (от @BotFather), `ADMIN_PASSWORD`, `SESSION_SECRET` и `APP_ENCRYPTION_KEY`
(сгенерировать: `uv run python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`).
`.env` читается всеми процессами и в git не попадает.

```bash
cp .env.example .env   # PowerShell: Copy-Item .env.example .env
```

Запуск локально (три терминала):

```bash
cd apps/onec-mock && uv run uvicorn app.main:app --port 8100   # 1. мок 1С
cd apps/backend  && uv run uvicorn app.main:app --port 8000    # 2. бэкенд + агент + админка
cd apps/bot      && uv run python -m bot.main                  # 3. бот
```

**Доступ пользователей** (кто к какой компании) хранится в БД (SQLite,
`data/real/copilot.db`), управляется в веб-админке: `http://localhost:8000/admin`
(вход по `ADMIN_PASSWORD`). Учётные данные 1С каждой компании шифруются
(`APP_ENCRYPTION_KEY`). Быстро завести первого пользователя без админки:

```bash
cd apps/backend && SEED_TELEGRAM_ID=<ваш telegram id> uv run python -m app.db.seed
```
