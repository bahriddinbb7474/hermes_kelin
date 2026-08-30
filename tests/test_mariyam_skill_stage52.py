"""Permanent text-level contract for Mariyam Stage 5.2 report decisions.

SOUL v2 (imp04, 2026-07-28) сжал промпт: таблица решений стала четырьмя
блоками `**…**`, но сами правила (какой tool, какие заголовки таблиц, где
дословная финальная фраза) остались теми же — их ломали живые баги 5.2.
"""

from pathlib import Path


PROMPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "SOUL.md"
)
HEADING = "### 5.2. Отчёты — контракт формата"
FINAL_PHRASE = (
    "Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб "
    "чиқамиз. Маълумотлар тайёр."
)
SUMMARY_TABLE = "Харажат гуруҳи | Режа | Сарфлангани | Қолгани"
ITEMS_TABLE = "Маҳсулот | Миқдор | Сарфлангани"


def _section() -> str:
    text = PROMPT.read_text(encoding="utf-8")
    assert text.count(HEADING) == 1
    return text.split(HEADING, 1)[1].split("\n### 5.3.", 1)[0]


def _decision_block(marker: str) -> str:
    """One `**…**` block of the decision list, without the following blocks."""
    section = _section()
    assert section.count(f"`{marker}`") == 1
    tail = section.split(f"`{marker}`", 1)[1]
    return tail.split("\n\n**", 1)[0]


def test_report_decision_table_has_all_supported_intents_and_tools():
    section = _section()
    for marker in (
        "GENERAL_FAMILY_REPORT",
        "CATEGORY_DETAIL",
        "COMPARE_OR_TREND",
        "SET_MONTHLY_BUDGET",
    ):
        assert section.count(marker) == 1
    assert "только\n`get_monthly_budget_status`" in section
    assert "`get_expense_report`" in section
    assert "`set_monthly_budget`" in section


def test_general_report_has_plan_spent_remaining_and_no_automatic_items():
    section = _section()
    assert SUMMARY_TABLE in section
    assert "Товарные строки автоматически не показывай" in section
    assert "только после" in section.lower()
    assert section.count(FINAL_PHRASE) == 1


def test_report_completion_depends_on_report_type_not_total_row():
    section = _section()
    general_block = _decision_block("GENERAL_FAMILY_REPORT")
    category_block = _decision_block("CATEGORY_DETAIL")

    assert "можно `Жами`" in general_block
    assert "завершить дословной фразой ниже" in general_block
    assert "можно `Жами`" in category_block
    assert "После таблиц завершить ответ" in category_block
    assert "финальную фразу общего отчёта не писать" in category_block
    assert "вопросов не задавать" in category_block
    assert "Наличие `Жами` никогда не определяет" in section


def test_general_final_phrase_is_not_a_category_detail_suffix():
    section = _section()
    category_block = _decision_block("CATEGORY_DETAIL")

    assert section.count(FINAL_PHRASE) == 1
    assert FINAL_PHRASE not in category_block
    assert "Общий отчёт всегда заверши дословно" in section


def test_category_detail_has_summary_before_actual_items():
    category_block = _decision_block("CATEGORY_DETAIL")
    assert category_block.index(SUMMARY_TABLE) < category_block.index(ITEMS_TABLE)
    assert (
        "Summary категории выводи только\nотдельной Markdown-таблицей"
        in category_block
    )
    assert "минимум с одной строкой выбранной категории" in category_block
    assert "маркированный список вместо\nsummary-таблицы запрещён" in category_block
    assert (
        "Сразу после summary-таблицы выведи таблицу фактических\nтоваров"
        in category_block
    )
    assert "quantity только из tool result, иначе\n`—`" in category_block
    assert "только её фактические `by_item`" in category_block


def test_category_detail_has_one_short_two_table_example():
    section = _section()
    example = section.split("Короткий правильный пример подробного отчёта:", 1)[1]
    assert example.index(SUMMARY_TABLE) < example.index(ITEMS_TABLE)
    assert "| Озиқ-овқат | 500 000 сўм | 221 000 сўм | 279 000 сўм |" in example
    assert "| Тухум | 12 та | 36 000 сўм |" in example


def test_group_mapping_missing_plan_and_negative_remaining_are_explicit():
    section = _section()
    for group in ("Озиқ-овқат", "Дори-дармон", "Коммунал", "Уй", "Бошқа"):
        assert group in section
    # imp12-opus: reworded to remove the fix12-terra-flagged internal
    # contradiction (a plan-less line vs. a plan-less group both claimed
    # `айтилмаган`); the two cases are now stated as one condition each,
    # in the opposite but unambiguous order.
    assert "конкретная строка пуста — `айтилмаган`, не `0`" in section
    assert "плана по группе нет вообще — колонки `Режа` и `Қолгани` не выводи" in section
    assert "Отрицательный остаток" in section
    assert "Режадан 50 000 сўм кўп сарфланди." in section


def test_units_are_global_ta_only_and_stage52_detail_stays_actual_only():
    text = PROMPT.read_text(encoding="utf-8")
    assert text.count("pcs → та") == 1
    assert "дона" not in text
    assert "product plan не показывай" in _section()
    assert "### 5.3. Месячный план по продуктам" in text


def test_old_conflicting_report_instructions_are_absent():
    text = PROMPT.read_text(encoding="utf-8")
    assert "внутри питания — товары" not in text
    assert "разбивку category/item" not in text
    assert "get_expense_report` с\n   `user_id: 0`, `period=month`" not in text
