"""Permanent text-level contract for Mariyam Stage 5.2 decision table."""

from pathlib import Path


PROMPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "SOUL.md"
)
HEADING = "### 3.2. Таблица решений по отчётам — единственный контракт"
FINAL_PHRASE = (
    "Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб "
    "чиқамиз. Маълумотлар тайёр."
)


def _section() -> str:
    text = PROMPT.read_text(encoding="utf-8")
    assert text.count(HEADING) == 1
    return text.split(HEADING, 1)[1].split("\n### 3.3.", 1)[0]


def test_report_decision_table_has_all_supported_intents_and_tools():
    section = _section()
    for marker in (
        "GENERAL_FAMILY_REPORT",
        "CATEGORY_DETAIL",
        "COMPARE_OR_TREND",
        "SET_MONTHLY_BUDGET",
    ):
        assert section.count(marker) == 1
    assert "Только `get_monthly_budget_status`" in section
    assert "`get_expense_report`" in section
    assert "`set_monthly_budget`" in section


def test_general_report_has_plan_spent_remaining_and_no_automatic_items():
    section = _section()
    assert "Харажат гуруҳи | Режа | Сарфлангани | Қолгани" in section
    assert "Товарные строки автоматически не показывай" in section
    assert "только после" in section.lower()
    assert section.count(FINAL_PHRASE) == 1


def test_category_detail_has_summary_before_actual_items():
    section = _section()
    summary = "Харажат гуруҳи | Режа | Сарфлангани | Қолгани"
    items = "Маҳсулот | Миқдор | Сарфлангани"
    category_row = next(
        line for line in section.splitlines() if "`CATEGORY_DETAIL`" in line
    )
    assert category_row.index(summary) < category_row.index(items)
    assert "summary категории выводи только отдельной Markdown-таблицей" in category_row
    assert "минимум одной строкой выбранной категории" in category_row
    assert "Маркированный список вместо summary-таблицы запрещён" in category_row
    assert (
        "Сразу после summary-таблицы выведи таблицу фактических товаров"
        in category_row
    )
    assert "quantity только из tool result, иначе `—`" in category_row
    assert "только её фактические `by_item`" in section


def test_category_detail_has_one_short_two_table_example():
    section = _section()
    example = section.split("Короткий правильный пример подробного отчёта:", 1)[1]
    summary = "Харажат гуруҳи | Режа | Сарфлангани | Қолгани"
    items = "Маҳсулот | Миқдор | Сарфлангани"
    assert example.index(summary) < example.index(items)
    assert "| Озиқ-овқат | 500 000 сўм | 221 000 сўм | 279 000 сўм |" in example
    assert "| Тухум | 12 та | 36 000 сўм |" in example


def test_group_mapping_missing_plan_and_negative_remaining_are_explicit():
    section = _section()
    for group in ("Озиқ-овқат", "Дори-дармон", "Коммунал", "Уй", "Бошқа"):
        assert group in section
    assert "План отсутствует —\n`айтилмаган`, не `0`" in section
    assert "Отрицательный остаток" in section
    assert "Режадан 50 000 сўм кўп сарфланди." in section


def test_units_are_global_ta_only_and_product_plan_is_forbidden():
    text = PROMPT.read_text(encoding="utf-8")
    assert text.count("pcs → та") == 1
    assert "дона" not in text
    assert "Product plan не показывай" in _section()
    assert "не начинай Stage 5.3" in _section()


def test_old_conflicting_report_instructions_are_absent():
    text = PROMPT.read_text(encoding="utf-8")
    assert "внутри питания — товары" not in text
    assert "разбивку category/item" not in text
    assert "get_expense_report` с\n   `user_id: 0`, `period=month`" not in text