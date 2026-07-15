"""Permanent contract for Mariyam Stage 5.2 simple family reports."""
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "mariyam" / "SKILL.md"
STAGE52_HEADING = "## 3.6. Ойижон учун оддий оила харажатлари ҳисоботи"


def _stage52() -> str:
    text = SKILL.read_text(encoding="utf-8")
    assert STAGE52_HEADING in text
    return text.split(STAGE52_HEADING, 1)[1].split("\n## 4.", 1)[0]


def test_general_report_allows_natural_intro_and_flexible_labels():
    section = _stage52()
    assert "естественн" in section.lower()
    assert "вступлен" in section.lower()
    assert "Сарфланди" in section
    assert "Сарфлангани" in section
    assert "Қолди" in section
    assert "Қолгани" in section
    assert "Жами" in section


def test_general_report_ends_with_exact_required_phrase():
    section = _stage52()
    prompt = (
        "Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб "
        "чиқамиз. Маълумотлар тайёр."
    )
    assert section.count(prompt) == 1
    assert "заверши общий отчёт" in section.lower()


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


def test_details_have_category_summary_then_actual_items_only():
    section = _stage52()
    lower = section.lower()
    summary = "Харажат гуруҳи | Режа | Сарфлангани | Қолгани"
    items = "Маҳсулот | Миқдор | Сарфлангани"
    assert summary in section
    assert items in section
    assert section.index(summary) < section.index(items)
    assert "только фактические товары" in lower
    assert "фактическую сумму" in lower
    assert "только из `get_expense_report`" in section
    assert "фактическое количество" in lower
    assert "только при наличии `quantity`" in section


def test_unknown_values_are_not_guessed_or_replaced_with_zero():
    section = _stage52()
    compact = " ".join(section.split())
    lower = section.lower()
    assert "missing quantity" in lower
    assert "`—`" in section
    assert "не показывать" in lower
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
        "`pcs` → `та`",
        "`pack` → `қадоқ`",
    ):
        assert mapping in section


def test_product_plan_storage_is_not_invented():
    section = _stage52()
    assert "Stage 5.2 не имеет product-plan storage" in section
    assert "product plan в Stage 5.2 не показывай" in section
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


def test_negative_remaining_is_shown_with_simple_explanation():
    section = _stage52()
    assert "отрицательный остаток" in section
    assert "простым пояснением" in section
    assert "без сложной формулы" in section


def test_month_end_has_only_the_required_soft_statement():
    section = _stage52()
    statement = (
        "Ойижон, вақтингиз бўлганда, кейинги ой учун оила харажатлари "
        "режасини бирга кўриб чиқамиз."
    )
    assert section.count(statement) == 1
    assert "Не начинай Stage 5.3" in section
    assert "семь вопросов" in section
