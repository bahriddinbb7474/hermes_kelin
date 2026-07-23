# imp01 (Opus) — отчёт: `approve_monthly_plan` + статусы цикла (Stage 5.3A, шаг 2)

## Что сделано
Реализован user-scoped backend tool `approve_monthly_plan` с детерминированной
state machine цикла месячного плана поверх готовой схемы `monthly_plan_cycles`
(migration 003). Новая migration 004 **не потребовалась** — существующая схема
(status/source CHECK, unique `user/month`, household/approval metadata) достаточна.
Repo inventory 21 → **22**; deployed на VPS остаётся 21 (backend deploy отдельно).

## Контракт (кратко)
Вход: `user_id`, `month` (`YYYY-MM-01`), `source` ∈ `oyijon|admin|auto`; optional
`approved_by_user_id`, `household_size`. Выход (ok): `month, status, source,
household_size, approved_by_user_id, approved_at, idempotent, plan_copied`.

State machine (`monthly_plan_cycles.status`):
- non-terminal `draft|waiting_oyijon|waiting_admin` → target по approval source:
  `oyijon→approved_by_oyijon`, `admin→approved_by_admin`, `auto→auto_approved`.
- `current == target` → идемпотентный replay (без второй записи, `approved_at`
  не переписывается), допустим даже после начала месяца (retry/cron safety).
- `current ∈ terminal и != target` → `INVALID_STATUS_TRANSITION`, без мутации.

Границы месяца (Asia/Tashkent, до записи):
- ручное (`oyijon`/`admin`) — только строго ДО начала месяца, иначе
  `MONTH_ALREADY_STARTED`;
- `auto` (cron «1 число») — только в 1-й календарный день: раньше
  `MONTH_NOT_STARTED`, позже `MONTH_ALREADY_STARTED`.

Валидность/источник плана:
- valid draft = ≥1 строка `monthly_budget_plans` за месяц с `SUM(planned) > 0`;
  пустой/нулевой → `EMPTY_DRAFT`.
- `auto`: valid draft → approve; нет cycle-строки → copy последнего approved
  месяца (`monthly_budget_plans` + `monthly_budget_items`, `plan_copied:true`,
  origin `copied_previous`); нет draft и нет прошлого → `NO_PLAN_SOURCE`.
- ручное без cycle-строки → `NO_DRAFT`.

Identity rails (backend-уровень, дублируют identity guard):
`SELF_ONLY_VIOLATION` (oyijon с чужим approved_by), `ADMIN_TARGET_REQUIRED`
(admin без target / target==self), `INVALID_APPROVER` (auto с approved_by).
Проверка `allowed_target_user_ids` — на стороне identity guard.

transactions не читаются на запись и не изменяются; суммы плана этот tool не
редактирует (остаётся `set_monthly_budget`); единственная запись плановых сумм —
copy последнего approved при `auto`. `now` инъектируется только в тестах (не в
MCP schema), поэтому LLM не может подделать время.

## Изменённые файлы
- `backend/db.py` — `approve_monthly_plan` + хелперы (`_plan_is_valid`,
  `_last_approved_month`, `_copy_plan`, `_cycle_result`, `APPROVAL_SOURCES`).
- `backend/server.py` — dispatch `t_approve_monthly_plan`, `CYCLE_ERRORS`
  (ru/uz), params `source|approved_by_user_id|household_size`, TOOLS entry.
- `tests/test_stage53a_approval_cycle.py` — новый suite (state machine, границы,
  идемпотентность, self-only/admin target, corrupt draft, auto copy, MCP-mapping).
- Обновлён count 21→22: `tests/run_tests.py` (+ expected names),
  `tests/test_mariyam_effective_prompt.py`, `tests/test_stage51_expense_analytics.py`,
  `tests/test_stage51_monthly_budget.py`, `tests/test_stage53_product_plans.py`,
  `tests/test_mariyam_cron_identity_guard.py`.
- Доки: `docs/TZ/TOOLS_CONTRACTS.md` (полный контракт + state machine + коды),
  `docs/TZ/DATABASE.md`, `README.md`, `docs/ROADMAP.md`.

## Тесты (полный прогон, локальный disposable PostgreSQL `hermes_test`)
Окружение: `APP_ENV=test`, `DATABASE_URL=…/hermes_test` (docker `postgres:16-alpine`).

```
ruff check backend/ tests/ → All checks passed!

pytest tests/ -q → 293 passed in 32.85s
  (в т.ч. tests/test_stage53a_approval_cycle.py → 26 passed)

python tests/run_tests.py →
  ALL_TOOL_TESTS_PASSED
  TZ_BOUNDARY_PASSED
  POOL_STABLE_PASSED
  MCP_SMOKE_PASSED
```

Ранее (без DB) DB-интеграционные тесты корректно `skip`; count/schema-тесты
всегда выполняются. Тестовая БД поднималась только локально; production БД/VPS
не затрагивались (жёсткий `tests/db_guard.py` запрещает destructive против `hermes`).

## Что НЕ сделано (сознательно, вне рамок задачи)
- Backend deploy на VPS (deployed остаётся 21) — отдельный шаг.
- Production cron jobs 25/27/28/1, private mapping, prompt для draft-генерации и
  admin-уведомлений (`NO_PLAN_SOURCE`) — не backend, PLANNED.
- Редактирование сумм плана внутри этого tool не реализовано: интерпретировано как
  зона `set_monthly_budget` (Oyijon self-only, future month); tool не расширяет
  update/delete transactions. Открытый вопрос для ревью — при желании перенести
  amount-adjustment в approve.

## Коммит
`feat: approve_monthly_plan tool and cycle statuses (5.3A)` — hash: 9f3504b
