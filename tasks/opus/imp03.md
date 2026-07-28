# imp03 (Opus) — Tool `open_monthly_plan_cycle` (вариант A, разблокировка imp02)

## Контекст
Repo `main` (после `61162f6`). Твой STOP-отчёт imp02 принят, заказчик утвердил
вариант A: jobs 25/28 получают единственную узкую cycle-мутацию (без каких-либо
прав на расходы/transactions), 27 остаётся read-only. Новый user-scoped tool
`open_monthly_plan_cycle`, tool count repo 22 → 23 (deployed пока 21).
Базис: контракт `approve_monthly_plan` в `docs/TZ/TOOLS_CONTRACTS.md`,
state machine цикла, `backend/db.py:1187+`.

## Что сделать
1. DECISIONS.md: зафиксировать уточнение решения заказчика (2026-07-24,
   вариант A) — формулировка из imp02.report.md.
2. Контракт в TOOLS_CONTRACTS.md (перед имплементацией):
   - `open_monthly_plan_cycle(user_id, month, action, household_size?)`;
   - `action=open`: создать строку цикла `waiting_oyijon` для future month
     (Asia/Tashkent, строго до начала месяца); требует valid budget draft
     (та же валидация, что `EMPTY_DRAFT` в approve); существующая строка
     любого статуса → идемпотентный ответ `already_exists` без мутации;
   - `action=escalate`: переход `waiting_oyijon → waiting_admin`; из любого
     другого статуса — идемпотентный no-op (если уже `waiting_admin`) или
     `INVALID_STATUS_TRANSITION` (terminal), без мутации;
   - никаких записей в `monthly_budget_plans`/`monthly_budget_items`/
     `transactions`; только строка `monthly_plan_cycles`;
   - error codes в стиле существующих (`MONTH_ALREADY_STARTED`, `NO_DRAFT`,
     `EMPTY_DRAFT`, `INVALID_STATUS_TRANSITION`, ...);
   - identity: Ойижон self-only; admin cross-target — target из
     `allowed_target_user_ids`; cron — trusted mapping (guard 1.1.0 уже умеет).
3. Имплементация в `backend/db.py` + регистрация в `backend/server.py`;
   inventory/dispatch/discovery 22 → 23 синхронно; count-тесты обновить.
4. Тесты: open (future/started month, no draft/empty draft, повтор → idempotent,
   duplicate rows = 0), escalate (из каждого статуса), связка с
   `approve_monthly_plan` (open → «ха»-approve; open → escalate → admin approve;
   open → auto на 1-е число). Существующие suites не ломать.
5. Доки минимально: README/ROADMAP (repo 23 / deployed 21), DATABASE.md если
   нужны constraints (только через новую миграцию, существующие не править).

## Запрещено
Deploy (это imp02); менять Hermes core/plugins/SOUL; трогать transactions;
менять контракт/поведение `approve_monthly_plan`, кроме случая если тесты
связки вскроют дефект — тогда описать в отчёте и минимально исправить.

## Отчёт
`tasks/opus/imp03.report.md`: контракт кратко, полный тестовый прогон
(disposable PostgreSQL, как в imp01), hash коммитов. Commit поимённо + push:
`feat: open_monthly_plan_cycle tool for approval cycle (5.3A)`.
В чат заказчику: 2–3 предложения простым русским.
