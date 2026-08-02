# fix03 — report

## Done

- Replaced all 10 `isha` self-feeling questions with distinct, soft blood-
  pressure questions.
- Each new `isha` message has exactly one question mark, uses Uzbek Cyrillic
  only, asks for a measurement, and offers to record the result.
- Extended the existing `high_blood_pressure` trigger with the Russian root
  `давлен` and any Unicode-word ending, keeping the same three-word context
  window and the same `high_blood_pressure` trigger id.
- Numeric values remain deliberately outside the guard: `Давлениям 108/67`
  does not alert.
- No threshold logic, other health triggers, normalization, deduplication,
  alert persistence, admin notification, quiet gate, or non-`isha` slots were
  changed.

## The 10 new `isha` phrases

1. `Хайрли кеч, Ойижон. Хуфтон намозига оз қолди. Бугун қон босимингизни ўлчадингизми? Айтсангиз, ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.`
2. `Ассалому алайкум, Ойижон. Хуфтон вақти яқинлашди. Қон босимингизни бугун текшириб кўрдингизми? Натижасини айтсангиз, кундаликка қайд қиламан. Бирор хизмат бўлса, шу ердаман.`
3. `Хайрли кеч, Ойижон. Хуфтон намозига ўн дақиқа қолди. Бугун босимингизни ўлчашга улгурдингизми? Рақамларини айтсангиз, ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.`
4. `Ассалому алайкум, Ойижон. Хуфтонга тайёрланадиган пайт яқин. Қон босими ўлчовини бугун қилдингизми? Натижасини айтсангиз, қайд этиб қўяман. Бирор хизмат бўлса, шу ердаман.`
5. `Хайрли кеч, Ойижон. Бугунги хуфтон намози яқинлашди. Босимингизни кечқурун ўлчаб кўрдингизми? Айтганингизни кундаликка ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.`
6. `Ассалому алайкум, Ойижон. Хуфтон ибодатига оз вақт қолди. Бугунги қон босими ўлчовингиз борми? Айтсангиз, кундаликка киритиб қўяман. Бирор хизмат бўлса, шу ердаман.`
7. `Хайрли кеч, Ойижон. Хуфтон вақтига яқинлашдик. Қон босимингизни текшириб қўйдингизми? Натижасини айтсангиз, сақлаб қўяман. Бирор хизмат бўлса, шу ердаман.`
8. `Ассалому алайкум, Ойижон. Хуфтон намози учун тайёрланиб оладиган пайт бўлди. Бугун босим ҳақида ўлчов қилдингизми? Натижасини айтсангиз, қайд қиламан. Бирор хизмат бўлса, шу ердаман.`
9. `Хайрли кеч, Ойижон. Хуфтон намозига озгина қолди. Қон босимингизни ўлчаб, натижасини ёзиб қўйдингизми? Айтсангиз, мен ҳам кундаликка киритаман. Бирор хизмат бўлса, шу ердаман.`
10. `Ассалому алайкум, Ойижон. Хуфтон вақти яқин. Босим ўлчовини бугун амалга оширдингизми? Натижасини айтсангиз, ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.`

## Guard diff

```diff
             r"\b(?:қон\s+босим(?:им)?(?:\s+\S+){0,3}\s+"
             r"(?:баланд|юқори|кўтар)"
-            r"|босимим(?:\s+\S+){0,3}\s+(?:баланд|юқори|кўтар))"
+            r"|босимим(?:\s+\S+){0,3}\s+(?:баланд|юқори|кўтар)"
+            r"|давлен\w*(?:\s+\S+){0,3}\s+(?:баланд|юқори|кўтар))"
```

## Tests added

```python
def test_isha_templates_ask_about_blood_pressure_and_offer_recording():
    templates = rhythm.PRAYER_TEMPLATES["isha"]
    assert len(templates) == 10
    assert all(text.count("?") == 1 for text in templates)
    assert all("босим" in text.lower() for text in templates)
    assert all(
        any(
            marker in text.lower()
            for marker in ("айтсангиз", "қайд", "ёзиб", "кирит", "сақлаб")
        )
        for text in templates
    )
    assert all(not re.search(r"[A-Za-z0-9]", text) for text in templates)


def test_keyword_layer_accepts_russian_davlenie_without_numeric_false_alert():
    assert guard.detect_health_keyword("Давлениям баланд") == "high_blood_pressure"
    assert guard.detect_health_keyword("Давлениям 108/67") is None
```

## Changed files

- `deploy/day_rhythm/mariyam_day_rhythm.py`
- `deploy/hermes_plugins/mariyam_health_guard/__init__.py`
- `tests/test_day_rhythm.py`
- `tests/test_stage7_health_alerts.py`
- `tasks/luna/fix03.report.md`

## Verification

- Targeted command: `pytest -q tests/test_day_rhythm.py tests/test_stage7_health_alerts.py`
- Targeted result: `19 passed`.
- `py_compile` passed for all four changed Python files.
- `git diff --check` passed.
- Full `pytest -q`: collection stopped with 14 environment errors because the
  available Python 3.12 cannot load the local Hermes Python 3.11 `asyncpg`
  binary. Affected tests:
  `test_backup_status.py`, `test_imp09_news_control.py`,
  `test_imp10_feed_discovery.py`, `test_imp11_news_sources.py`,
  `test_mariyam_effective_prompt.py`, `test_stage51_expense_analytics.py`,
  `test_stage51_monthly_budget.py`, `test_stage53_product_plans.py`,
  `test_stage53a_approval_cycle.py`, `test_stage53a_get_cycle.py`,
  `test_stage53a_open_cycle.py`, `test_stage6_daily_life.py`,
  `test_stage6_recurring_obligations.py`, and `test_stage7_admin_report.py`.
- Remaining suite with those 14 collection blockers excluded: `274 passed`.

## Commit and push

- Required commit message: `day rhythm: ask about blood pressure at isha; health guard: match russian davlenie`
- Push target: `origin/main`.
- VPS deploy: not performed, as requested; Sol will handle the next VPS step.
