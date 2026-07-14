"""Permanent contract for Mariyam Stage 5.2 simple family reports."""
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "mariyam" / "SKILL.md"
STAGE52_HEADING = "## 3.6. Ойижон учун оддий оила харажатлари ҳисоботи"


def _stage52() -> str:
    text = SKILL.read_text(encoding="utf-8")
    assert STAGE52_HEADING in text
    return text.split(STAGE52_HEADING, 1)[1].split("\n## 4.", 1)[0]


def test_general_report_starts_with_required_table():
    section = _stage52()
    assert "Харажат гуруҳи | Режа | Сарфланди | Қолди" in section
    assert "первым" in section.lower()


def test_general_report_has_exactly_one_follow_up_question():
    section = _stage52()
    prompt = (
        "Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб "
        "чиқамиз. Маълумотлар тайёр."
    )
    assert section.count(prompt) == 1


def test_details_are_only_on_request_and_not_automatic():
    section = _stage52().lower()
    assert "детали только после просьбы" in section
    assert "не показывать автоматически" in section


def test_user_facing_group_mapping_is_explicit():
    section = _stage52()
    for group in ("Озиқ-овқат", "Дори-дармон", "Коммунал", "Уй", "Бошқа"):
        assert group in section
    for mapping in (
        "`food` и `food.*` → `Озиқ-овқат`",
        "`medicine` → `Дори-дармон`",
        "`utilities` → `Коммунал`",
        "`home` → `Уй`",
        "остальные категории → `Бошқа`",
    ):
        assert mapping in section


def test_food_details_use_item_table_and_tool_facts_only():
    section = _stage52()
    lower = section.lower()
    assert "Маҳсулот | Режада миқдор/сумма | Олинган миқдор/сумма" in section
    assert "фактическую сумму" in lower
    assert "только из `get_expense_report`" in section
    assert "фактическое количество" in lower
    assert "только при наличии `quantity`" in section


def test_unknown_values_are_not_guessed_or_replaced_with_zero():
    section = _stage52()
    compact = " ".join(section.split())
    lower = section.lower()
    assert "айтилмаган" in section
    assert "не `0`" in section
    assert "quantity не угадывать" in section
    assert "разные единицы не смешивать" in lower
    assert "не выводить из суммы или числа покупок" in compact


def test_all_user_facing_units_are_documented():
    section = _stage52()
    for mapping in (
        "`kg` → `кг`",
        "`g` → `г`",
        "`l` → `л`",
        "`ml` → `мл`",
        "`pcs` → `дона`",
        "`pack` → `қадоқ`",
    ):
        assert mapping in section


def test_product_plan_storage_is_not_invented():
    section = _stage52()
    compact = " ".join(section.split())
    assert "Stage 5.2 не имеет product-plan storage" in section
    assert "только когда точное значение реально пришло из tool" in compact
    assert "migration 003" in section
    assert "новые tools" in section


def test_simple_user_facing_financial_words_are_required():
    section = _stage52()
    for word in (
        "режа",
        "сарфланди",
        "қолди",
        "харажат гуруҳи",
        "режадан кўп",
        "режадан кам",
        "ойлар бўйича ўзгариш",
    ):
        assert word in section.lower()


def test_technical_financial_text_is_explicitly_hidden_from_oyijon():
    section = _stage52()
    assert "Не показывай Ойижон" in section
    for term in (
        "JSON",
        "tool names",
        "plan/fact",
        "usage_percent",
        "analytics",
        "trend",
        "category_code",
        "remaining_uzs",
        "planned_amount_uzs",
        "actual_amount_uzs",
        "purchase_count",
        "canonical units",
    ):
        assert f"`{term}`" in section


def test_negative_remaining_is_explained_without_formula():
    section = _stage52()
    assert "Режадан 50 000 сўм кўп сарфланди." in section
    assert "отрицательный остаток" in section
    assert "не показывай отрицательное значение" in section


def test_month_end_has_only_the_required_soft_statement():
    section = _stage52()
    statement = (
        "Ойижон, вақтингиз бўлганда, кейинги ой учун оила харажатлари "
        "режасини бирга кўриб чиқамиз."
    )
    assert section.count(statement) == 1
    assert "Не начинай Stage 5.3" in section
    assert "семь вопросов" in section
