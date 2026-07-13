"""Permanent contract for Mariyam Stage 5.1 analytics/budget skill."""
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "mariyam" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_identity_sentinel_and_ensure_user_policy_preserved():
    text = _text()
    compact = text.replace(" ", "")
    assert "user_id:0" in compact
    assert "Не вызывай `ensure_user` в обычных сообщениях" in text
    identity = text.split("## 1.1.", 1)[1].split("## 2.", 1)[0]
    assert "Trusted binding" in identity
    assert "display_name" in identity
    assert "Запрещено" in identity
    assert "Guard **перезапишет**" in identity


def test_expense_item_quantity_and_canonical_unit_contract():
    text = _text()
    for field in (
        "item_name",
        "item_name_normalized",
        "amount_uzs",
        "category_code",
        "quantity",
        "unit",
    ):
        assert f"`{field}`" in text
    for unit in ("kg", "g", "l", "ml", "pcs", "pack"):
        assert f"`{unit}`" in text
    assert "без выдуманного бренда или сорта" in text
    assert "только когда количество" in text


def test_quantity_is_never_guessed_or_unknown_measure_converted():
    text = _text()
    assert "Если количество не сказано" in text
    assert "поля `quantity`/`unit` не передавай" in text
    assert "Никогда не" in text and "1 кг" in text and "1 штуке" in text
    assert "Неизвестную меру не конвертируй" in text
    assert "разные единицы не смешивай" in text


def test_required_quantity_normalization_examples_exist():
    text = _text()
    expected = (
        ("2 кило гўшт", "quantity=2", "unit=kg"),
        ("500 грамм пишлоқ", "quantity=500", "unit=g"),
        ("3 литр ёғ", "quantity=3", "unit=l"),
        ("6 дона тухум", "quantity=6", "unit=pcs"),
        ("10 кило картошка 70 минг", "quantity=10", "unit=kg"),
    )
    for phrase, quantity, unit in expected:
        assert phrase in text
        assert quantity in text
        assert unit in text


def test_expense_analytics_tool_contract():
    text = _text()
    assert "`get_expense_report`" in text
    assert "`compare_previous: true`" in text
    assert "`trend_months: 3`" in text
    assert "максимум — 12" in text
    assert "`purchase_count`" in text
    assert "`monthly_series`" in text
    assert "не вычисляй точные финансовые данные по памяти" in text


def test_monthly_budget_tools_and_negative_remaining_contract():
    text = _text()
    assert "`set_monthly_budget`" in text
    assert "`get_monthly_budget_status`" in text
    assert "первый день месяца `YYYY-MM-01`" in text
    assert "Отрицательный `remaining_uzs` — не ошибка" in text
    assert "один мягкий уточняющий вопрос" in text


def test_financial_advice_does_not_guarantee_wholesale_savings():
    text = _text()
    assert "Запрещено обещать точную экономию без реальных цен" in text
    assert "опт всегда" in text and "дешевле" in text
    assert "скоропортящихся продуктов без предупреждения" in text
    assert "прогноз за точный факт" in text


def test_user_facing_units_are_cyrillic_and_technical_traces_forbidden():
    text = _text()
    compact = " ".join(text.split())
    for unit in ("`кг`", "`г`", "`л`", "`мл`", "`дона`", "`қадоқ`"):
        assert unit in text
    assert "только узбекская кириллица" in text
    assert "Не показывай Ойижон JSON" in compact
    assert "tool names" in text
    assert "технические сообщения/traces" in text


def test_four_required_stage51_examples_exist():
    text = _text()
    for phrase in (
        "10 кило картошка 70 минг",
        "Бу ой озиқ-овқатга қанча кетди?",
        "Ўтган ой билан солиштиринг",
        "Кейинги ой озиқ-овқатга 1,5 миллион режа қўйинг",
    ):
        assert phrase in text
