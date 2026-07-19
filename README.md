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
Запуск локально (три процесса):

```bash
# 1. Мок 1С
cd apps/onec-mock && uv run uvicorn app.main:app --port 8100

# 2. Бэкенд (ядро агента + API). Нужен ключ Claude.
cd apps/backend && ONEC_BASE_URL=http://localhost:8100 \
  uv run uvicorn app.main:app --port 8000

# 3. Бот
cd apps/bot && BOT_TOKEN=<токен> BACKEND_URL=http://localhost:8000 \
  BOT_WHITELIST="<telegram_user_id>:demo" uv run python -m bot.main
```
