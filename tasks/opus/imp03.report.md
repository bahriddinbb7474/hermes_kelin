# imp03 (Opus) — отчёт: tool `open_monthly_plan_cycle` (вариант A)

## Что сделано
Добавлен user-scoped backend tool `open_monthly_plan_cycle` — узкая мутация
статуса цикла, которой не было у `approve_monthly_plan` (разблокировка imp02,
вариант A). Пишет **только** строку `monthly_plan_cycles`; `monthly_budget_plans`,
`monthly_budget_items`, `transactions` не трогает. Новой migration не потребовалось
(статусы `waiting_oyijon`/`waiting_admin` уже в CHECK migration 003). Контракт и
поведение `approve_monthly_plan` **не менялись** (дефектов связка не вскрыла).
Repo inventory 22 → **23**; deployed остаётся 21 (deploy — imp02).

## Контракт (кратко)
`open_monthly_plan_cycle(user_id, month, action, household_size?)`,
`action ∈ {open, escalate}`. Ok: `{month, status, source, household_size,
idempotent, created}`.

- `open`: нет строки → создать `waiting_oyijon` (`source=calculated`,
  `created:true`), future month (Asia/Tashkent, строго до начала), нужен valid
  budget draft (та же валидация, что `EMPTY_DRAFT` в approve). Строка любого
  статуса уже есть → идемпотентно (`idempotent:true`, `created:false`), без
  дублей и мутации.
- `escalate`: `draft`/`waiting_oyijon` → `waiting_admin` (future month); уже
  `waiting_admin` → идемпотентный no-op; terminal → `INVALID_STATUS_TRANSITION`;
  нет строки → `NO_DRAFT`. При отказе — без мутации.
- Коды: `MONTH_ALREADY_STARTED`, `EMPTY_DRAFT`, `INVALID_STATUS_TRANSITION`,
  `NO_DRAFT` (+ `INVALID_INPUT` на bad `action`/`household_size`).
- Identity (Oyijon self-only, admin narrow cross-target, cron trusted job) —
  на стороне identity guard 1.1.0.

## Изменённые файлы
- `backend/db.py` — `open_monthly_plan_cycle` + `CYCLE_ACTIONS`, `_open_result`.
- `backend/server.py` — dispatch `t_open_monthly_plan_cycle` (reuse `CYCLE_ERRORS`),
  param `action`, TOOLS entry, DISPATCH.
- `tests/test_stage53a_open_cycle.py` — новый suite (open/escalate, границы,
  idempotent, duplicate rows = 0, no budget/tx side effects, связка с approve).
- Count 22→23: `tests/run_tests.py` (+ expected names),
  `tests/test_mariyam_effective_prompt.py`, `tests/test_stage51_expense_analytics.py`
  (+ new_tools set), `tests/test_stage51_monthly_budget.py`,
  `tests/test_stage53_product_plans.py`, `tests/test_mariyam_cron_identity_guard.py`,
  `tests/test_stage53a_approval_cycle.py`.
- Доки: `docs/TZ/DECISIONS.md` (решение 2026-07-24, вариант A),
  `docs/TZ/TOOLS_CONTRACTS.md`, `docs/TZ/DATABASE.md`, `README.md`, `docs/ROADMAP.md`.

## Тесты (полный прогон, disposable PostgreSQL `hermes_test`)
Окружение: `APP_ENV=test`, `DATABASE_URL=…/hermes_test` (docker `postgres:16-alpine`).

```
ruff check backend/ tests/ → All checks passed!

pytest tests/ -q → 316 passed in 48.31s
  (в т.ч. tests/test_stage53a_open_cycle.py → 23 passed)

python tests/run_tests.py →
  ALL_TOOL_TESTS_PASSED
  TZ_BOUNDARY_PASSED
  POOL_STABLE_PASSED
  MCP_SMOKE_PASSED
```

Тестовая БД поднималась только локально; production БД/VPS не затрагивались.

## Что НЕ сделано (по рамкам задачи)
Deploy (это imp02); Hermes core/plugins/SOUL, transactions, контракт
`approve_monthly_plan` — не менялись; production cron jobs/mapping не создавались.

## Коммит
`feat: open_monthly_plan_cycle tool for approval cycle (5.3A)` — hash: a89f73f
