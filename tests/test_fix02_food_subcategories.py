"""fix02: подгруппы еды, которых не хватало справочнику.

Живой случай 2 августа: Ойижон попросила разбивку по «Тайёр овқат» и получила
кофе, морс, катык, томатную пасту и тесто для самсы — готовой еды среди них
ноль. Дыра была не в модели, а в справочнике: напитков, молочного, соусов и
полуфабрикатов в нём просто не существовало, а `other` для продуктов выглядит
хуже похожей подгруппы.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INIT_SQL = REPO / "backend" / "sql" / "001_init.sql"
MIGRATION = REPO / "backend" / "sql" / "007_food_subcategories.sql"

NEW_CODES = {
    "food.dairy": "Сут маҳсулотлари",
    "food.drinks": "Ичимликлар",
    "food.sauces": "Соус ва консерва",
    "food.semi": "Ярим тайёр маҳсулотлар",
}


def _codes_in(text: str) -> set[str]:
    return set(re.findall(r"'(food\.[a-z_]+)'", text))


def test_migration_adds_exactly_the_four_missing_groups():
    text = MIGRATION.read_text(encoding="utf-8")
    assert _codes_in(text) == set(NEW_CODES)


def test_new_names_are_uzbek_cyrillic():
    text = MIGRATION.read_text(encoding="utf-8")
    for code, name in NEW_CODES.items():
        assert f"'{code}'" in text and f"'{name}'" in text
        assert not re.search(r"[A-Za-z]", name)
        assert re.search(r"[Ѐ-ӿ]", name)


def test_migration_is_idempotent_and_touches_nothing_else():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "ON CONFLICT (code) DO NOTHING" in text
    for forbidden in ("UPDATE", "DELETE", "DROP", "ALTER"):
        assert forbidden not in text.upper(), f"migration must only insert, found {forbidden}"


def test_new_groups_hang_under_food():
    text = MIGRATION.read_text(encoding="utf-8")
    assert text.count("'food'") == len(NEW_CODES), "each new row must have parent_code 'food'"


def test_ready_food_survives_as_a_narrow_group():
    """`food.ready_food` stays — it is still the right label for real cooked food."""
    assert "'food.ready_food'" in INIT_SQL.read_text(encoding="utf-8")
    assert "'food.ready_food'" not in MIGRATION.read_text(encoding="utf-8")


def test_the_five_live_rows_now_have_a_home():
    """Every mislabelled item from the live table maps to one of the new groups."""
    live_case = {
        "Қаҳва Жокей": "food.drinks",
        "Морс": "food.drinks",
        "Қатиқ": "food.dairy",
        "Помидор пастаси": "food.sauces",
        "Сомса хамири": "food.semi",
    }
    assert set(live_case.values()) <= set(NEW_CODES)
