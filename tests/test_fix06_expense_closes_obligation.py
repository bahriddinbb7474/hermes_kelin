"""fix06: расход, который и есть оплата обязательства, закрывает обязательство.

3 августа мама сказала боту `электрга 400 минг тўладим`. Расход записался, а
обязательство осталось `paid=false`: §8 описывала только обратное направление
(`mark_paid` → отдельный `save_expense`), поэтому на следующее утро она получила
бы напоминание заплатить за уже оплаченное. Тест держит новое правило и его
предохранители — критерий узкий, потому что ошибочно закрытое обязательство
хуже незакрытого: оно больше никогда о себе не напомнит.
"""
from __future__ import annotations

import re
from pathlib import Path

SOUL = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "SOUL.md"
)
TEXT = SOUL.read_text(encoding="utf-8")


def _section_8() -> str:
    start = TEXT.index("## 8. Напоминания")
    return TEXT[start : TEXT.index("## 9.", start)]


def test_rule_lives_inside_section_8_and_not_in_a_new_section():
    body = _section_8()
    assert "mark_paid" in body
    # правило встроено в существующий блок про обязательства, без нового раздела
    assert TEXT.count("## 8.") == 1
    assert "## 8а" not in TEXT and "### 8." not in TEXT


def test_expense_that_is_a_payment_also_marks_the_obligation():
    body = _section_8()
    assert "save_expense" in body and "mark_paid" in body
    assert re.search(r"И наоборот", body), "нужно явное обратное направление"
    # расход по-прежнему записывается — старое правило не отменено
    assert "записывай расход отдельным `save_expense`" in TEXT


def test_match_criterion_is_narrow():
    body = _section_8()
    for marker in (
        "оплате",          # это платёж по счёту, а не покупка
        "reminder_lead_days",  # срок рядом
        "ровно одно обязательство",
    ):
        assert marker in body, f"в критерии не хватает: {marker}"


def test_buying_a_thing_never_closes_a_payment():
    body = _section_8()
    assert "лампочка" in body
    assert "не закрывает" in body


def test_amount_difference_is_not_a_reason_to_skip():
    """Заплатили 400 000 вместо 300 000 — обязательство всё равно закрывается."""
    body = _section_8()
    assert "expected_amount_uzs" in body
    assert re.search(r"сумма.{0,80}отлич", body, re.IGNORECASE | re.DOTALL)


def test_ambiguity_produces_one_soft_question_and_never_silence():
    body = _section_8()
    assert "один мягкий вопрос" in body
    assert "Молча не" in body


def test_rule_examples_stay_in_uzbek_cyrillic():
    body = _section_8()
    quoted = re.findall(r"`([^`]+)`", body)
    phrases = [
        item
        for item in quoted
        if " " in item and not re.search(r"[a-z_]{3,}", item)
    ]
    assert phrases, "в правиле должна быть готовая фраза для Ойижон"
    for phrase in phrases:
        assert not re.search(r"[A-Za-z]", phrase), phrase
        assert re.search(r"[Ѐ-ӿ]", phrase), phrase
