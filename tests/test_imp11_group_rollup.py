"""imp11: общий отчёт за месяц приходит группами верхнего уровня.

Живой случай 2 августа: Ойижон спросила расходы за месяц и получила десять
сырых подгрупп. Свёртка `food.*` -> `food` в `get_monthly_budget_status`
срабатывала только если в плане есть строка `food`; в её плане такой строки нет.
Теперь свёртка не зависит от того, как составлен план, а план свёрнутой строки —
сумма планов подгрупп. Подгруппы остаются там, где их просят: в
`get_expense_report` с `category_code`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend import db
from tests.test_stage53_product_plans import (  # noqa: F401  (fixture reuse)
    _insert_expense,
    _seed_user,
    requires_db,
    stage53_pool,
)

JULY = datetime(2026, 7, 10, tzinfo=timezone.utc)
JUNE = datetime(2026, 6, 10, tzinfo=timezone.utc)


def _by_code(rows):
    return {row["category_code"]: row for row in rows}


@requires_db
@pytest.mark.asyncio
async def test_general_report_folds_food_subgroups_without_a_food_plan(stage53_pool):
    """План задан по подгруппам, строки `food` в нём нет — это случай Ойижон."""
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(pool, user_id, "2026-07-01", "food.meat", 300000)
    await db.set_monthly_budget(pool, user_id, "2026-07-01", "food.bread", 100000)
    await db.set_monthly_budget(pool, user_id, "2026-07-01", "home", 50000)
    for amount, category, item in (
        (250000, "food.meat", "гўшт"),
        (40000, "food.bread", "нон"),
        (70000, "food.sweets", "ширинлик"),   # подгруппа вообще без плана
        (30000, "home", "супурги"),
        (20000, "clothes", "пайпоқ"),          # группа без плана
    ):
        await _insert_expense(
            pool, user_id, amount=amount, category=category, item=item,
            occurred_at=JULY,
        )

    status = await db.get_monthly_budget_status(pool, user_id, "2026-07-01")

    rows = _by_code(status["by_category"])
    assert sorted(rows) == ["clothes", "food", "home"]
    # план свёрнутой строки = сумма планов подгрупп, иначе Режа/Қолгани соврут
    assert rows["food"]["planned_uzs"] == 400000
    assert rows["food"]["actual_uzs"] == 360000
    assert rows["food"]["difference_uzs"] == 40000
    assert rows["clothes"]["planned_uzs"] == 0
    # контрольные суммы не меняются от перегруппировки
    assert status["planned_total_uzs"] == 450000
    assert status["actual_total_uzs"] == 410000
    assert status["remaining_uzs"] == 40000


@requires_db
@pytest.mark.asyncio
async def test_plan_on_parent_and_subgroup_gives_one_row(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(pool, user_id, "2026-07-01", "food", 200000)
    await db.set_monthly_budget(pool, user_id, "2026-07-01", "food.meat", 300000)
    await _insert_expense(
        pool, user_id, amount=120000, category="food.meat", item="гўшт",
        occurred_at=JULY,
    )
    await _insert_expense(
        pool, user_id, amount=80000, category="food", item="бозорлик",
        occurred_at=JULY,
    )

    status = await db.get_monthly_budget_status(pool, user_id, "2026-07-01")

    assert [row["category_code"] for row in status["by_category"]] == ["food"]
    assert status["by_category"][0]["planned_uzs"] == 500000
    assert status["by_category"][0]["actual_uzs"] == 200000


@requires_db
@pytest.mark.asyncio
async def test_general_report_has_no_subgroup_rows_even_with_many_subgroups(stage53_pool):
    """Каждая новая подгруппа еды больше не добавляет строку в главный отчёт."""
    pool = stage53_pool
    user_id = await _seed_user(pool)
    subgroups = (
        "food.meat", "food.oil", "food.vegetables", "food.fruits", "food.bread",
        "food.grains", "food.sweets", "food.ready_food", "food.wholesale",
    )
    for category in subgroups:
        await _insert_expense(
            pool, user_id, amount=1000, category=category, item=category,
            occurred_at=JULY,
        )

    status = await db.get_monthly_budget_status(pool, user_id, "2026-07-01")

    assert [row["category_code"] for row in status["by_category"]] == ["food"]
    assert status["actual_total_uzs"] == 1000 * len(subgroups)


@requires_db
@pytest.mark.asyncio
async def test_category_detail_for_food_keeps_subgroups_and_items(stage53_pool):
    """«Покажи подробнее еду» — подгруппы и товарные строки на месте."""
    pool = stage53_pool
    user_id = await _seed_user(pool)
    for amount, category, item in (
        (250000, "food.meat", "гўшт"),
        (40000, "food.bread", "нон"),
        (60000, "food", "бозорлик"),
        (20000, "clothes", "пайпоқ"),
    ):
        await _insert_expense(
            pool, user_id, amount=amount, category=category, item=item,
            occurred_at=JULY,
        )

    detail = await db.expense_report(
        pool, user_id, "custom", "2026-07-01", "2026-07-31", "food"
    )

    assert detail["total_uzs"] == 350000  # родитель + подгруппы, без одежды
    assert _by_code(detail["by_category"]).keys() == {
        "food", "food.meat", "food.bread"
    }
    items = {row["item_name_normalized"]: row for row in detail["by_item"]}
    assert items.keys() == {"гўшт", "нон", "бозорлик"}
    assert items["гўшт"]["total_uzs"] == 250000
    assert items["гўшт"]["category_code"] == "food.meat"

    narrow = await db.expense_report(
        pool, user_id, "custom", "2026-07-01", "2026-07-31", "food.meat"
    )
    assert narrow["total_uzs"] == 250000
    assert [row["category_code"] for row in narrow["by_category"]] == ["food.meat"]


@requires_db
@pytest.mark.asyncio
async def test_expense_report_without_filter_is_a_group_summary(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    for amount, category, item in (
        (250000, "food.meat", "гўшт"),
        (40000, "food.bread", "нон"),
        (20000, "clothes", "пайпоқ"),
    ):
        await _insert_expense(
            pool, user_id, amount=amount, category=category, item=item,
            occurred_at=JULY,
        )

    report = await db.expense_report(
        pool, user_id, "custom", "2026-07-01", "2026-07-31"
    )

    rows = _by_code(report["by_category"])
    assert rows.keys() == {"food", "clothes"}
    assert rows["food"]["sum_uzs"] == 290000
    assert rows["food"]["name_uz"] == "Озиқ-овқат"
    assert report["top_category"] == "food"
    assert report["total_uzs"] == 310000
    # товарные строки не свёрнуты — их показывают только по явной просьбе
    assert {row["item_name_normalized"] for row in report["by_item"]} == {
        "гўшт", "нон", "пайпоқ"
    }


@requires_db
@pytest.mark.asyncio
async def test_compare_and_trend_for_a_parent_group_include_subgroups(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await _insert_expense(
        pool, user_id, amount=100000, category="food.meat", item="гўшт",
        occurred_at=JUNE,
    )
    await _insert_expense(
        pool, user_id, amount=150000, category="food.bread", item="нон",
        occurred_at=JULY,
    )

    report = await db.expense_report(
        pool, user_id, "custom", "2026-07-01", "2026-07-31", "food",
        compare_previous=True, trend_months=2,
    )

    assert report["total_uzs"] == 150000
    assert report["previous_period"]["total_uzs"] == 100000
    assert report["previous_period"]["change_uzs"] == 50000
    assert [row["total_uzs"] for row in report["monthly_series"]] == [100000, 150000]
