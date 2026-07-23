"""Stage 5.3A — approve_monthly_plan tool, deterministic status state machine.

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


# --- helpers ---------------------------------------------------------------
def _t(y, mo, d, h=12) -> datetime:
    """Asia/Tashkent wall-clock instant (tz-aware)."""
    return datetime(y, mo, d, h, tzinfo=TASHKENT)


BEFORE = _t(2026, 7, 31, 12)     # last day before planned month
DAY1 = _t(2026, 8, 1, 6)         # first day of planned month
DAY2 = _t(2026, 8, 2, 0)         # month already underway


async def _seed_user(pool, telegram_id=953101, role="oyijon") -> int:
    return await pool.fetchval(
        "INSERT INTO users (telegram_id, role, display_name) "
        "VALUES ($1,$2,'Stage 5.3A Test') RETURNING id",
        telegram_id, role,
    )


async def _plan(pool, user_id, month=MONTH_D, *, category="food", planned=500000):
    await pool.execute(
        "INSERT INTO monthly_budget_plans (user_id, month, category_code, planned_amount_uzs) "
        "VALUES ($1,$2,$3,$4)",
        user_id, month, category, planned,
    )


async def _cycle(pool, user_id, month=MONTH_D, *, status="waiting_oyijon", source="calculated"):
    await pool.execute(
        "INSERT INTO monthly_plan_cycles (user_id, month, status, source) VALUES ($1,$2,$3,$4)",
        user_id, month, status, source,
    )


async def _status(pool, user_id, month=MONTH_D):
    return await pool.fetchval(
        "SELECT status FROM monthly_plan_cycles WHERE user_id=$1 AND month=$2",
        user_id, month,
    )


async def _row_count(pool, user_id, month=MONTH_D):
    return await pool.fetchval(
        "SELECT COUNT(*) FROM monthly_plan_cycles WHERE user_id=$1 AND month=$2",
        user_id, month,
    )


# ===========================================================================
# Pure schema / dispatch (always run)
# ===========================================================================
@pytest.mark.asyncio
async def test_tool_is_registered_and_callable():
    tools = await server.list_tools()
    names = [t.name for t in tools]
    assert names.count("approve_monthly_plan") == 1
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 24
    assert "approve_monthly_plan" in server.DISPATCH

    schema = {t.name: t.inputSchema for t in tools}["approve_monthly_plan"]
    assert schema["required"] == ["user_id", "month", "source"]
    assert schema["properties"]["source"]["enum"] == ["oyijon", "admin", "auto"]


def test_approval_sources_and_target_map():
    assert db.APPROVAL_SOURCES == ("oyijon", "admin", "auto")
    assert db._APPROVAL_TARGET_STATUS["oyijon"] == "approved_by_oyijon"
    assert db._APPROVAL_TARGET_STATUS["admin"] == "approved_by_admin"
    assert db._APPROVAL_TARGET_STATUS["auto"] == "auto_approved"


@requires_db
@pytest.mark.asyncio
async def test_invalid_source_rejected_via_mcp():
    content = await server.call_tool(
        "approve_monthly_plan",
        {"user_id": 1, "month": MONTH, "source": "bogus"},
    )
    r = json.loads(content[0].text)
    assert r["ok"] is False and r["error_code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_missing_required_rejected_via_mcp():
    content = await server.call_tool("approve_monthly_plan", {"user_id": 1})
    r = json.loads(content[0].text)
    assert r["ok"] is False and r["error_code"] == "INVALID_INPUT"


# ===========================================================================
# DB integration — state machine
# ===========================================================================
@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("start_status", ["draft", "waiting_oyijon", "waiting_admin"])
async def test_oyijon_approves_from_any_non_terminal(pool, start_status):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status=start_status)
    r = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=BEFORE)
    assert r.get("_cycle_error") is None, r
    assert r["status"] == "approved_by_oyijon"
    assert r["approved_by_user_id"] == uid
    assert r["idempotent"] is False and r["plan_copied"] is False
    assert await _status(pool, uid) == "approved_by_oyijon"


@requires_db
@pytest.mark.asyncio
async def test_admin_approves_target_future_month(pool):
    oy = await _seed_user(pool, 953201, "oyijon")
    admin = await _seed_user(pool, 953202, "admin")
    await _plan(pool, oy)
    await _cycle(pool, oy, status="waiting_admin")
    r = await db.approve_monthly_plan(
        pool, oy, MONTH, "admin", approved_by_user_id=admin, now=BEFORE
    )
    assert r.get("_cycle_error") is None, r
    assert r["status"] == "approved_by_admin"
    assert r["approved_by_user_id"] == admin


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal,other_source",
    [
        ("approved_by_admin", "oyijon"),
        ("approved_by_oyijon", "admin"),
        ("auto_approved", "oyijon"),
    ],
)
async def test_terminal_status_blocks_other_transition(pool, terminal, other_source):
    uid = await _seed_user(pool)
    admin = await _seed_user(pool, 953203, "admin")
    await _plan(pool, uid)
    await _cycle(pool, uid, status=terminal)
    kw = {"approved_by_user_id": admin} if other_source == "admin" else {}
    r = await db.approve_monthly_plan(pool, uid, MONTH, other_source, now=BEFORE, **kw)
    assert r["_cycle_error"] == "INVALID_STATUS_TRANSITION"
    assert await _status(pool, uid) == terminal  # unchanged


@requires_db
@pytest.mark.asyncio
async def test_idempotent_repeat_no_second_write(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")
    first = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=BEFORE)
    assert first["idempotent"] is False
    second = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=DAY1)
    # DAY1 is "already started" for manual, but idempotent replay short-circuits
    # before the boundary check only if status already matches... verify:
    assert second["idempotent"] is True
    assert second["approved_at"] == first["approved_at"]  # no re-stamp
    assert await _row_count(pool, uid) == 1


@requires_db
@pytest.mark.asyncio
async def test_empty_draft_not_approved(pool):
    uid = await _seed_user(pool)
    await _cycle(pool, uid, status="waiting_oyijon")  # cycle row but NO plan rows
    r = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=BEFORE)
    assert r["_cycle_error"] == "EMPTY_DRAFT"
    assert await _status(pool, uid) == "waiting_oyijon"


@requires_db
@pytest.mark.asyncio
async def test_zero_amount_draft_is_empty(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid, planned=0)
    await _cycle(pool, uid, status="waiting_oyijon")
    r = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=BEFORE)
    assert r["_cycle_error"] == "EMPTY_DRAFT"


@requires_db
@pytest.mark.asyncio
async def test_manual_without_draft_row(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)  # plan rows but no cycle row
    r = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=BEFORE)
    assert r["_cycle_error"] == "NO_DRAFT"


# ===========================================================================
# DB integration — month boundaries
# ===========================================================================
@requires_db
@pytest.mark.asyncio
async def test_manual_refused_once_month_started(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")
    r = await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", now=DAY1)
    assert r["_cycle_error"] == "MONTH_ALREADY_STARTED"
    assert await _status(pool, uid) == "waiting_oyijon"


@requires_db
@pytest.mark.asyncio
async def test_auto_only_on_first_day(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")

    early = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=BEFORE)
    assert early["_cycle_error"] == "MONTH_NOT_STARTED"

    late = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=DAY2)
    assert late["_cycle_error"] == "MONTH_ALREADY_STARTED"

    ok = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=DAY1)
    assert ok.get("_cycle_error") is None
    assert ok["status"] == "auto_approved"


# ===========================================================================
# DB integration — identity rails
# ===========================================================================
@requires_db
@pytest.mark.asyncio
async def test_oyijon_self_only(pool):
    uid = await _seed_user(pool)
    other = await _seed_user(pool, 953301, "oyijon")
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")
    r = await db.approve_monthly_plan(
        pool, uid, MONTH, "oyijon", approved_by_user_id=other, now=BEFORE
    )
    assert r["_cycle_error"] == "SELF_ONLY_VIOLATION"


@requires_db
@pytest.mark.asyncio
async def test_admin_requires_distinct_target(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_admin")
    missing = await db.approve_monthly_plan(pool, uid, MONTH, "admin", now=BEFORE)
    assert missing["_cycle_error"] == "ADMIN_TARGET_REQUIRED"
    same = await db.approve_monthly_plan(
        pool, uid, MONTH, "admin", approved_by_user_id=uid, now=BEFORE
    )
    assert same["_cycle_error"] == "ADMIN_TARGET_REQUIRED"


@requires_db
@pytest.mark.asyncio
async def test_auto_rejects_explicit_approver(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")
    r = await db.approve_monthly_plan(
        pool, uid, MONTH, "auto", approved_by_user_id=uid, now=DAY1
    )
    assert r["_cycle_error"] == "INVALID_APPROVER"


# ===========================================================================
# DB integration — auto copy-last-approved
# ===========================================================================
@requires_db
@pytest.mark.asyncio
async def test_auto_copies_last_approved_when_no_draft(pool):
    uid = await _seed_user(pool)
    # previous approved month (July) with plan rows
    await _plan(pool, uid, month=date(2026, 7, 1), category="food", planned=400000)
    await _plan(pool, uid, month=date(2026, 7, 1), category="transport", planned=150000)
    await _cycle(pool, uid, month=date(2026, 7, 1), status="approved_by_oyijon")
    # August: no draft at all
    r = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=DAY1)
    assert r.get("_cycle_error") is None, r
    assert r["status"] == "auto_approved"
    assert r["source"] == "copied_previous"
    assert r["plan_copied"] is True
    copied = await pool.fetch(
        "SELECT category_code, planned_amount_uzs FROM monthly_budget_plans "
        "WHERE user_id=$1 AND month=$2 ORDER BY category_code",
        uid, MONTH_D,
    )
    assert [(c["category_code"], int(c["planned_amount_uzs"])) for c in copied] == [
        ("food", 400000),
        ("transport", 150000),
    ]


@requires_db
@pytest.mark.asyncio
async def test_auto_no_draft_no_previous(pool):
    uid = await _seed_user(pool)
    r = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=DAY1)
    assert r["_cycle_error"] == "NO_PLAN_SOURCE"
    assert await _row_count(pool, uid) == 0


@requires_db
@pytest.mark.asyncio
async def test_auto_approves_existing_valid_draft(pool):
    uid = await _seed_user(pool)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_admin")
    r = await db.approve_monthly_plan(pool, uid, MONTH, "auto", now=DAY1)
    assert r["status"] == "auto_approved"
    assert r["plan_copied"] is False
    assert r["source"] == "calculated"  # keeps original draft source


# ===========================================================================
# DB integration — no transaction side effects + household_size + MCP layer
# ===========================================================================
@requires_db
@pytest.mark.asyncio
async def test_does_not_touch_transactions(pool):
    uid = await _seed_user(pool)
    await pool.execute(
        "INSERT INTO transactions (user_id, type, amount, currency, category_code, "
        "item_name, source_type, occurred_at) VALUES "
        "($1,'expense',12000,'UZS','food.bread','нон','text', now())",
        uid,
    )
    before = await pool.fetchval("SELECT COUNT(*) FROM transactions WHERE user_id=$1", uid)
    await _plan(pool, uid)
    await _cycle(pool, uid, status="waiting_oyijon")
    await db.approve_monthly_plan(pool, uid, MONTH, "oyijon", household_size=4, now=BEFORE)
    after = await pool.fetchval("SELECT COUNT(*) FROM transactions WHERE user_id=$1", uid)
    assert before == after == 1
    hh = await pool.fetchval(
        "SELECT household_size FROM monthly_plan_cycles WHERE user_id=$1 AND month=$2",
        uid, MONTH_D,
    )
    assert hh == 4


def test_every_cycle_error_code_has_bilingual_message():
    # Every _cycle_err(...) code the db layer can return must map to a message.
    codes = {
        "MONTH_ALREADY_STARTED", "MONTH_NOT_STARTED", "NO_DRAFT", "EMPTY_DRAFT",
        "NO_PLAN_SOURCE", "INVALID_STATUS_TRANSITION", "SELF_ONLY_VIOLATION",
        "ADMIN_TARGET_REQUIRED", "INVALID_APPROVER",
    }
    assert codes <= set(server.CYCLE_ERRORS)
    for ru, uz in server.CYCLE_ERRORS.values():
        assert ru and uz


@requires_db
@pytest.mark.asyncio
async def test_dispatch_maps_ok_and_error(pool):
    """t_approve_monthly_plan wraps db results into ok/err shapes."""
    uid = await _seed_user(pool)
    # Far-future month with a valid draft → ok.
    await _plan(pool, uid, month=date(2030, 1, 1))
    await _cycle(pool, uid, month=date(2030, 1, 1), status="waiting_oyijon")
    ok_r = await server.t_approve_monthly_plan(
        pool, {"user_id": uid, "month": "2030-01-01", "source": "oyijon"}
    )
    assert ok_r["ok"] is True and ok_r["status"] == "approved_by_oyijon"

    # Past month → manual approval deterministically refused, mapped bilingual.
    await _plan(pool, uid, month=date(2020, 1, 1))
    await _cycle(pool, uid, month=date(2020, 1, 1), status="waiting_oyijon")
    err_r = await server.t_approve_monthly_plan(
        pool, {"user_id": uid, "month": "2020-01-01", "source": "oyijon"}
    )
    assert err_r["ok"] is False
    assert err_r["error_code"] == "MONTH_ALREADY_STARTED"
    assert err_r["message_ru"] and err_r["message_uz"]
