"""Stage 5.3A — get_monthly_plan_cycle (read-only cycle status for cron gating)."""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio

from backend import db, server
from tests.db_guard import validate_destructive_test_target

REPO = Path(__file__).resolve().parents[1]
SQL_001 = REPO / "backend" / "sql" / "001_init.sql"
SQL_002 = REPO / "backend" / "sql" / "002_stage51_quantity_budget.sql"
SQL_003 = REPO / "backend" / "sql" / "003_stage53_product_plans.sql"

MONTH = "2026-08-01"
MONTH_D = date(2026, 8, 1)


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


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="APP_ENV=test + validated *_test DATABASE_URL required",
)


@pytest_asyncio.fixture
async def pool():
    if not _db_available():
        pytest.skip("requires disposable PostgreSQL test database")
    import asyncpg

    p = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=3)
    try:
        async with p.acquire() as conn:
            await conn.execute(SQL_001.read_text(encoding="utf-8"))
            await conn.execute(SQL_002.read_text(encoding="utf-8"))
            await conn.execute(
                "DROP TABLE IF EXISTS monthly_budget_items, monthly_plan_cycles"
            )
            await conn.execute(SQL_003.read_text(encoding="utf-8"))
            await conn.execute(
                "TRUNCATE monthly_budget_items, monthly_plan_cycles, "
                "monthly_budget_plans, transactions, users RESTART IDENTITY CASCADE"
            )
        yield p
    finally:
        await p.close()


async def _seed_user(pool, telegram_id=955101, role="oyijon") -> int:
    return await pool.fetchval(
        "INSERT INTO users (telegram_id, role, display_name) "
        "VALUES ($1,$2,'Stage 5.3A Get') RETURNING id",
        telegram_id, role,
    )


# --- pure schema (always run) ---
@pytest.mark.asyncio
async def test_registered_and_schema():
    tools = await server.list_tools()
    names = [t.name for t in tools]
    assert names.count("get_monthly_plan_cycle") == 1
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 24
    schema = {t.name: t.inputSchema for t in tools}["get_monthly_plan_cycle"]
    assert schema["required"] == ["user_id", "month"]


# --- DB integration ---
@requires_db
@pytest.mark.asyncio
async def test_absent_cycle_reports_exists_false(pool):
    uid = await _seed_user(pool)
    r = await db.get_monthly_plan_cycle(pool, uid, MONTH)
    assert r["exists"] is False
    assert r["status"] is None and r["approved_at"] is None


@requires_db
@pytest.mark.asyncio
async def test_reads_status_after_open(pool):
    uid = await _seed_user(pool)
    await pool.execute(
        "INSERT INTO monthly_plan_cycles (user_id, month, status, source) "
        "VALUES ($1,$2,'waiting_oyijon','calculated')",
        uid, MONTH_D,
    )
    r = await db.get_monthly_plan_cycle(pool, uid, MONTH)
    assert r["exists"] is True
    assert r["status"] == "waiting_oyijon"
    assert r["source"] == "calculated"


@requires_db
@pytest.mark.asyncio
async def test_read_is_pure_no_mutation(pool):
    uid = await _seed_user(pool)
    before = await pool.fetchval("SELECT COUNT(*) FROM monthly_plan_cycles")
    await db.get_monthly_plan_cycle(pool, uid, MONTH)
    after = await pool.fetchval("SELECT COUNT(*) FROM monthly_plan_cycles")
    assert before == after == 0


@requires_db
@pytest.mark.asyncio
async def test_dispatch_ok_shape(pool):
    uid = await _seed_user(pool)
    content = await server.t_get_monthly_plan_cycle(pool, {"user_id": uid, "month": MONTH})
    assert content["ok"] is True and content["exists"] is False


@pytest.mark.asyncio
async def test_bad_month_via_mcp():
    content = await server.call_tool("get_monthly_plan_cycle", {"user_id": 1})
    r = json.loads(content[0].text)
    assert r["ok"] is False and r["error_code"] == "INVALID_INPUT"
