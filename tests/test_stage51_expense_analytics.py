"""Stage 5.1 — save_expense quantity/unit + get_expense_report analytics.

Unit tests (always): validation helpers, by_item builder, previous bounds.
Integration tests: require APP_ENV=test + DATABASE_URL → *_test DB with 002 applied.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend import db
from backend.config import TASHKENT


# ---------------------------------------------------------------------------
# Pure unit tests (no DB)
# ---------------------------------------------------------------------------


def test_normalize_qty_unit_absent():
    assert db._normalize_qty_unit({"amount_uzs": 100}) == (None, None)


def test_normalize_qty_unit_ok():
    q, u = db._normalize_qty_unit({"quantity": 10, "unit": "KG"})
    assert q == 10.0 and u == "kg"


def test_normalize_qty_unit_negative():
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        db._normalize_qty_unit({"quantity": -1, "unit": "kg"})


def test_normalize_qty_unit_zero():
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        db._normalize_qty_unit({"quantity": 0, "unit": "kg"})


def test_normalize_qty_unit_bad_unit():
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        db._normalize_qty_unit({"quantity": 1, "unit": "box"})


def test_normalize_qty_unit_without_quantity():
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        db._normalize_qty_unit({"unit": "kg"})


def test_normalize_qty_unit_qty_only_ok():
    q, u = db._normalize_qty_unit({"quantity": 3})
    assert q == 3.0 and u is None


@pytest.mark.parametrize("bad", [True, "10", float("nan"), float("inf")])
def test_normalize_qty_unit_rejects_wrong_or_nonfinite_type(bad):
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        db._normalize_qty_unit({"quantity": bad, "unit": "kg"})


def test_build_by_item_homogeneous_avg():
    rows = [
        {"item_name_normalized": "картошка", "category_code": "food.vegetables",
         "amount": 70000, "quantity": Decimal("10"), "unit": "kg"},
        {"item_name_normalized": "картошка", "category_code": "food.vegetables",
         "amount": 35000, "quantity": Decimal("5"), "unit": "kg"},
    ]
    bi = db._build_by_item(rows)
    assert len(bi) == 1
    assert bi[0]["total_uzs"] == 105000
    assert bi[0]["purchase_count"] == 2
    assert bi[0]["quantity_by_unit"] == {"kg": 15}
    assert bi[0]["average_unit_price_uzs"] == 7000.0


def test_build_by_item_mixed_null_avg_none():
    rows = [
        {"item_name_normalized": "нон", "category_code": "food.bread",
         "amount": 12000, "quantity": None, "unit": None},
        {"item_name_normalized": "нон", "category_code": "food.bread",
         "amount": 6000, "quantity": Decimal("2"), "unit": "pcs"},
    ]
    bi = db._build_by_item(rows)
    assert bi[0]["average_unit_price_uzs"] is None
    assert bi[0]["purchase_count"] == 2
    assert bi[0]["quantity_by_unit"] == {"pcs": 2}


def test_build_by_item_skips_null_normalized():
    rows = [
        {"item_name_normalized": None, "category_code": "food.bread",
         "amount": 12000, "quantity": None, "unit": None},
        {"item_name_normalized": "гўшт", "category_code": "food.meat",
         "amount": 150000, "quantity": Decimal("1"), "unit": "kg"},
    ]
    bi = db._build_by_item(rows)
    assert len(bi) == 1
    assert bi[0]["item_name_normalized"] == "гўшт"


def test_previous_period_bounds_month_like():
    start = datetime(2026, 7, 1, tzinfo=TASHKENT).astimezone(timezone.utc)
    end = datetime(2026, 8, 1, tzinfo=TASHKENT).astimezone(timezone.utc)
    p0, p1 = db._previous_period_bounds(start, end)
    assert p1 == start
    assert (p1 - p0) == (end - start)


def test_previous_calendar_month_uses_exact_tashkent_boundaries():
    start = datetime(2026, 3, 1, tzinfo=TASHKENT).astimezone(timezone.utc)
    end = datetime(2026, 4, 1, tzinfo=TASHKENT).astimezone(timezone.utc)
    p0, p1 = db._previous_period_bounds(start, end, calendar_month=True)
    assert p0.astimezone(TASHKENT).date().isoformat() == "2026-02-01"
    assert p1.astimezone(TASHKENT).date().isoformat() == "2026-03-01"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [0, 13, True, 3.5, "3"])
async def test_expense_report_rejects_invalid_trend_before_db(bad):
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.expense_report(None, 1, "month", trend_months=bad)


@pytest.mark.asyncio
async def test_expense_report_rejects_non_boolean_compare_before_db():
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.expense_report(None, 1, "month", compare_previous="false")


def test_dispatch_keeps_old_19_and_adds_exactly_two_budget_tools():
    from backend.server import DISPATCH, TOOLS

    old_19 = {
        "ensure_user", "save_expense", "save_income", "update_expense",
        "update_last_expense", "delete_expense", "delete_last_expense",
        "get_expense_report", "get_balance_summary", "save_quran_progress",
        "get_quran_progress", "save_health_note", "save_alert_event",
        "save_plan_note", "get_admin_report_data", "backup_data",
        "get_backup_status", "get_bot_status", "log_usage_cost",
    }
    new_tools = {"set_monthly_budget", "get_monthly_budget_status", "approve_monthly_plan"}
    dispatch_names = set(DISPATCH)
    listed_names = {name for name, _description, _schema in TOOLS}

    assert len(old_19) == 19
    assert dispatch_names == listed_names == old_19 | new_tools
    assert len(DISPATCH) == len(TOOLS) == 22


# ---------------------------------------------------------------------------
# Integration (optional DB)
# ---------------------------------------------------------------------------


def _db_available() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    env = os.environ.get("APP_ENV")
    if env != "test" or not url:
        return False
    try:
        from tests.db_guard import validate_destructive_test_target
        validate_destructive_test_target(
            database_url=url,
            app_env=env,
            allow_remote=os.environ.get("ALLOW_DESTRUCTIVE_TESTS") == "1",
        )
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="APP_ENV=test + hermes_test DATABASE_URL required")


@requires_db
@pytest.mark.asyncio
async def test_save_and_report_integration():
    from backend.config import get_pool

    pool = await get_pool()
    # ensure 002 columns exist
    cols = await pool.fetch(
        """SELECT column_name FROM information_schema.columns
           WHERE table_name='transactions'
             AND column_name IN ('item_name_normalized','quantity','unit')"""
    )
    if len(cols) < 3:
        pytest.skip("migration 002 not applied on test DB")

    await pool.execute(
        "TRUNCATE transactions, quran_progress, health_notes, alert_events, "
        "plan_notes, usage_costs, users RESTART IDENTITY CASCADE"
    )
    oy, _ = await db.ensure_user(pool, 511001, "oyijon", "Тест 5.1")

    # old-style save
    r0 = await db.save_expense(
        pool, oy,
        [{"item_name": "нон", "amount_uzs": 12000, "category_code": "food.bread"}],
        "2026-07-15T10:00:00Z", "text",
    )
    assert r0["total_uzs"] == 12000
    row0 = await pool.fetchrow("SELECT quantity, unit, item_name_normalized FROM transactions WHERE id=$1", r0["saved_ids"][0])
    assert row0["quantity"] is None and row0["unit"] is None

    # potato 10 kg
    r1 = await db.save_expense(
        pool, oy,
        [{
            "item_name": "картошка",
            "item_name_normalized": "картошка",
            "amount_uzs": 70000,
            "category_code": "food.vegetables",
            "quantity": 10,
            "unit": "kg",
        }],
        "2026-07-15T11:00:00Z", "text",
    )
    assert r1["total_uzs"] == 70000
    row1 = await pool.fetchrow(
        "SELECT quantity, unit, item_name_normalized FROM transactions WHERE id=$1",
        r1["saved_ids"][0],
    )
    assert float(row1["quantity"]) == 10.0 and row1["unit"] == "kg"

    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.save_expense(
            pool, oy,
            [{"amount_uzs": 1, "category_code": "food.bread", "quantity": -3, "unit": "kg"}],
            None, "text",
        )
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.save_expense(
            pool, oy,
            [{"amount_uzs": 1, "category_code": "food.bread", "quantity": 1, "unit": "box"}],
            None, "text",
        )
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.save_expense(
            pool, oy,
            [{"amount_uzs": 1, "category_code": "food.bread", "unit": "kg"}],
            None, "text",
        )

    # second kg potato for avg
    await db.save_expense(
        pool, oy,
        [{
            "item_name": "картошка",
            "item_name_normalized": "картошка",
            "amount_uzs": 35000,
            "category_code": "food.vegetables",
            "quantity": 5,
            "unit": "kg",
        }],
        "2026-07-16T11:00:00Z", "text",
    )

    # previous month spend for compare
    await db.save_expense(
        pool, oy,
        [{"item_name": "old", "item_name_normalized": "old", "amount_uzs": 100000,
          "category_code": "other"}],
        "2026-06-10T10:00:00Z", "text",
    )

    rep = await db.expense_report(
        pool, oy, "custom", "2026-07-01", "2026-07-31",
        compare_previous=True, trend_months=3,
    )
    assert rep["total_uzs"] == 12000 + 70000 + 35000
    assert "by_item" in rep
    kart = next(x for x in rep["by_item"] if x["item_name_normalized"] == "картошка")
    assert kart["total_uzs"] == 105000
    assert kart["purchase_count"] == 2
    assert kart["quantity_by_unit"]["kg"] == 15
    assert kart["average_unit_price_uzs"] == 7000.0
    # legacy bread without normalized still in total, not in by_item as bread group
    names = {x["item_name_normalized"] for x in rep["by_item"]}
    assert "нон" not in names  # no normalized name

    prev = rep["previous_period"]
    assert prev["total_uzs"] == 100000
    assert prev["change_uzs"] == rep["total_uzs"] - 100000
    assert prev["change_percent"] is not None

    # empty previous → percent null
    rep2 = await db.expense_report(
        pool, oy, "custom", "2026-05-01", "2026-05-31",
        compare_previous=True, trend_months=3,
    )
    assert rep2["previous_period"]["total_uzs"] == 0
    assert rep2["previous_period"]["change_percent"] is None

    series = rep["monthly_series"]
    assert len(series) == 3
    assert [x["month"] for x in series] == ["2026-05-01", "2026-06-01", "2026-07-01"]
    assert [x["total_uzs"] for x in series] == [0, 100000, 117000]

    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.expense_report(pool, oy, "month", trend_months=0)
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.expense_report(pool, oy, "month", trend_months=13)
