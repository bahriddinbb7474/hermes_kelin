"""Permanent canonical SOUL contract for Stage 5.3 product planning.

SOUL v2 (imp04, 2026-07-28): раздел сжат — подробный сценарий цикла живёт в
cron-промптах 25/27/28/1a, а в SOUL остались правила, которые ломались в живых
прогонах: один вопрос за сообщение, цены только из read-only lookup, никакого
`set_monthly_budget` до подтверждения, точные имена полей, трёхколоночный отчёт
и flow короткого «ха» → `approve_monthly_plan`.
"""
from pathlib import Path

PROMPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "SOUL.md"
)
STAGE53_HEADING = "### 5.3. Месячный план по продуктам"
CATEGORY_HEADER = "Харажат гуруҳи | Режа | Сарфлангани | Қолгани"
PRODUCT_HEADER = "Маҳсулот | Режа: миқдор / сумма | Амалда: миқдор / сумма"
OLD_FIVE_COLUMN = (
    "Маҳсулот | Режа миқдор | Режа сўм | "
    "Сарфланган миқдор | Сарфланган сўм | Қолди сўм"
)


def _text() -> str:
    return PROMPT.read_text(encoding="utf-8")


def _stage53() -> str:
    text = _text()
    assert text.count(STAGE53_HEADING) == 1
    return text.split(STAGE53_HEADING, 1)[1].split("\n### 5.4.", 1)[0]


def test_stage52_decision_table_and_completion_contract_remain_present():
    text = _text()
    for marker in (
        "GENERAL_FAMILY_REPORT",
        "CATEGORY_DETAIL",
        "COMPARE_OR_TREND",
        "SET_MONTHLY_BUDGET",
    ):
        assert marker in text
    assert CATEGORY_HEADER in text
    assert (
        "Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ "
        "кўриб чиқамиз. Маълумотлар тайёр."
    ) in text


def test_dialog_is_strictly_sequential_and_draft_first():
    text = _text()
    section = _stage53()
    # Правило «один вопрос» стало общим правилом тона (§2) и действует всегда.
    assert "бир хабарда фақат битта савол" in text
    assert "по одному вопросу за\nсообщение" in section
    assert "уже сказанное не\nпереспрашивай" in section
    assert "не вызывай `set_monthly_budget`" in section
    assert "До явного\nподтверждения draft" in section


def test_price_choice_requires_read_only_lookup_before_draft():
    section = _stage53()
    lookup = "price_lookup_items"
    assert lookup in section
    assert "get_monthly_budget_status" in section
    assert "user_id: 0" in section
    assert "month" in section
    assert "item_name_normalized" in section
    assert "price_basis: last|average" in section
    assert "Цены бери только из" in section
    assert "вернулся `null` — задай один вопрос про цену и не сохраняй" in section


def test_confirmed_product_payload_uses_exact_contract_fields_and_never_drops_items():
    section = _stage53()
    for field in (
        "`item_name_normalized`",
        "`item_name_display`",
        "`planned_quantity`",
        "`unit`",
        "`planned_amount_uzs`",
        "`reference_unit_price_uzs`",
        "`price_basis`",
        "`price_as_of`",
    ):
        assert field in section
    assert "aliases `item_name`, `quantity`, `price_uzs`\nзапрещены" in section
    assert "`items: []` запрещён" in section
    assert "ровно один вызов" in section
    assert "повторный mutating call после успешного save\nзапрещён" in section


def test_oyijon_output_contract_forbids_ascii_letters():
    text = _text()
    assert "ASCII letters `[A-Za-z]`" in text
    assert "ответ ошибочный" in text


def test_financial_flow_forbids_terminal_and_execute_code():
    section = _stage53()
    assert "Арифметику считает backend" in section
    for marker in ("execute_code", "terminal", "калькулятор"):
        assert marker in section
    assert "запрещены" in section


def test_stage53_dialog_has_required_sequential_fields():
    section = _stage53()
    required = (
        "месяц",
        "сколько человек в семье",
        "группа",
        "что есть дома",
        "что нужно",
        "количество по одному продукту",
        "бюджет",
        "способ цены",
    )
    positions = [section.index(marker) for marker in required]
    assert positions == sorted(positions)


def test_dead_nutrition_web_search_directive_is_gone():
    # imp04: web_search не сконфигурирован в профиле — обещать поиск нельзя.
    text = _text()
    for dead in (
        "Nutrition search",
        "максимум один web search на plan cycle",
        "cache 30 дней",
        "WHO",
        "FAO",
    ):
        assert dead not in text
    # Медицинские ограничения остаются, но живут в разделе безопасности.
    assert "## 10. Медицинская безопасность" in text
    assert "не назначать" in text or "менять или отменять лекарства" in text


def test_stage53_detailed_report_uses_exact_three_column_table():
    section = _stage53()
    assert "get_monthly_budget_status(include_items=true)" in section
    assert f"`{PRODUCT_HEADER}`" in section
    assert "summary-таблица групп" in section
    assert section.index("summary-таблица групп") < section.index(PRODUCT_HEADER)
    assert OLD_FIVE_COLUMN not in section


def test_stage53_unknown_values_units_and_no_technical_fields():
    text = _text()
    section = _stage53()
    assert "`—`" in section
    assert "`айтилмаган`" in section
    assert "ничего не угадывай" in section
    for mapping in (
        "kg → кг",
        "g → г",
        "l → л",
        "ml → мл",
        "pcs → та",
        "pack → қадоқ",
    ):
        assert mapping in text
    assert "дона" not in text
    assert "JSON" in text and "tool names" in text


def test_stage53a_approval_flow_enabled_and_self_only():
    # Stage 5.3A: «ха» → сначала get_monthly_plan_cycle, потом approve.
    section = _stage53()
    assert "get_monthly_plan_cycle" in section
    assert "approve_monthly_plan" in section
    assert "source=oyijon" in section
    assert "25 — черновик" in section
    assert "«ха»" in section
    assert "cron" in section
    assert "сначала инструмент, потом интерпретация" in section
    assert "waiting_oyijon" in section
    assert "не реализованы" not in section
