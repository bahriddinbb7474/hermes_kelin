"""Permanent canonical SOUL contract for Stage 5.3 product planning."""
from pathlib import Path

PROMPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "SOUL.md"
)
STAGE53_HEADING = "### 3.3. Stage 5.3 — продуктовый месячный план"
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
    return text.split(STAGE53_HEADING, 1)[1].split("\n### 3.4.", 1)[0]


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
    section = _stage53()
    assert "бир хабарда фақат битта савол" in section
    assert "повторно не спрашивай" in section
    assert "Если quantity неизвестно, задай один уточняющий" in section
    assert "draft" in section
    assert "явного подтверждения" in section
    assert "не вызывай `set_monthly_budget`" in section
    assert "исправленный draft" in section
    assert "снова получи подтверждение" in section


def test_price_choice_requires_read_only_lookup_before_draft():
    section = _stage53()
    lookup = "price_lookup_items"
    assert lookup in section
    assert "get_monthly_budget_status" in section
    assert "user_id: 0" in section
    assert "month" in section
    assert "item_name_normalized" in section
    assert "unit" in section
    assert section.index(lookup) < section.index("полный draft")
    assert "Draft формируй только из результата этого tool" in section
    assert "lookup вернул `null`" in section
    assert "один вопрос о manual price" in section
    assert "не сохраняй plan" in section


def test_confirmed_product_payload_uses_exact_contract_fields_and_never_drops_items():
    section = _stage53()
    required_fields = (
        '"item_name_normalized": "кир совуни"',
        '"item_name_display": "Кир совуни"',
        '"planned_quantity": 5',
        '"unit": "pcs"',
        '"planned_amount_uzs": 60000',
        '"reference_unit_price_uzs": 12000',
        '"price_basis": "last"',
        '"price_as_of":',
    )
    assert all(field in section for field in required_fields)
    assert "никогда не заменяй подтверждённые товары на `items: []`" in section
    assert "не сохраняй category-only plan" in section
    assert "ровно один вызов `set_monthly_budget`" in section
    assert "сразу прекрати tool loop" in section


def test_oyijon_output_contract_forbids_ascii_letters():
    text = _text()
    assert "ASCII letters `[A-Za-z]`" in text
    assert "ответ Ойижон считается ошибочным" in text


def test_financial_flow_forbids_terminal_and_execute_code():
    section = _stage53()
    for marker in ("execute_code", "terminal", "shell", "Python"):
        assert marker in section
    assert "запрещено" in section
    assert "quantity × confirmed reference price" in section
    assert "command approval" in section


def test_stage53_dialog_has_required_sequential_fields():
    section = _stage53()
    required = (
        "На какой месяц",
        "На сколько членов семьи",
        "Какая группа расходов",
        "Какие продукты уже есть дома",
        "Какие продукты нужны семье",
        "Для одного продукта за сообщение уточняй только его количество",
        "Сначала уточни бюджет",
        "полный draft",
    )
    positions = [section.index(marker) for marker in required]
    assert positions == sorted(positions)
    assert "Только после ответа отдельным сообщением уточни способ цены" in section
    assert "последнюю, средневзвешенную или вручную названную" in section


def test_nutrition_search_and_medical_limits_are_explicit():
    section = _stage53()
    assert "Web search выполняй только если нужны практические рекомендации" in section
    assert "максимум один web search на plan cycle" in section
    assert "cache 30 дней" in section
    for source in ("WHO", "FAO", "официальный Минздрав Узбекистана"):
        assert source in section
    assert "источник и дату" in section
    assert "диагноз" in section
    assert "лечебную диету" in section
    assert "лекарств" in section
    assert "универсальную обязательную норму мяса" in section
    assert "Если интернет недоступен или надёжного источника нет" in section
    assert "согласовать рацион с врачом" in section


def test_stage53_detailed_report_uses_exact_three_column_table():
    section = _stage53()
    assert "get_monthly_budget_status(include_items=true)" in section
    assert section.index(CATEGORY_HEADER) < section.index(PRODUCT_HEADER)
    assert f"| {PRODUCT_HEADER} |" in section
    assert "|---|---:|---:|" in section
    assert OLD_FIVE_COLUMN not in section
    assert "отдельную товарную колонку `Қолгани`" in section
    assert "не добавляй" in section
    assert "Маҳсулот | Миқдор | Сарфлангани" in section
    assert "только Stage 5.2" in section


def test_stage53_unknown_values_units_and_no_technical_fields():
    text = _text()
    section = _stage53()
    assert "`—`" in section
    assert "`айтилмаган`" in section
    assert "не угадывай количество" in section
    assert "не угадывай цену" in section
    assert "разные единицы не смешивай" in section
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


def test_stage53_does_not_claim_stage53a_or_runtime_cron():
    section = _stage53()
    assert "Stage 5.3A" in section
    assert "approve_monthly_plan" in section
    assert "25/27/28/1" in section
    assert "не реализованы" in section
    assert "cron" in section
