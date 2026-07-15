# Database

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md` (DDL всех таблиц — §13).
Реализация: `backend/sql/001_init.sql` + идемпотентная migration `002_stage51_quantity_budget.sql`. Migration 002 проверена offline двойным применением на чистой PostgreSQL 16 и применена на production/VPS; schema verification = **3 columns / 1 table / 1 index**. Жёсткий DB guard (`tests/db_guard.py`) блокирует destructive tests против production-БД.

**v3.12 design:** migrations 003/004/005 — **PLANNED / NOT IMPLEMENTED**. SQL-файлов и runtime tables для них нет; current schema остаётся 001+002.

## Назначение

PostgreSQL хранит точные данные. Hermes memory хранит только мягкий контекст и onboarding/cron state.

Все временные метки хранятся в UTC (`TIMESTAMPTZ`). Границы "сегодня", дня, недели, месяца и cron-время считаются в `Asia/Tashkent` (UTC+5).

## Таблицы

- `users` — Telegram ID, роль `oyijon`/`admin`, имя, язык, timezone.
- `expense_categories` — фиксированные категории и подкатегории расходов.
- `transactions` — расходы и доходы: сумма, валюта, категория, предмет, description, source, время. **Migration 002 active:** nullable `item_name_normalized`, `quantity`, `unit` (`kg|g|l|ml|pcs|pack`); unit только с quantity; quantity>0; старые rows без quantity валидны.
- `monthly_budget_plans` — **migration 002 active:** plan на `(user_id, month, category_code)`: planned_amount_uzs, note, timestamps.
- `quran_progress` — сура/жуз/страница/заметка и дата обновления.
- `health_notes` — заметки о самочувствии с severity, без диагноза.
- `alert_events` — срочные события: тип, severity, исходная фраза, ответ бота, `detected_by`, отправлено ли админу.
- `plan_notes` — планы, custom notes, счётчики, если их нужно хранить как факт.
- `usage_costs` — оценка стоимости STT/TTS/LLM по провайдерам.

### Planned tables v3.12 — не runtime

- Migration 003: `monthly_budget_items` (user/month/category/item, planned quantity/unit/amount; минимум quantity или amount; unique item per month/category) и `monthly_plan_cycles` (status, household size, source, proposal/approval metadata; unique user/month).
  Planned `monthly_budget_items` дополнительно содержит `reference_unit_price_uzs NUMERIC(14,4) NULL`, `price_basis TEXT NULL CHECK (price_basis IN ('last','average','manual'))`, `price_as_of TIMESTAMPTZ NULL`.
  История фактических цен остаётся в `transactions`; отдельную таблицу цен сейчас не создавать. `last` и weighted `average` вычисляются из подходящих transactions одного товара и одной unit. При сохранении плана фиксируется snapshot выбранной цены: новый факт покупки не меняет старый план. `planned_amount_uzs` рассчитывается из подтверждённых quantity × snapshot price либо задаётся вручную.
- Migration 004: `utility_accounts` (service, provider, masked account reference, admin-defined minimum prepaid balance, sync state) и immutable `utility_snapshots` (reading/consumption/billed/prepaid/debt/tariff/observed/source).
- Migration 005: `recurring_obligations` (internet/loan/tax/utility/other, expected amount, due date, repeat rule, reminder lead, paid/active state).
- Не хранить одновременно negative prepaid balance и separate debt без утверждённого provider rule; field normalization утверждается после исследования реального кабинета.
- Utility credentials и raw account reference в PostgreSQL запрещены; хранится только masked reference и allowlisted structured data.

## Что не хранить как отдельную обязательную таблицу

- Напоминания: живут в Hermes cron/profile и попадают в backup через копию профиля.
- `daily_reports`: не обязательна. Отчёт 19:30 формирует Hermes из `get_admin_report_data`. Архив `sent_reports` можно добавить позже, если понадобится.

## Миграции и seed (ТЗ §13.2)

- SQL-файлы нумерованные (`001_init.sql`, `002_*.sql`), каждый идемпотентен (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`). Planned numbering: 003 product plans/cycles, 004 utilities, 005 obligations; до implementation не объявлять их applied.
- `docker-entrypoint-initdb.d` применяется только при первом создании volume; последующие изменения схемы применяются вручную через `psql -f` (команда — в deploy-доке).
- До первого реального вызова tools в `users` обязателен `role=admin` (Бахриддин ака). Опционально разрешён **временный test-user** (`role=oyijon`, `display_name="Тест Ойижон"`) **только на втором аккаунте заказчика** для end-to-end тестов (ТЗ §0.4). Настоящий ID Ойижон и seed — только при handover. Создание через tool `ensure_user` или документированный SQL-seed; перед handover временный test-user и его данные удаляются.

## Валюта и суммы

Основная валюта — UZS, дополнительная — USD. Разные валюты в отчётах не смешивать без явного пояснения. Нормализацию фраз вроде "180 минг" делает Hermes до вызова tool.
