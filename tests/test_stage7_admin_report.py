"""Stage 7 admin-report facts and privacy contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio

from backend import db
from tests.db_guard import validate_destructive_test_target


REPO = Path(__file__).resolve().parents[1]
MIGRATIONS = [
    REPO / "backend" / "sql" / "001_init.sql",
    REPO / "backend" / "sql" / "002_stage51_quantity_budget.sql",
    REPO / "backend" / "sql" / "003_stage53_product_plans.sql",
    REPO / "backend" / "sql" / "005_stage6_recurring_obligations.sql",
]
ADMIN_PROMPT = (
    REPO
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "cron"
    / "07_admin_report.md"
)


def _db_available() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    env = os.environ.get("APP_ENV")
    if env != "test" or not url:
        return False
    validate_destructive_test_target(
        database_url=url,
        app_env=env,
        allow_remote=os.environ.get("ALLOW_DESTRUCTIVE_TESTS") == "1",
    )
    return True


@pytest_asyncio.fixture
async def pool():
    if not _db_available():
        pytest.skip("requires disposable PostgreSQL test database")
    import asyncpg

    result = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=1, max_size=3
    )
    try:
        async with result.acquire() as conn:
            for migration in MIGRATIONS:
                await conn.execute(migration.read_text(encoding="utf-8"))
            await conn.execute(
                """TRUNCATE recurring_obligations, monthly_budget_items,
                   monthly_plan_cycles, monthly_budget_plans, transactions,
                   quran_progress, health_notes, alert_events, users
                   RESTART IDENTITY CASCADE"""
            )
        yield result
    finally:
        await result.close()


def _contains_private_text(value, needle: str) -> bool:
    return needle in json.dumps(value, ensure_ascii=False)


@pytest.mark.asyncio
async def test_admin_report_matches_sql_and_excludes_health_text(pool):
    user_id = await pool.fetchval(
        """INSERT INTO users(telegram_id, role, display_name)
           VALUES (970001, 'oyijon', 'Stage 7 Test') RETURNING id"""
    )
    await db.save_expense(
        pool,
        user_id,
        [
            {
                "item_name": "нон",
                "amount_uzs": 12000,
                "category_code": "food.bread",
            },
            {
                "item_name": "гўшт",
                "amount_uzs": 180000,
                "category_code": "food.meat",
            },
        ],
        "2026-07-27T10:00:00Z",
        "text",
    )
    await db.save_expense(
        pool,
        user_id,
        [{
            "item_name": "ой боши",
            "amount_uzs": 8000,
            "category_code": "food.bread",
        }],
        "2026-07-02T10:00:00Z",
        "text",
    )
    await db.save_income(
        pool, user_id, 2300000, "UZS", "pension",
        "2026-07-27T09:00:00Z", "text",
    )
    await pool.execute(
        """INSERT INTO monthly_budget_plans
           (user_id, month, category_code, planned_amount_uzs)
           VALUES ($1, '2026-07-01', 'food', 500000)""",
        user_id,
    )
    await pool.execute(
        """INSERT INTO monthly_plan_cycles(user_id, month, status, source)
           VALUES (
               $1, '2026-07-01', 'approved_by_oyijon', 'manually_created'
           )""",
        user_id,
    )
    await pool.execute(
        """INSERT INTO recurring_obligations(
               user_id, obligation_type, name, expected_amount_uzs, due_date,
               repeat_rule, repeat_interval_days, repeat_anchor_month,
               repeat_anchor_day, reminder_lead_days
           ) VALUES
             ($1,'internet','Internet',150000,'2026-07-26','monthly',NULL,7,26,3),
             ($1,'tax','Far future',90000,'2026-08-20','yearly',NULL,8,20,7)""",
        user_id,
    )
    private_note = "махфий соғлиқ матни"
    private_source = "юрагим оғрияпти"
    await db.save_health_note(pool, user_id, private_note, "high", private_note)
    await db.save_alert_event(
        pool, user_id, "medical", "critical", private_source,
        "soft response", "keyword", True,
    )
    await pool.execute(
        "UPDATE health_notes SET created_at='2026-07-27T10:00:00Z' "
        "WHERE user_id=$1",
        user_id,
    )
    await pool.execute(
        "UPDATE alert_events SET created_at='2026-07-27T10:01:00Z' "
        "WHERE user_id=$1",
        user_id,
    )

    report = await db.admin_report_data(pool, user_id, "2026-07-27")
    day_sql = await pool.fetchval(
        """SELECT SUM(amount) FROM transactions
           WHERE user_id=$1 AND type='expense'
             AND occurred_at >= '2026-07-26T19:00:00Z'
             AND occurred_at < '2026-07-27T19:00:00Z'""",
        user_id,
    )
    month_sql = await pool.fetchval(
        """SELECT SUM(amount) FROM transactions
           WHERE user_id=$1 AND type='expense'
             AND occurred_at >= '2026-06-30T19:00:00Z'
             AND occurred_at < '2026-07-31T19:00:00Z'""",
        user_id,
    )
    assert report["expense_total_uzs"] == int(day_sql) == 192000
    assert report["month_expense_total_uzs"] == int(month_sql) == 200000
    assert report["income_total_uzs"] == 2300000
    assert report["month_income_total_uzs"] == 2300000
    assert report["plan"] == {
        "status": "approved_by_oyijon",
        "source": "manually_created",
        "household_size": None,
        "planned_total_uzs": 500000,
        "actual_total_uzs": 200000,
        "remaining_uzs": 300000,
    }
    assert [item["name"] for item in report["due_obligations"]] == ["Internet"]
    assert report["due_obligations"][0]["overdue"] is True
    assert len(report["alerts"]) == 1
    assert report["alerts"][0]["sent_to_admin"] is True
    assert not _contains_private_text(report, private_note)
    assert not _contains_private_text(report, private_source)
    assert "source_text" not in json.dumps(report)
    assert "bot_response" not in json.dumps(report)


def test_admin_prompt_uses_one_tool_and_forbids_invented_numbers():
    prompt = ADMIN_PROMPT.read_text(encoding="utf-8")
    assert prompt.count("get_admin_report_data") == 1
    assert "ровно один read-only tool" in prompt
    assert "Ничего не вычисляй и не" in prompt
    assert "исходные health-фразы" in prompt
