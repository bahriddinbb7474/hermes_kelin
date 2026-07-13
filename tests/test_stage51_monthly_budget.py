"""Stage 5.1 monthly-budget plan/fact tests.

Pure contract tests always run. PostgreSQL integration runs when APP_ENV=test and
DATABASE_URL points to a disposable database with migrations 001+002 applied.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend import db, server

OLD_19_TOOLS = (
    "ensure_user",
    "save_expense",
    "save_income",
    "update_expense",
    "update_last_expense",
    "delete_expense",
    "delete_last_expense",
    "get_expense_report",
    "get_balance_summary",
    "save_quran_progress",
    "get_quran_progress",
    "save_health_note",
    "save_alert_event",
    "save_plan_note",
    "get_admin_report_data",
    "backup_data",
    "get_backup_status",
    "get_bot_status",
    "log_usage_cost",
)


def test_budget_month_requires_first_day():
    assert db._budget_month("2026-07-01").isoformat() == "2026-07-01"
    for bad in ("2026-07-02", "2026-7-01", "bad", None):
        with pytest.raises(ValueError, match="INVALID_INPUT"):
            db._budget_month(bad)


def test_budget_amount_zero_and_negative_or_nonnumeric():
    assert db._budget_amount(0) == Decimal(0)
    for bad in (-1, "100", True, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="BAD_AMOUNT"):
            db._budget_amount(bad)


@pytest.mark.asyncio
async def test_tool_inventory_and_separate_required_schemas():
    tools = await server.list_tools()
    names = [tool.name for tool in tools]
    assert len(tools) == len(server.DISPATCH) == 21
    assert [name for name in names if name in OLD_19_TOOLS] == list(OLD_19_TOOLS)
    assert names.count("set_monthly_budget") == 1
    assert names.count("get_monthly_budget_status") == 1

    schemas = {tool.name: tool.inputSchema for tool in tools}
    assert schemas["set_monthly_budget"]["required"] == [
        "user_id",
        "month",
        "category_code",
        "planned_amount_uzs",
    ]
    assert schemas["get_monthly_budget_status"]["required"] == ["user_id", "month"]
    assert schemas["set_monthly_budget"] is not schemas["get_monthly_budget_status"]


async def _call_json(name, arguments):
    content = await server.call_tool(name, arguments)
    return json.loads(content[0].text)


@pytest.mark.asyncio
async def test_monthly_budget_postgres_plan_fact_and_call_tool(monkeypatch):
    if os.environ.get("APP_ENV") != "test" or not os.environ.get("DATABASE_URL"):
        pytest.skip("requires disposable PostgreSQL with APP_ENV=test + DATABASE_URL")

    import asyncpg

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    monkeypatch.setattr(server, "get_pool", lambda: _return_pool(pool))
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "TRUNCATE monthly_budget_plans, transactions, users RESTART IDENTITY CASCADE"
                )
                user_id = await conn.fetchval(
                    """INSERT INTO users (telegram_id, role, display_name)
                       VALUES (930001, 'oyijon', 'Budget Test') RETURNING id"""
                )

        # Insert + created=true through call_tool.
        first = await _call_json(
            "set_monthly_budget",
            {
                "user_id": user_id,
                "month": "2026-07-01",
                "category_code": "food.bread",
                "planned_amount_uzs": 100,
                "note": "first",
            },
        )
        assert first["ok"] is True and first["created"] is True

        # Upsert updates amount/note, keeps one row and plan_id.
        second = await _call_json(
            "set_monthly_budget",
            {
                "user_id": user_id,
                "month": "2026-07-01",
                "category_code": "food.bread",
                "planned_amount_uzs": 150,
                "note": "updated",
            },
        )
        assert second == {"ok": True, "plan_id": first["plan_id"], "created": False}
        assert await pool.fetchval(
            """SELECT count(*) FROM monthly_budget_plans
               WHERE user_id=$1 AND month='2026-07-01' AND category_code='food.bread'""",
            user_id,
        ) == 1
        row = await pool.fetchrow(
            "SELECT planned_amount_uzs, note FROM monthly_budget_plans WHERE id=$1",
            first["plan_id"],
        )
        assert row["planned_amount_uzs"] == Decimal("150.00")
        assert row["note"] == "updated"

        # Planned-only and zero plan.
        meat = await db.set_monthly_budget(pool, user_id, "2026-07-01", "food.meat", 200)
        zero = await db.set_monthly_budget(
            pool, user_id, "2026-07-01", "food.vegetables", 0
        )
        assert meat["created"] is True and zero["created"] is True

        # Exact Tashkent month is [2026-06-30 19:00Z, 2026-07-31 19:00Z).
        transactions = [
            (120, "UZS", "food.bread", datetime(2026, 7, 10, tzinfo=timezone.utc)),
            (50, "UZS", "food.oil", datetime(2026, 7, 11, tzinfo=timezone.utc)),
            (10, "UZS", "food.bread", datetime(2026, 6, 30, 19, tzinfo=timezone.utc)),
            (999, "UZS", "food.bread", datetime(2026, 6, 30, 18, 59, 59, tzinfo=timezone.utc)),
            (777, "UZS", "food.bread", datetime(2026, 7, 31, 19, tzinfo=timezone.utc)),
            (1000, "USD", "food.bread", datetime(2026, 7, 12, tzinfo=timezone.utc)),
        ]
        await pool.executemany(
            """INSERT INTO transactions
               (user_id,type,amount,currency,category_code,source_type,occurred_at)
               VALUES ($1,'expense',$2,$3,$4,'text',$5)""",
            [(user_id, *values) for values in transactions],
        )

        status = await _call_json(
            "get_monthly_budget_status", {"user_id": user_id, "month": "2026-07-01"}
        )
        assert status["ok"] is True
        assert status["month"] == "2026-07-01"
        assert status["planned_total_uzs"] == 350
        assert status["actual_total_uzs"] == 180
        assert status["remaining_uzs"] == 170
        assert [x["category_code"] for x in status["by_category"]] == [
            "food.bread",
            "food.meat",
            "food.oil",
            "food.vegetables",
        ]
        by_cat = {x["category_code"]: x for x in status["by_category"]}
        assert by_cat["food.bread"] == {
            "category_code": "food.bread",
            "planned_uzs": 150,
            "actual_uzs": 130,
            "difference_uzs": 20,
            "usage_percent": 86.6667,
        }
        assert by_cat["food.meat"]["actual_uzs"] == 0  # planned only
        assert by_cat["food.oil"]["planned_uzs"] == 0  # actual only
        assert by_cat["food.oil"]["usage_percent"] is None
        assert by_cat["food.vegetables"]["usage_percent"] is None

        # Exceed total plan -> negative remaining.
        await pool.execute(
            """INSERT INTO transactions
               (user_id,type,amount,currency,category_code,source_type,occurred_at)
               VALUES ($1,'expense',500,'UZS','food.bread','text',$2)""",
            user_id,
            datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        over = await db.get_monthly_budget_status(pool, user_id, "2026-07-01")
        assert over["remaining_uzs"] == -330

        bad_amount = await _call_json(
            "set_monthly_budget",
            {
                "user_id": user_id,
                "month": "2026-07-01",
                "category_code": "food.bread",
                "planned_amount_uzs": -1,
            },
        )
        assert bad_amount["error_code"] == "BAD_AMOUNT"
        bad_category = await _call_json(
            "set_monthly_budget",
            {
                "user_id": user_id,
                "month": "2026-07-01",
                "category_code": "missing.category",
                "planned_amount_uzs": 1,
            },
        )
        assert bad_category["error_code"] == "BAD_CATEGORY"
        await pool.execute("UPDATE expense_categories SET active=false WHERE code='food.sweets'")
        inactive_category = await _call_json(
            "set_monthly_budget",
            {
                "user_id": user_id,
                "month": "2026-07-01",
                "category_code": "food.sweets",
                "planned_amount_uzs": 1,
            },
        )
        assert inactive_category["error_code"] == "BAD_CATEGORY"
        bad_month = await _call_json(
            "get_monthly_budget_status", {"user_id": user_id, "month": "2026-07-02"}
        )
        assert bad_month["error_code"] == "INVALID_INPUT"
    finally:
        await pool.close()


async def _return_pool(pool):
    return pool
