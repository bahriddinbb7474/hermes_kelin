# fix04 — report

## Changes

### Health guard

All three `high_blood_pressure` alternatives now share this terminal pattern:

```python
HIGH_BLOOD_PRESSURE_END = (
    r"(?:баланд|юқори|кўтар)(?!\s+(?:эмас|емас)\b)"
)
```

Complete guard diff:

```diff
 # Narrow multi-word patterns. No standalone ёмон/ёрдам/дард/бемор/температура.
+HIGH_BLOOD_PRESSURE_END = (
+    r"(?:баланд|юқори|кўтар)(?!\s+(?:эмас|емас)\b)"
+)
 KEYWORD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
@@
         "high_blood_pressure",
         re.compile(
             r"\b(?:қон\s+босим(?:им)?(?:\s+\S+){0,3}\s+"
-            r"(?:баланд|юқори|кўтар)"
-            r"|босимим(?:\s+\S+){0,3}\s+(?:баланд|юқори|кўтар)"
-            r"|давлен\w*(?:\s+\S+){0,3}\s+(?:баланд|юқори|кўтар))"
+            + HIGH_BLOOD_PRESSURE_END
+            + r"|босимим(?:\s+\S+){0,3}\s+"
+            + HIGH_BLOOD_PRESSURE_END
+            + r"|давлен\w*(?:\s+\S+){0,3}\s+"
+            + HIGH_BLOOD_PRESSURE_END
+            + r")"
         ),
```

The lookahead suppresses only `эмас`/`емас` immediately after the pressure
adjective. Other triggers, normalization, numeric handling, and the
`high_blood_pressure` id remain unchanged.

### DEPLOY.md

Complete documentation diff:

```diff
 `backend/sql/001_init.sql` применяется контейнером Postgres только при первом создании volume.
 Для будущих миграций `002_*.sql` на существующей БД применять вручную:

+Применённые миграции (в порядке применения):
+
+1. `001_init` — схема и справочники.
+2. `002_stage51_quantity_budget` — количество и месячные бюджеты.
+3. `003_stage53_product_plans` — планы продуктов.
+4. `005_stage6_recurring_obligations` — повторяющиеся обязательства.
+5. `006_user_news_sources` — пользовательские источники новостей.
+6. `007_food_subcategories` — подгруппы еды: молочное, напитки, соусы,
+   полуфабрикаты.
+
+Миграция `004` в репозитории отсутствует.

 ```bash
 set -a; . backend/.env; set +a
```

## Seven guard checks

| Phrase | Expected | Actual |
|---|---|---|
| `Давлениям баланд` | `high_blood_pressure` | `high_blood_pressure` |
| `Давлениям юқори эмас` | `None` | `None` |
| `Давлениям яхши, юқори эмас` | `None` | `None` |
| `Қон босимим баланд эмас` | `None` | `None` |
| `Босимим кўтарилди` | `high_blood_pressure` | `high_blood_pressure` |
| `Давлениям бугун жуда баланд` | `high_blood_pressure` | `high_blood_pressure` |
| `Давлениям 108/67` | `None` | `None` |

Test code:

```python
def test_keyword_layer_handles_negated_russian_davlenie_variants():
    assert guard.detect_health_keyword("Давлениям баланд") == "high_blood_pressure"
    assert guard.detect_health_keyword("Давлениям юқори эмас") is None
    assert guard.detect_health_keyword("Давлениям яхши, юқори эмас") is None
    assert guard.detect_health_keyword("Қон босимим баланд эмас") is None
    assert guard.detect_health_keyword("Босимим кўтарилди") == "high_blood_pressure"
    assert (
        guard.detect_health_keyword("Давлениям бугун жуда баланд")
        == "high_blood_pressure"
    )
    assert guard.detect_health_keyword("Давлениям 108/67") is None
```

## Changed files

- `deploy/hermes_plugins/mariyam_health_guard/__init__.py`
- `deploy/DEPLOY.md`
- `tests/test_stage7_health_alerts.py`
- `tasks/luna/fix04.report.md`

## Verification

- Targeted guard and related suite: `19 passed`.
- Guard-only suite: `11 passed`.
- `py_compile` passed for the changed Python file.
- `git diff --check` passed.
- Full `pytest -q`: collection stopped with 14 known environment errors from
  the Python 3.11 `asyncpg` binary being loaded by the available Python 3.12.
  Affected tests: `test_backup_status.py`, `test_imp09_news_control.py`,
  `test_imp10_feed_discovery.py`, `test_imp11_news_sources.py`,
  `test_mariyam_effective_prompt.py`, `test_stage51_expense_analytics.py`,
  `test_stage51_monthly_budget.py`, `test_stage53_product_plans.py`,
  `test_stage53a_approval_cycle.py`, `test_stage53a_get_cycle.py`,
  `test_stage53a_open_cycle.py`, `test_stage6_daily_life.py`,
  `test_stage6_recurring_obligations.py`, and `test_stage7_admin_report.py`.
- Remaining suite with those 14 collection blockers excluded: `274 passed`.

## Commit and push

- Required commit message: `health guard: do not alert on negated high pressure; docs: list applied migrations`
- Implementation commit hash: `04b0ffa`.
- Push status: pending explicit authorization for this fix04 payload to `origin/main`.
- VPS deploy: not performed, as requested.
