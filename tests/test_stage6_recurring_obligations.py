"""Stage 6 — migration 005 and recurring-obligation tool contracts."""
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
SQL_005 = REPO / "backend" / "sql" / "005_stage6_recurring_obligations.sql"


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
            await conn.execute("DROP TABLE IF EXISTS recurring_obligations")
            await conn.execute(SQL_005.read_text(encoding="utf-8"))
            await conn.execute(
                "TRUNCATE recurring_obligations, transactions, users "
                "RESTART IDENTITY CASCADE"
            )
        yield p
    finally:
        await p.close()


async def _seed_user(pool, telegram_id: int) -> int:
    return await pool.fetchval(
        "INSERT INTO users (telegram_id, role, display_name) "
        "VALUES ($1,'oyijon','Stage 6 Test') RETURNING id",
        telegram_id,
    )


async def _upsert(
    pool,
    user_id,
    *,
    name="Internet",
    due_date="2027-01-31",
    repeat_rule="monthly",
    repeat_interval_days=None,
):
    return await db.upsert_recurring_obligation(
        pool,
        user_id,
        "upsert",
        obligation_type="internet",
        name=name,
        expected_amount_uzs=150000,
        due_date=due_date,
        repeat_rule=repeat_rule,
        repeat_interval_days=repeat_interval_days,
        reminder_lead_days=3,
    )


@pytest.mark.asyncio
async def test_inventory_dispatch_and_schemas_are_26():
    tools = await server.list_tools()
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 26
    schemas = {tool.name: tool.inputSchema for tool in tools}
    assert schemas["upsert_recurring_obligation"]["required"] == [
        "user_id",
        "action",
    ]
    assert schemas["get_recurring_obligations"]["required"] == ["user_id"]
    assert schemas["upsert_recurring_obligation"]["properties"]["action"]["enum"] == [
        "upsert",
        "mark_paid",
        "disable",
    ]
    assert schemas["upsert_recurring_obligation"]["properties"]["repeat_rule"][
        "enum"
    ] == ["none", "monthly", "yearly", "interval_days"]


@pytest.mark.asyncio
async def test_required_fields_fail_before_dispatch():
    content = await server.call_tool("upsert_recurring_obligation", {"user_id": 1})
    result = json.loads(content[0].text)
    assert result["ok"] is False
    assert result["error_code"] == "INVALID_INPUT"


@pytest.mark.parametrize(
    "current,rule,interval,anchor_month,anchor_day,expected",
    [
        (date(2027, 1, 31), "monthly", None, 1, 31, date(2027, 2, 28)),
        (date(2027, 2, 28), "monthly", None, 1, 31, date(2027, 3, 31)),
        (date(2027, 12, 31), "monthly", None, 12, 31, date(2028, 1, 31)),
        (date(2024, 2, 29), "yearly", None, 2, 29, date(2025, 2, 28)),
        (date(2027, 2, 28), "yearly", None, 2, 29, date(2028, 2, 29)),
        (date(2027, 12, 20), "interval_days", 20, 12, 20, date(2028, 1, 9)),
    ],
)
def test_repeat_rule_calendar_edges(
    current, rule, interval, anchor_month, anchor_day, expected
):
    assert db._next_obligation_due_date(
        current, rule, interval, anchor_month, anchor_day
    ) == expected


def test_non_repeating_rule_has_no_next_date():
    assert db._next_obligation_due_date(
        date(2027, 1, 31), "none", None, 1, 31
    ) is None


@requires_db
@pytest.mark.asyncio
async def test_natural_key_upsert_is_idempotent(pool):
    uid = await _seed_user(pool, 956101)
    first = await _upsert(pool, uid)
    second = await _upsert(pool, uid)
    assert first["obligation_id"] == second["obligation_id"]
    assert first["idempotent"] is False and second["idempotent"] is True
    assert await pool.fetchval(
        "SELECT COUNT(*) FROM recurring_obligations WHERE user_id=$1", uid
    ) == 1


