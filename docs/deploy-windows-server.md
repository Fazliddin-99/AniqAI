# Деплой на Windows Server

Инструкция развёртывания Python-стека (Telegram-бот + backend) на боевом
Windows Server. 1С может жить на этой же машине или на соседней — backend ходит
в неё по HTTP. Мок (`apps/onec-mock`) на сервер не ставится.

## 1. Предварительные требования

| Что | Зачем |
|---|---|
| Windows Server 2019+ (или Windows 10/11 Pro) | ОС |
| [uv](https://docs.astral.sh/uv/) | зависимости и запуск (Python 3.12 скачает сам) |
| Git | доставка кода |
| [NSSM](https://nssm.cc/download) | запуск бота и backend как Windows-служб |

Установка инструментов. На Windows Server `winget` обычно отсутствует —
ставим напрямую (PowerShell от администратора):

```powershell
# uv (после установки перезапустить PowerShell — обновится PATH)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# NSSM
Invoke-WebRequest https://nssm.cc/release/nssm-2.24.zip -OutFile $env:TEMP\nssm.zip
Expand-Archive $env:TEMP\nssm.zip -DestinationPath C:\tools\
copy C:\tools\nssm-2.24\win64\nssm.exe C:\Windows\System32\

# Git (если не установлен) — https://git-scm.com/download/win, либо:
Invoke-WebRequest https://github.com/git-for-windows/git/releases/latest/download/Git-64-bit.exe -OutFile $env:TEMP\git.exe 2>$null
# (если прямая ссылка не сработала — скачать установщик с сайта вручную)
& $env:TEMP\git.exe /VERYSILENT /NORESTART
```

Отдельная установка Python не нужна: `uv sync` сам скачает Python 3.12.
| Исходящий доступ к `api.telegram.org:443` и `api.anthropic.com:443` | Telegram и Claude |
| Сетевой доступ к публикации 1С (`http(s)://<хост-1С>/copilot/hs/copilot/v1`) | данные |

В 1С к этому моменту должно быть: опубликован HTTP-сервис `copilot` (ТЗ
`onec-api-spec.md`), заведён пользователь ИБ **BA_КопилотAPI** с ролью
расширения (интерактивный вход запрещён), включён **HTTPS** на публикации
(требование ТЗ §2 для продуктива).

## 2. Установка

```powershell
cd C:\srv
git clone <url-репозитория> Accountant-Copilot
cd Accountant-Copilot

# Зависимости (у каждого приложения своё окружение, shared подтянется сам)
cd apps\backend;  uv sync;  cd ..\..
cd apps\bot;      uv sync;  cd ..\..
```

## 3. Конфигурация: `.env` в корне репозитория

Скопировать `.env.example` → `.env` и заполнить:

```ini
# Claude
ANTHROPIC_API_KEY=sk-ant-...            # боевой ключ с пополненным балансом

# Подключение 1С по умолчанию (для сид-скрипта; реальные подключения компаний — в админке)
ONEC_BASE_URL=https://<хост-1С>/copilot

# Шифрование учётных данных 1С в БД
APP_ENCRYPTION_KEY=<uv run python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">

# Веб-админка
ADMIN_PASSWORD=<сильный пароль>
SESSION_SECRET=<второй Fernet-ключ, команда та же>

# Telegram
BOT_TOKEN=<токен продуктового бота от @BotFather>
BACKEND_URL=http://localhost:8000
```

⚠️ Не переносить dev-значения из рабочей машины: пароль админки, ключи
шифрования и токены на сервере должны быть свои. `.env` в git не попадает.

## 4. Инициализация БД и доступа

```powershell
cd apps\backend
$env:SEED_TELEGRAM_ID = "<ваш telegram id>"
uv run python -m app.db.seed
```

Дальше компании и пользователи заводятся через веб-админку
`http://localhost:8000/admin` (пароль из `.env`): для каждой компании — её
`base_url` публикации 1С + логин/пароль `BA_КопилотAPI` (хранятся в БД
зашифрованными). БД лежит в `data\real\copilot.db`.

## 5. Запуск как Windows-службы (NSSM)

```powershell
$repo = "C:\srv\Accountant-Copilot"
$uv = (Get-Command uv).Source

# Backend
nssm install CopilotBackend $uv "run uvicorn app.main:app --host 127.0.0.1 --port 8000"
nssm set CopilotBackend AppDirectory   $repo\apps\backend
nssm set CopilotBackend AppEnvironmentExtra PYTHONUTF8=1
nssm set CopilotBackend AppStdout      $repo\logs\backend.out.log
nssm set CopilotBackend AppStderr      $repo\logs\backend.err.log
nssm set CopilotBackend AppExit        Default Restart      # автоперезапуск при падении
nssm set CopilotBackend Start          SERVICE_AUTO_START   # автозапуск при загрузке

# Бот
nssm install CopilotBot $uv "run python -m bot.main"
nssm set CopilotBot AppDirectory   $repo\apps\bot
nssm set CopilotBot AppEnvironmentExtra PYTHONUTF8=1
nssm set CopilotBot AppStdout      $repo\logs\bot.out.log
nssm set CopilotBot AppStderr      $repo\logs\bot.err.log
nssm set CopilotBot AppExit        Default Restart
nssm set CopilotBot Start          SERVICE_AUTO_START

mkdir $repo\logs -Force
nssm start CopilotBackend
nssm start CopilotBot
```

Порт 8000 наружу не публиковать (бот ходит на localhost). Если админка нужна
извне — только через обратный прокси с HTTPS и ограничением по IP.

## 6. Проверка

```powershell
# Backend жив
curl http://localhost:8000/metrics                       # → 200

# 1С достижима с сервера
curl -u "BA_КопилотAPI:<пароль>" https://<хост-1С>/copilot/hs/copilot/v1/warehouses  # → 200

# Бот на полинге (pending_update_count не растёт)
curl https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```

Затем e2e руками: написать боту чек → карточка → «Отправить в 1С» → черновик
в базе; спросить «сколько нам должны?» → цифры из 1С.

## 7. Обновление версии

```powershell
cd C:\srv\Accountant-Copilot
git pull
cd apps\backend; uv sync; cd ..\..
cd apps\bot;     uv sync; cd ..\..
nssm restart CopilotBackend
nssm restart CopilotBot
```

## 8. Эксплуатация

- **Бэкап**: `data\real\copilot.db` (компании, пользователи, зашифрованные
  учётки 1С) + `.env`. Достаточно ежедневного копирования файла.
- **Логи**: `logs\*.log` (ротацию включить `nssm set <svc> AppRotateFiles 1`).
- **Типовые сбои**: 1С недоступна → бот честно отвечает пользователю, чинить
  сеть/публикацию; «credit balance is too low» в логе backend → пополнить
  баланс Anthropic; смена токена бота → обновить `.env`, `nssm restart CopilotBot`.
- **Смена подключения 1С** (переезд базы) — через админку, без перезапуска
  служб не обойтись только при смене `.env`.

## 9. Чего в этой схеме осознанно нет (кандидаты на пилот)

- Postgres вместо SQLite — смена `DATABASE_URL`, заложено в архитектуре.
- Метрики/алертинг (сейчас — только `/metrics` и логи).
- Второй экземпляр backend — сессии агента живут в памяти процесса,
  горизонтальное масштабирование потребует внешнего хранилища сессий.
