# imp01 (Opus) — Tool `approve_monthly_plan` + статусы цикла (Stage 5.3A, шаг 2)

## Контекст
Repo `main` (после `055c135`). Backend — MCP tools/storage, PostgreSQL,
migration 003 уже создала `monthly_plan_cycles` (status, household size, source,
proposal/approval metadata; unique user/month) и `monthly_budget_items`.
Требования — ТЗ `docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md`, раздел «Этап 5.3A»
(~стр. 1484) и «Stage 5.3A (+1 → planned 22)» (~стр. 1243).
Identity обеспечивает guard 1.1.0 (cron + Telegram): backend получает уже
доверенный `user_id`. Cross-run idempotency — ответственность ЭТОГО tool и
unique constraints (решение заказчика 2026-07-23, DECISIONS.md).

## Что сделать
1. Сначала контракт в `docs/TZ/TOOLS_CONTRACTS.md` (раздел Stage 5.3A):
   параметры, результат, error codes, полная детерминированная state machine
   статусов: `draft → waiting_oyijon → waiting_admin →
   approved_by_oyijon | approved_by_admin | auto_approved`.
2. Реализовать в backend user-scoped tool `approve_monthly_plan`:
   - работает только ДО начала планового месяца (Asia/Tashkent); после начала —
     детерминированный отказ;
   - transactions/расходы не читает на запись и не изменяет;
   - Ойижон — self-only; admin — только target из `allowed_target_user_ids`
     через отдельный narrow allowlist и только future month;
   - изменение сумм допустимо только future month и разрешённый target;
     это НЕ даёт update/delete transactions;
   - пустой/corrupt draft не approve (валидация до записи);
   - idempotency: повторный approve того же месяца → тот же результат без
     второй записи/дублей (unique user/month + проверка текущего status);
     недопустимый переход статуса → отказ с кодом, без мутации;
   - `auto_approved` устанавливается этим же tool (source=`auto`) — использует
     его будущий cron job «1 число»: valid draft → approve; нет draft →
     copy last approved plan; нет и прошлого → отказ `NO_PLAN_SOURCE`
     (уведомление админа — задача cron prompt, не backend).
3. Inventory/dispatch/discovery 21 → 22 синхронно (tool виден и вызываем);
   тест на count обновить.
4. Тесты: state machine полностью (все допустимые и все недопустимые переходы),
   идемпотентность повторного вызова, границы месяца (последний день/первое
   число), self-only/чужой target, admin narrow allowlist, corrupt draft.
   Существующие suites не ломать.
5. Доки минимально: TOOLS_CONTRACTS.md, DATABASE.md (если добавятся
   constraints/индексы — только через новую migration 004, если реально нужно;
   существующие миграции не редактировать), README/ROADMAP: repo tool count 22,
   deployed 21 (deploy отдельно).

## Запрещено
Менять Hermes core, plugins, SOUL; создавать cron jobs; трогать transactions;
менять существующие 21 tools кроме регистрации 22-го.

## Отчёт
- `tasks/opus/imp01.report.md`: контракт (кратко), изменённые файлы, полный
  вывод тестов, hash коммитов.
- Commit(ы) поимённо + push: `feat: approve_monthly_plan tool and cycle statuses (5.3A)`.
- В чат заказчику: 2–3 предложения простым русским.