@requires_db
@pytest.mark.asyncio
async def test_monthly_paid_replay_advances_only_once_and_restores_31(pool):
    uid = await _seed_user(pool, 956102)
    created = await _upsert(pool, uid)
    oid = created["obligation_id"]
    first = await db.upsert_recurring_obligation(
        pool, uid, "mark_paid", obligation_id=oid, due_date="2027-01-31"
    )
    assert first["due_date"] == "2027-02-28"
    assert first["last_paid_due_date"] == "2027-01-31"
    replay = await db.upsert_recurring_obligation(
        pool, uid, "mark_paid", obligation_id=oid, due_date="2027-01-31"
    )
    assert replay["idempotent"] is True
    assert replay["due_date"] == "2027-02-28"
    next_occurrence = await db.upsert_recurring_obligation(
        pool, uid, "mark_paid", obligation_id=oid, due_date="2027-02-28"
    )
    assert next_occurrence["due_date"] == "2027-03-31"


@requires_db
@pytest.mark.asyncio
async def test_one_time_paid_stops_and_never_creates_transaction(pool):
    uid = await _seed_user(pool, 956103)
    created = await _upsert(
        pool, uid, name="Tax", due_date="2027-12-31", repeat_rule="none"
    )
    before = await pool.fetchval(
        "SELECT COUNT(*) FROM transactions WHERE user_id=$1", uid
    )
    paid = await db.upsert_recurring_obligation(
        pool,
        uid,
        "mark_paid",
        obligation_id=created["obligation_id"],
        due_date="2027-12-31",
    )
    after = await pool.fetchval(
        "SELECT COUNT(*) FROM transactions WHERE user_id=$1", uid
    )
    assert paid["paid"] is True and paid["active"] is False
    assert before == after == 0


@requires_db
@pytest.mark.asyncio
async def test_due_date_mismatch_has_zero_mutation(pool):
    uid = await _seed_user(pool, 956104)
    created = await _upsert(pool, uid)
    result = await db.upsert_recurring_obligation(
        pool,
        uid,
        "mark_paid",
        obligation_id=created["obligation_id"],
        due_date="2027-01-30",
    )
    assert result["_obligation_error"] == "DUE_DATE_MISMATCH"
    due = await pool.fetchval(
        "SELECT due_date FROM recurring_obligations WHERE id=$1",
        created["obligation_id"],
    )
    assert due == date(2027, 1, 31)


@requires_db
@pytest.mark.asyncio
async def test_disable_and_active_due_query_are_scoped(pool):
    first_user = await _seed_user(pool, 956105)
    second_user = await _seed_user(pool, 956106)
    first = await _upsert(pool, first_user, name="Internet A", due_date="2027-01-10")
    await _upsert(pool, first_user, name="Internet B", due_date="2027-02-10")
    await _upsert(pool, second_user, name="Foreign", due_date="2027-01-10")
    disabled = await db.upsert_recurring_obligation(
        pool, first_user, "disable", obligation_id=first["obligation_id"]
    )
    assert disabled["active"] is False
    replay = await db.upsert_recurring_obligation(
        pool, first_user, "disable", obligation_id=first["obligation_id"]
    )
    assert replay["idempotent"] is True
    result = await db.get_recurring_obligations(
        pool,
        first_user,
        active_only=True,
        due_from="2027-02-01",
        due_to="2027-02-28",
    )
    assert [item["name"] for item in result["obligations"]] == ["Internet B"]


@requires_db
@pytest.mark.asyncio
async def test_server_maps_domain_error_without_mutation(pool):
    uid = await _seed_user(pool, 956107)
    created = await _upsert(pool, uid)
    result = await server.t_upsert_recurring_obligation(
        pool,
        {
            "user_id": uid,
            "action": "mark_paid",
            "obligation_id": created["obligation_id"],
            "due_date": "2027-01-30",
        },
    )
    assert result["ok"] is False
    assert result["error_code"] == "DUE_DATE_MISMATCH"
