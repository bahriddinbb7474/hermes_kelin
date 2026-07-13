# Evidence — Stage 5.1 OFFLINE PASS

Дата: 2026-07-13
Статус: **OFFLINE PASS / LIVE PENDING**
Источник требований: `TZ_Hermes_Mariyam_FINAL_v3_0.md` v3.8 (§0.7–0.8)

## Scope реализации

Stage 5.1 реализован и проверен только в repo/worktree:

- идемпотентная migration `backend/sql/002_stage51_quantity_budget.sql`;
- nullable `item_name_normalized`, `quantity`, `unit` и индекс `idx_tx_item_norm`;
- item analytics, `compare_previous`, `previous_period`, `monthly_series`;
- monthly budget plan/fact: `set_monthly_budget`, `get_monthly_budget_status`;
- MCP inventory в repo: **19 → 21**;
- identity plugin repo: **1.0.4**, оба новых tools user-scoped/self-only, admin cross-target запрещён;
- SKILL-контракт аналитики/бюджета и skill-protect regression.

## Migration 002

Migration 002 проверена двойным последовательным применением на чистой PostgreSQL 16. Второе применение прошло без ошибки. Старые transactions остаются валидными; production/VPS migration **не применялась**.

## Аналитика расходов

`save_expense` поддерживает явные quantity/unit и нормализованное имя товара. `get_expense_report` возвращает факты по категориям и товарам, purchase count, quantity по units, сравнение с предыдущим периодом и календарный monthly series по Asia/Tashkent. Backend не формирует советы и прозу.

## Месячный бюджет

Реализованы category/month upsert плана и plan/fact status с planned/actual/remaining, category breakdown и usage percent. Учитываются только expense в UZS за календарный месяц Asia/Tashkent; отрицательный remaining допустим.

## Identity и SKILL

- Repo plugin: **1.0.4**.
- VPS plugin: **1.0.3** (Stage 5.1 ещё не развёрнут).
- Canonical SKILL: `skills/mariyam/SKILL.md`.
- SHA-256: `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`.
- Отдельная protected SKILL-copy в git не создаётся; защита — profile-scoped config + SHA/contract tests. Runtime-копирование только при будущем deploy.
- Skill-protect fix готов offline, но по зафиксированному Stage 5.1 deploy-state на VPS ещё не применён.

## Offline verification

```text
pytest -q:         147 passed, 2 skipped
ruff check .:      All checks passed
py_compile:        PASS
git diff --check:  PASS
runtime repo tools: 21
```

## Изменённые файлы реализации Stage 5.1

```text
backend/db.py
backend/server.py
backend/sql/002_stage51_quantity_budget.sql
deploy/hermes_plugins/mariyam_identity_guard/__init__.py
deploy/hermes_plugins/mariyam_identity_guard/plugin.yaml
skills/mariyam/SKILL.md
tests/run_tests.py
tests/test_db_guard.py
tests/test_mariyam_identity_guard.py
tests/test_mariyam_skill_protection.py
tests/test_mariyam_skill_stage51.py
tests/test_stage51_expense_analytics.py
tests/test_stage51_monthly_budget.py
deploy/hermes_profile_mariyam_oyijon/config.skill-protect.snippet.yaml
```

Документы статуса v3.8 обновлены отдельным Шагом 5; исторические evidence не переписывались.

## Не выполнялось

- VPS deploy или изменение VPS runtime;
- production migration;
- Gateway restart;
- Telegram controlled E2E/API-вызовы;
- сообщения реальной Ойижон или «Тест Ойижон»;
- commit;
- push.

## Разделение состояний

| Область | Tools | Plugin | Stage 5.1 |
|---|---:|---:|---|
| Repo/worktree | 21 | 1.0.4 | OFFLINE PASS |
| Текущий VPS runtime | 19 | 1.0.3 | NOT DEPLOYED / LIVE PENDING |

## Вердикт

**OFFLINE PASS / LIVE PENDING.** Stage 5.1 окончательно не закрыт. Live deploy и controlled E2E разрешены только отдельным решением заказчика.
