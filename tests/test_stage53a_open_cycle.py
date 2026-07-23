"""Stage 5.3A — open_monthly_plan_cycle (variant A): narrow cycle-status mutation.

Pure schema/dispatch tests always run. PostgreSQL integration tests run only
against a validated disposable ``*_test`` database with ``APP_ENV=test``.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from backend import db, server
from tests.db_guard import validate_destructive_test_target

TASHKENT = ZoneInfo("Asia/Tashkent")
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


def _t(y, mo, d, h=12) -> datetime:
    return datetime(y, mo, d, h, tzinfo=TASHKENT)


BEFORE = _t(2026, 7, 31, 12)
DAY1 = _t(2026, 8, 1, 6)


async def _seed_user(pool, telegram_id=954101, role="oyijon") -> int:
    return await pool.fetchval(
        "INSERT INTO users (telegram_id, role, display_name) "
        "VALUES ($1,$2,'Stage 5.3A Open') RETURNING id",
        telegram_id, role,
    )


async def _plan(pool, user_id, month=MONTH_D, *, category="food", planned=500000):
    await pool.execute(
        "INSERT INTO monthly_budget_plans (user_id, month, category_code, planned_amount_uzs) "
        "VALUES ($1,$2,$3,$4)",
        user_id, month, category, planned,
    )


async def _cycle(pool, user_id, month=MONTH_D, *, status, source="calculated"):
    await pool.execute(
        "INSERT INTO monthly_plan_cycles (user_id, month, status, source) VALUES ($1,$2,$3,$4)",
        user_id, month, status, source,
    )


async def _status(pool, user_id, month=MONTH_D):
    return await pool.fetchval(
        "SELECT status FROM monthly_plan_cycles WHERE user_id=$1 AND month=$2",
        user_id, month,
    )


async def _count(pool, user_id, month=MONTH_D):
    return await pool.fetchval(
        "SELECT COUNT(*) FROM monthly_plan_cycles WHERE user_id=$1 AND month=$2",
        user_id, month,
    )


# ===========================================================================
# Pure schema / dispatch (always run)
# ===========================================================================
@pytest.mark.asyncio
async def test_tool_registered_and_schema():
    tools = await server.list_tools()
    names = [t.name for t in tools]
    assert names.count("open_monthly_plan_cycle") == 1
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 23
    schema = {t.name: t.inputSchema for t in tools}["open_monthly_plan_cycle"]
    assert schema["required"] == ["user_id", "month", "action"]
    assert schema["properties"]["action"]["enum"] == ["open", "escalate"]


def test_cycle_actions_constant():
    assert db.CYCLE_ACTIONS == ("open", "escalate")


@pytest.mark.asyncio
async def test_missing_required_via_mcp():
    content = await server.call_tool("open_monthly_plan_cycle", {"user_id": 1})
    r = json.loads(content[0].text)
    assert r["ok"] is False and r["error_code"] == "INVALID_INPUT"


# ===========================================================================
# DB integration — action=open
# ===========================================================================
@requires_db
@pytest.mark.asyncio
async def test_open_creates_waiting_oyijon(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=BEFORE)
    assert r.get("_cycle_error") is None, r
    assert r["status"] == "waiting_oyijon"
    assert r["source"] == "calculated"
    assert r["created"] is True and r["idempotent"] is False
    assert await _status(pool, uid) == "waiting_oyijon"


@requires_db
@pytest.mark.asyncio
async def test_open_requires_valid_draft(pool):
    uid = await _seed_user(pool)
    empty = await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=BEFORE)
    assert empty["_cycle_error"] == "EMPTY_DRAFT"
    await _plan(pool, uid, planned=0)
    zero = await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=BEFORE)
    assert zero["_cycle_error"] == "EMPTY_DRAFT"
    assert await _count(pool, uid) == 0


@requires_db
@pytest.mark.asyncio
async def test_open_future_month_only(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=DAY1)
    assert r["_cycle_error"] == "MONTH_ALREADY_STARTED"
    assert await _count(pool, uid) == 0


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "existing",
    ["waiting_oyijon", "waiting_admin", "approved_by_oyijon", "auto_approved"],
)
async def test_open_idempotent_when_row_exists(pool, existing):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status=existing)
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=BEFORE)
    assert r.get("_cycle_error") is None, r
    assert r["idempotent"] is True and r["created"] is False
    assert r["status"] == existing
    assert await _count(pool, uid) == 1  # no duplicate row


@requires_db
@pytest.mark.asyncio
async def test_open_stores_household_size(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", household_size=5, now=BEFORE)
    hh = await pool.fetchval(
        "SELECT household_size FROM monthly_plan_cycles WHERE user_id=$1 AND month=$2",
        uid, MONTH_D,
    )
    assert hh == 5


# ===========================================================================
# DB integration — action=escalate
# ===========================================================================
@requires_db
@pytest.mark.asyncio
async def test_escalate_waiting_oyijon_to_admin(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "escalate", now=BEFORE)
    assert r.get("_cycle_error") is None, r
    assert r["status"] == "waiting_admin"
    assert r["idempotent"] is False and r["created"] is False


@requires_db
@pytest.mark.asyncio
async def test_escalate_idempotent_when_already_admin(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_admin")
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "escalate", now=BEFORE)
    assert r["idempotent"] is True and r["status"] == "waiting_admin"


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal", ["approved_by_oyijon", "approved_by_admin", "auto_approved"]
)
async def test_escalate_terminal_rejected(pool, terminal):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status=terminal)
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "escalate", now=BEFORE)
    assert r["_cycle_error"] == "INVALID_STATUS_TRANSITION"
    assert await _status(pool, uid) == terminal


@requires_db
@pytest.mark.asyncio
async def test_escalate_without_row(pool):
    uid = await _seed_user(pool)
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "escalate", now=BEFORE)
    assert r["_cycle_error"] == "NO_DRAFT"


@requires_db
@pytest.mark.asyncio
async def test_escalate_future_month_only(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")
    r = await db.open_monthly_plan_cycle(pool, uid, MONTH, "escalate", now=DAY1)
    assert r["_cycle_error"] == "MONTH_ALREADY_STARTED"
    assert await _status(pool, uid) == "waiting_oyijon"


@requires_db
@pytest.mark.asyncio
async def test_open_and_escalate_do_not_touch_budget_or_transactions(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await pool.execute(
        "INSERT INTO transactions (user_id, type, amount, currency, category_code, "
        "item_name, source_type, occurred_at) VALUES "
        "($1,'expense',12000,'UZS','food.bread','нон','text', now())",
        uid,
    )
    tx_before = await pool.fetchval("SELECT COUNT(*) FROM transactions WHERE user_id=$1", uid)
    bp_before = await pool.fetchval(
        "SELECT COUNT(*) FROM monthly_budget_plans WHERE user_id=$1", uid
    )
    await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=BEFORE)
    await db.open_monthly_plan_cycle(pool, uid, MONTH, "escalate", now=BEFORE)
    assert await pool.fetchval(
        "SELECT COUNT(*) FROM transactions WHERE user_id=$1", uid
    ) == tx_before == 1
    assert await pool.fetchval(
        "SELECT COUNT(*) FROM monthly_budget_plans WHERE user_id=$1", uid
    ) == bp_before == 1


# ===========================================================================
# DB integration — integration with approve_monthly_plan (variant A end-to-end)
# ===========================================================================
@requires_db
@pytest.mark.asyncio
async def test_open_then_oyijon_approve(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=BEFORE)
    r = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=BEFORE)
    assert r.get("_cycle_error") is None, r
    assert r["status"] == "approved_by_oyijon"


@requires_db
@pytest.mark.asyncio
async def test_open_escalate_then_admin_approve(pool):
    oy = await _seed_user(pool, 954201, "oyijon")
    admin = await _seed_user(pool, 954202, "admin")
    await _plan(pool, oy)
    await db.open_monthly_plan_cycle(pool, oy, MONTH, "open", now=BEFORE)
    await db.open_monthly_plan_cycle(pool, oy, MONTH, "escalate", now=BEFORE)
    assert await _status(pool, oy) == "waiting_admin"
    r = await db.approve_monthly_plan(
        pool, oy, MONTH, "admin", approved_by_user_id=admin, now=BEFORE
    )
    assert r["status"] == "approved_by_admin"


@requires_db
@pytest.mark.asyncio
async def test_open_then_auto_on_first_day(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await db.open_monthly_plan_cycle(pool, uid, MONTH, "open", now=BEFORE)
    r = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=DAY1)
    assert r["status"] == "auto_approved"
    assert r["plan_copied"] is False  # approves the existing opened draft
    replay = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=DAY1)
    assert replay["idempotent"] is True
    assert await _count(pool, uid) == 1


@requires_db
@pytest.mark.asyncio
async def test_dispatch_ok_and_error_mapping(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid, month=date(2030, 1, 1))
    ok_r = await server.t_open_monthly_plan_cycle(
        pool, {"user_id": uid, "month": "2030-01-01", "action": "open"}
    )
    assert ok_r["ok"] is True and ok_r["status"] == "waiting_oyijon"

    await _plan(pool, uid, month=date(2020, 1, 1))
    err_r = await server.t_open_monthly_plan_cycle(
        pool, {"user_id": uid, "month": "2020-01-01", "action": "open"}
    )
    assert err_r["ok"] is False
    assert err_r["error_code"] == "MONTH_ALREADY_STARTED"
    assert err_r["message_ru"] and err_r["message_uz"]
