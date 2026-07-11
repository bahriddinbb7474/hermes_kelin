# Database

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md` (DDL всех таблиц — §13).
Реализация: `backend/sql/001_init.sql` (схема + seed категорий, идемпотентно) в ветке `feature-hermes-mariyam-mvp`; проверено тестами, включая границу суток Asia/Tashkent (`TZ_BOUNDARY_PASSED`).

## Назначение

PostgreSQL хранит точные данные. Hermes memory хранит только мягкий контекст и onboarding/cron state.

Все временные метки хранятся в UTC (`TIMESTAMPTZ`). Границы "сегодня", дня, недели, месяца и cron-время считаются в `Asia/Tashkent` (UTC+5).

## Таблицы

- `users` — Telegram ID, роль `oyijon`/`admin`, имя, язык, timezone.
- `expense_categories` — фиксированные категории и подкатегории расходов.
- `transactions` — расходы и доходы: сумма, валюта, категория, предмет, описание, source text/type, время операции.
- `quran_progress` — сура/жуз/страница/заметка и дата обновления.
- `health_notes` — заметки о самочувствии с severity, без диагноза.
- `alert_events` — срочные события: тип, severity, исходная фраза, ответ бота, `detected_by`, отправлено ли админу.
- `plan_notes` — планы, custom notes, счётчики, если их нужно хранить как факт.
- `usage_costs` — оценка стоимости STT/TTS/LLM по провайдерам.

## Что не хранить как отдельную обязательную таблицу

- Напоминания: живут в Hermes cron/profile и попадают в backup через копию профиля.
- `daily_reports`: не обязательна. Отчёт 19:30 формирует Hermes из `get_admin_report_data`. Архив `sent_reports` можно добавить позже, если понадобится.

## Миграции и seed (ТЗ §13.2)

- SQL-файлы нумерованные (`001_init.sql`, `002_*.sql`), каждый идемпотентен (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).
- `docker-entrypoint-initdb.d` применяется только при первом создании volume; последующие изменения схемы применяются вручную через `psql -f` (команда — в deploy-доке).
- До первого реального вызова tools в `users` обязателен `role=admin` (Бахриддин ака). Опционально разрешён **временный test-user** (`role=oyijon`, `display_name="Тест Ойижон"`) **только на втором аккаунте заказчика** для end-to-end тестов (ТЗ §0.4). Настоящий ID Ойижон и seed — только при handover. Создание через tool `ensure_user` или документированный SQL-seed; перед handover временный test-user и его данные удаляются.

## Валюта и суммы

Основная валюта — UZS, дополнительная — USD. Разные валюты в отчётах не смешивать без явного пояснения. Нормализацию фраз вроде "180 минг" делает Hermes до вызова tool.
