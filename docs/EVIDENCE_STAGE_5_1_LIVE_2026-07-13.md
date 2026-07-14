# Evidence — Stage 5.1 LIVE PASS

Дата live acceptance: 2026-07-13
Документальное закрытие: 2026-07-14
Статус: **CLOSED / LIVE PASS**
Источник требований: `docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md` v3.9 (§0.7–0.9, §21 Stage 5.1)

## Runtime и schema

- Production migration `002_stage51_quantity_budget.sql` применена.
- Schema 002: **3 columns / 1 table / 1 index** (`item_name_normalized`, `quantity`, `unit`; `monthly_budget_plans`; `idx_tx_item_norm`).
- Backend inventory / dispatch / реальный MCP discovery: **21 / 21 / 21**.
- Identity plugin runtime: **1.0.4**.
- Canonical SKILL SHA-256: `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`.
- Skill-protect: **4/4**; `tool_progress` выключен.
- Gateway `active`/`enabled`, один процесс; PostgreSQL `healthy`.
- Hermes v0.18.2, Hermes core и его venv не изменялись; архитектура осталась Hermes-first.

## Controlled Telegram E2E

Тест выполнен только на временном test-user «Тест Ойижон», по одному сообщению.
Реальная Ойижон не подключалась и сообщений не получала.

Подтверждено:

- quantity/unit: **2 kg** и **6 pcs** сохранены как структурированные значения;
- item analytics для расходов;
- сравнение с предыдущим месяцем;
- трёхмесячный trend;
- monthly budget **plan/fact**: план 500 000 UZS, факт 180 000 UZS, остаток 320 000 UZS, использование 36%;
- ответы — только узбекская кириллица;
- tool traces в Telegram отсутствовали;
- identity binding: новые записи и budget plan принадлежали только test-user; данные admin не изменились.

## Provider budget

- Модель: только `gpt-5.6-luna` через n1n.
- Provider requests: **6 из разрешённых 7**.
- Retry: **0**.
- Exact cost по usage journal: **$0.222808**.
- Dashboard: balance `$155.32 → $155.10`, historical spend `$14.88 → $15.10`; отображаемая delta **$0.22**.
- Сырые token values, username и иные идентификаторы в evidence не сохраняются.

## Cleanup и финальный baseline

Точечный cleanup удалил только созданные E2E transactions и budget plan.
Временный test-user сохранён для следующих pre-handover этапов, но его DB baseline восстановлен:

- admin: **8 transactions / expense 768000 / income 0**;
- test-user: **1 transaction / expense 12000 / income 0**;
- test-user monthly budget plans: **0**.

После cleanup Gateway остался active, PostgreSQL healthy, runtime inventory **21**, plugin **1.0.4**, canonical SKILL и skill-protect без drift. `/opt/time-agent` не изменялся.

## Вердикт

**Stage 5.1 — CLOSED / LIVE PASS.** Quantity/unit, analytics, previous-month comparison, three-month trend, monthly budget plan/fact и identity подтверждены controlled live E2E. Дополнительные правки Stage 5.1 не требуются.
