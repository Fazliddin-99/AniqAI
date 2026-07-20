# Accountant Copilot — 1С-часть (BSL Agent Development Framework)

## ⚠️ Область работы: ТОЛЬКО каталог `onec/`

Это **подпроект** мультипроектного репозитория `C:\Projects\Accountant-Copilot`.
Родительский репозиторий содержит несторонние к 1С части (`apps/`, `packages/`,
`data/`, корневой `docs/`) — **фреймворк и агенты не должны их читать на предмет
изменения и не должны редактировать ничего за пределами `onec/`**.

Исключение (только чтение): `../docs/onec-api-spec.md` — ТЗ на разрабатываемое
расширение, источник требований.

## Конфигурация и база

- **Конфигурация**: «1С:Бухгалтерия для Узбекистана», ред. 3.0.
- **Исходники**: `src/cf` — выгрузка XML типовой конфигурации; `src/cfe` — расширения
  (сюда ляжет наше расширение `copilot`).
- **Документация конфигурации** (markdown): `docs/buhuz30`, `docs/accountinguz` —
  использовать как источник знаний по объектам БП УЗ перед поиском в исходниках.
- **Демо-база для тестов**: `Srvr="new1c";Ref="fazliddin_acc_60_3_demo"`,
  пользователь `Admin`, без пароля. Это **тестовая** база — рабочие базы клиентов
  трогать нельзя.

## Задача подпроекта

Разработать **расширение конфигурации** (не менять типовую!), публикующее HTTP-сервис
`copilot` (`/hs/copilot/v1`) из четырёх операций: поиск контрагентов, поиск
номенклатуры, создание непроведённого документа из JSON-операции (с идемпотентностью),
статус документа. Полное ТЗ, контракты JSON, маппинг на документы БП 3.0, требования
к правам и чек-лист приёмки — в `../docs/onec-api-spec.md`.

Ключевые инварианты: документы **только записываются, никогда не проводятся**;
типовая конфигурация не изменяется; повторный вызов с тем же ключом идемпотентности
не создаёт дубль.

Эталон поведения API — мок-сервер `../apps/onec-mock` (FastAPI): при сомнении в формате
ответа поведение расширения должно совпадать с ним.

---

## Always-on правила фреймворка

@.claude/rules/framework-bootstrap.md
@.claude/rules/agent-context-protocol.md
@.claude/rules/agent-debug.md
@.claude/rules/buddy-prompting.md
@.claude/rules/bug-reporting.md
@.claude/rules/capability-resolution.md
@.claude/rules/code-verification.md
@.claude/rules/coding-standards.md
@.claude/rules/dap-bsl-debugger.md
@.claude/rules/error-handling.md
@.claude/rules/escalation-format.md
@.claude/rules/form-patterns.md
@.claude/rules/form-visual-check.md
@.claude/rules/git-workflow.md
@.claude/rules/infostart-kb.md
@.claude/rules/metadata-object-design.md
@.claude/rules/no-direct-db-access.md
@.claude/rules/no-manual-xml-edit.md
@.claude/rules/predefined-elements.md
@.claude/rules/protected-paths.md
@.claude/rules/query-optimize.md
@.claude/rules/query-patterns.md
@.claude/rules/report-discovered-issues.md
@.claude/rules/rlm-workflow.md
@.claude/rules/sdd-policy.md
@.claude/rules/search-before-write.md
@.claude/rules/security.md
@.claude/rules/self-recovery-limits.md
@.claude/rules/semantic-code-comments.md
@.claude/rules/skill-learning-policy.md
@.claude/rules/skill-reading-protocol.md
@.claude/rules/source-of-truth.md
@.claude/rules/ssl-patterns.md
@.claude/rules/tdd-policy.md
@.claude/rules/test-zero-residue.md
@.claude/rules/vanessa-diagnostics-policy.md
@.claude/rules/vanessa-run-loop.md
@.claude/rules/vanessa-scenario-policy.md
@.claude/rules/vanessa-security-warning.md
@.claude/rules/vanessa-test-isolation-policy.md
@.claude/rules/vanessa-tests-location.md
