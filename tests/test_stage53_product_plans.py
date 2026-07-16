"""Permanent Stage 5.3 product-plan, price-snapshot and MCP contracts.

Pure schema/tool tests always run. PostgreSQL integration tests run only against a
validated disposable ``*_test`` database with ``APP_ENV=test``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio

from backend import db, server
from tests.db_guard import validate_destructive_test_target

REPO = Path(__file__).resolve().parents[1]
SQL_001 = REPO / "backend" / "sql" / "001_init.sql"
SQL_002 = REPO / "backend" / "sql" / "002_stage51_quantity_budget.sql"
SQL_003 = REPO / "backend" / "sql" / "003_stage53_product_plans.sql"
GUARD = (
    REPO
    / "deploy"
    / "hermes_plugins"
    / "mariyam_identity_guard"
    / "__init__.py"
)


def _db_available() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    env = os.environ.get("APP_ENV")
    if env != "test" or not url:
        return False
    try:
        validate_destructive_test_target(
            database_url=url,
            app_env=env,
            allow_remote=os.environ.get("ALLOW_DESTRUCTIVE_TESTS") == "1",
        )
    except Exception:
        return False
    return True


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="APP_ENV=test + validated *_test DATABASE_URL required",
)


@pytest_asyncio.fixture
async def stage53_pool():
    if not _db_available():
        pytest.skip("requires disposable PostgreSQL test database")
    import asyncpg

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            await conn.execute(SQL_001.read_text(encoding="utf-8"))
            await conn.execute(SQL_002.read_text(encoding="utf-8"))
            await conn.execute(SQL_003.read_text(encoding="utf-8"))
            await conn.execute(SQL_003.read_text(encoding="utf-8"))
            await conn.execute(
                "TRUNCATE monthly_budget_items, monthly_plan_cycles, "
                "monthly_budget_plans, transactions, users RESTART IDENTITY CASCADE"
            )
        yield pool
    finally:
        await pool.close()


async def _seed_user(pool, telegram_id: int = 953001) -> int:
    return await pool.fetchval(
        """INSERT INTO users (telegram_id, role, display_name)
           VALUES ($1, 'oyijon', 'Stage 5.3 Test') RETURNING id""",
        telegram_id,
    )


async def _call_json(name: str, arguments: dict) -> dict:
    content = await server.call_tool(name, arguments)
    return json.loads(content[0].text)


async def _insert_expense(
    pool,
    user_id: int,
    *,
    amount,
    category: str,
    item: str,
    occurred_at: datetime,
    quantity=None,
    unit=None,
):
    return await pool.fetchval(
        """INSERT INTO transactions
           (user_id, type, amount, currency, category_code, item_name,
            item_name_normalized, quantity, unit, source_type, occurred_at)
           VALUES ($1, 'expense', $2, 'UZS', $3, $4, $4, $5, $6, 'text', $7)
           RETURNING id""",
        user_id,
        amount,
        category,
        item,
        quantity,
        unit,
        occurred_at,
    )


def _item(
    name: str,
    *,
    quantity=None,
    unit=None,
    amount=None,
    price=None,
    basis=None,
    price_as_of=None,
    note=None,
):
    value = {
        "item_name_normalized": name,
        "item_name_display": name.capitalize(),
    }
    if quantity is not None:
        value["planned_quantity"] = quantity
    if unit is not None:
        value["unit"] = unit
    if amount is not None:
        value["planned_amount_uzs"] = amount
    if price is not None:
        value["reference_unit_price_uzs"] = price
    if basis is not None:
        value["price_basis"] = basis
    if price_as_of is not None:
        value["price_as_of"] = price_as_of
    if note is not None:
        value["note"] = note
    return value


# ---------------------------------------------------------------------------
# Migration and static contracts
# ---------------------------------------------------------------------------


def test_stage53_migration_declares_both_tables_and_guards():
    text = SQL_003.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS monthly_budget_items" in text
    assert "CREATE TABLE IF NOT EXISTS monthly_plan_cycles" in text
    assert "UNIQUE (user_id, month, category_code, item_name_normalized)" in text
    assert "UNIQUE (user_id, month)" in text
    assert "planned_quantity IS NOT NULL OR planned_amount_uzs IS NOT NULL" in text
    assert "date_trunc('month', month)::date = month" in text
    assert "('kg', 'g', 'l', 'ml', 'pcs', 'pack')" in text
    assert "('last', 'average', 'manual')" in text
    assert "DROP TABLE" not in text.upper()
    assert "ALTER TABLE transactions" not in text


@requires_db
@pytest.mark.asyncio
async def test_migration_003_first_and_second_apply_schema_and_old_transactions(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    tx_id = await _insert_expense(
        pool,
        user_id,
        amount=12000,
        category="food.bread",
        item="нон",
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    before = await pool.fetchrow("SELECT * FROM transactions WHERE id=$1", tx_id)

    async with pool.acquire() as conn:
        await conn.execute(SQL_003.read_text(encoding="utf-8"))
        await conn.execute(SQL_003.read_text(encoding="utf-8"))

    after = await pool.fetchrow("SELECT * FROM transactions WHERE id=$1", tx_id)
    assert dict(after) == dict(before)
    tables = {
        row["table_name"]
        for row in await pool.fetch(
            """SELECT table_name FROM information_schema.tables
               WHERE table_schema='public'
                 AND table_name IN ('monthly_budget_items','monthly_plan_cycles')"""
        )
    }
    assert tables == {"monthly_budget_items", "monthly_plan_cycles"}
    indexes = {
        row["indexname"]
        for row in await pool.fetch(
            """SELECT indexname FROM pg_indexes
               WHERE schemaname='public'
                 AND tablename IN ('monthly_budget_items','monthly_plan_cycles')"""
        )
    }
    assert "idx_mbi_user_month" in indexes
    assert "idx_mpc_user_month" in indexes


# ---------------------------------------------------------------------------
# Storage validation and atomic replacement
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_category_only_budget_remains_compatible_and_does_not_delete_items(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    first = await db.set_monthly_budget(
        pool,
        user_id,
        "2026-08-01",
        "food",
        500000,
        items=[_item("картошка", quantity=20, unit="kg", amount=160000)],
    )
    second = await db.set_monthly_budget(
        pool, user_id, "2026-08-01", "food", 600000, note="category only"
    )
    assert first["created"] is True
    assert second == {"plan_id": first["plan_id"], "created": False}
    assert await pool.fetchval(
        "SELECT count(*) FROM monthly_budget_items WHERE user_id=$1", user_id
    ) == 1


@requires_db
@pytest.mark.asyncio
async def test_product_plan_save_and_atomic_stale_replacement(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-08-01",
        "food",
        700000,
        items=[
            _item("картошка", quantity=20, unit="kg", amount=160000),
            _item("гўшт", quantity=5, unit="kg", amount=550000),
        ],
    )
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-08-01",
        "food",
        250000,
        items=[_item("картошка", quantity=25, unit="kg", amount=250000)],
    )
    rows = await pool.fetch(
        """SELECT item_name_normalized, planned_quantity, planned_amount_uzs
           FROM monthly_budget_items WHERE user_id=$1 ORDER BY item_name_normalized""",
        user_id,
    )
    assert [row["item_name_normalized"] for row in rows] == ["картошка"]
    assert rows[0]["planned_quantity"] == Decimal("25.000")
    assert rows[0]["planned_amount_uzs"] == Decimal("250000.00")


@requires_db
@pytest.mark.asyncio
async def test_duplicate_item_and_item_validation_rules(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    base = (pool, user_id, "2026-08-01", "food", 100000)

    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.set_monthly_budget(
            *base,
            items=[_item("картошка", amount=1), _item("картошка", amount=2)],
        )
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.set_monthly_budget(*base, items=[_item("картошка")])
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.set_monthly_budget(
            *base, items=[_item("картошка", amount=1, unit="kg")]
        )
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.set_monthly_budget(
            *base, items=[_item("картошка", quantity=1, unit="box")]
        )
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        await db.set_monthly_budget(
            *base,
            items=[_item("картошка", quantity=1, unit="kg", basis="manual")],
        )


@requires_db
@pytest.mark.asyncio
async def test_quantity_only_and_amount_only_items_are_allowed(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-08-01",
        "food",
        100000,
        items=[
            _item("картошка", quantity=20, unit="kg"),
            _item("нон", amount=100000),
        ],
    )
    rows = {
        row["item_name_normalized"]: row
        for row in await pool.fetch(
            "SELECT * FROM monthly_budget_items WHERE user_id=$1", user_id
        )
    }
    assert rows["картошка"]["planned_quantity"] == Decimal("20.000")
    assert rows["картошка"]["planned_amount_uzs"] is None
    assert rows["нон"]["planned_quantity"] is None
    assert rows["нон"]["planned_amount_uzs"] == Decimal("100000.00")


@requires_db
@pytest.mark.asyncio
async def test_failed_item_insert_rolls_back_plan_and_previous_items(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-08-01",
        "food",
        100000,
        items=[_item("нон", amount=100000)],
    )
    with pytest.raises(Exception):
        await db.set_monthly_budget(
            pool,
            user_id,
            "2026-08-01",
            "food",
            200000,
            items=[_item("картошка", amount=10**20)],
        )
    assert await pool.fetchval(
        """SELECT planned_amount_uzs FROM monthly_budget_plans
           WHERE user_id=$1 AND month='2026-08-01' AND category_code='food'""",
        user_id,
    ) == Decimal("100000.00")
    assert await pool.fetchval(
        """SELECT item_name_normalized FROM monthly_budget_items
           WHERE user_id=$1 AND month='2026-08-01' AND category_code='food'""",
        user_id,
    ) == "нон"


# ---------------------------------------------------------------------------
# Price and actual facts
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_last_weighted_average_manual_snapshot_and_derived_amount(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await _insert_expense(
        pool,
        user_id,
        amount=80000,
        category="food.vegetables",
        item="картошка",
        quantity=10,
        unit="kg",
        occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    await _insert_expense(
        pool,
        user_id,
        amount=45000,
        category="food.vegetables",
        item="картошка",
        quantity=5,
        unit="kg",
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    # Same item but another unit must not affect kg prices.
    await _insert_expense(
        pool,
        user_id,
        amount=10000,
        category="food.vegetables",
        item="картошка",
        quantity=500,
        unit="g",
        occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
    )
    # Missing quantity must not participate in unit prices.
    await _insert_expense(
        pool,
        user_id,
        amount=999999,
        category="food.vegetables",
        item="картошка",
        occurred_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )

    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-08-01",
        "food",
        300000,
        items=[
            _item("картошка", quantity=20, unit="kg", basis="last"),
            _item("сабзи", quantity=10, unit="kg", price=7000, basis="manual"),
        ],
    )
    status = await db.get_monthly_budget_status(
        pool, user_id, "2026-08-01", include_items=True
    )
    by_name = {item["item_name_normalized"]: item for item in status["items"]}
    potato = by_name["картошка"]
    assert potato["last_unit_price_uzs"] == 9000
    assert potato["average_unit_price_uzs"] == pytest.approx(125000 / 15)
    assert potato["reference_unit_price_uzs"] == 9000
    assert potato["price_basis"] == "last"
    assert potato["planned_amount_uzs"] == 180000
    carrot = by_name["сабзи"]
    assert carrot["reference_unit_price_uzs"] == 7000
    assert carrot["price_basis"] == "manual"
    assert carrot["planned_amount_uzs"] == 70000


@requires_db
@pytest.mark.asyncio
async def test_average_snapshot_is_weighted_and_immutable_after_new_purchase(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await _insert_expense(
        pool,
        user_id,
        amount=80000,
        category="food.vegetables",
        item="картошка",
        quantity=10,
        unit="kg",
        occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    await _insert_expense(
        pool,
        user_id,
        amount=50000,
        category="food.vegetables",
        item="картошка",
        quantity=5,
        unit="kg",
        occurred_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-08-01",
        "food",
        200000,
        items=[_item("картошка", quantity=15, unit="kg", basis="average")],
    )
    saved = await pool.fetchrow(
        "SELECT * FROM monthly_budget_items WHERE user_id=$1", user_id
    )
    assert float(saved["reference_unit_price_uzs"]) == pytest.approx(130000 / 15)

    await _insert_expense(
        pool,
        user_id,
        amount=20000,
        category="food.vegetables",
        item="картошка",
        quantity=1,
        unit="kg",
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    status = await db.get_monthly_budget_status(
        pool, user_id, "2026-08-01", include_items=True
    )
    potato = status["items"][0]
    assert potato["average_unit_price_uzs"] == pytest.approx(150000 / 16)
    assert potato["reference_unit_price_uzs"] == pytest.approx(130000 / 15)


@requires_db
@pytest.mark.asyncio
async def test_actuals_parent_food_exact_amount_homogeneous_quantity_and_category_filter(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-07-01",
        "food",
        300000,
        items=[_item("картошка", quantity=20, unit="kg", amount=160000)],
    )
    for amount, category, quantity in (
        (80000, "food.vegetables", 10),
        (40000, "food", 5),
    ):
        await _insert_expense(
            pool,
            user_id,
            amount=amount,
            category=category,
            item="картошка",
            quantity=quantity,
            unit="kg",
            occurred_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        )
    await _insert_expense(
        pool,
        user_id,
        amount=99999,
        category="home",
        item="картошка",
        quantity=9,
        unit="kg",
        occurred_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )
    status = await db.get_monthly_budget_status(
        pool, user_id, "2026-07-01", include_items=True
    )
    potato = status["items"][0]
    assert potato["actual_amount_uzs"] == 120000
    assert potato["actual_quantity"] == 15
    assert potato["actual_unit"] == "kg"
    assert potato["remaining_amount_uzs"] == 40000


@requires_db
@pytest.mark.asyncio
async def test_incompatible_or_missing_actual_quantity_is_null_but_amount_exact(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-07-01",
        "food",
        200000,
        items=[_item("картошка", amount=200000)],
    )
    await _insert_expense(
        pool,
        user_id,
        amount=80000,
        category="food.vegetables",
        item="картошка",
        quantity=10,
        unit="kg",
        occurred_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )
    await _insert_expense(
        pool,
        user_id,
        amount=10000,
        category="food.vegetables",
        item="картошка",
        quantity=500,
        unit="g",
        occurred_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )
    await _insert_expense(
        pool,
        user_id,
        amount=5000,
        category="food.vegetables",
        item="картошка",
        occurred_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )
    status = await db.get_monthly_budget_status(
        pool, user_id, "2026-07-01", include_items=True
    )
    potato = status["items"][0]
    assert potato["actual_amount_uzs"] == 95000
    assert potato["actual_quantity"] is None
    assert potato["actual_unit"] is None


@requires_db
@pytest.mark.asyncio
async def test_no_purchases_keeps_zero_actual_and_unknown_price_quantity_null(stage53_pool):
    pool = stage53_pool
    user_id = await _seed_user(pool)
    await db.set_monthly_budget(
        pool,
        user_id,
        "2026-07-01",
        "food",
        100000,
        items=[_item("номаълум", amount=100000)],
    )
    status = await db.get_monthly_budget_status(
        pool, user_id, "2026-07-01", include_items=True
    )
    item = status["items"][0]
    assert item["actual_amount_uzs"] == 0
    assert item["actual_quantity"] is None
    assert item["actual_unit"] is None
    assert item["last_unit_price_uzs"] is None
    assert item["average_unit_price_uzs"] is None
    assert item["reference_unit_price_uzs"] is None
    assert item["price_basis"] is None
    assert item["price_as_of"] is None


# ---------------------------------------------------------------------------
# MCP schema/dispatch and identity regressions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage53_extends_two_schemas_without_new_tools():
    tools = await server.list_tools()
    schemas = {tool.name: tool.inputSchema for tool in tools}
    assert len(tools) == len(server.DISPATCH) == len(server.TOOLS) == 21
    assert schemas["set_monthly_budget"]["required"] == [
        "user_id",
        "month",
        "category_code",
        "planned_amount_uzs",
    ]
    assert "items" in schemas["set_monthly_budget"]["properties"]
    item_schema = schemas["set_monthly_budget"]["properties"]["items"]["items"]
    assert set(item_schema["properties"]) >= {
        "item_name_normalized",
        "item_name_display",
        "planned_quantity",
        "unit",
        "planned_amount_uzs",
        "reference_unit_price_uzs",
        "price_basis",
        "price_as_of",
        "note",
    }
    assert schemas["get_monthly_budget_status"]["required"] == ["user_id", "month"]
    include = schemas["get_monthly_budget_status"]["properties"]["include_items"]
    assert include == {"type": "boolean", "default": False}
    assert "set_monthly_budget" in GUARD.read_text(encoding="utf-8")
    assert "get_monthly_budget_status" in GUARD.read_text(encoding="utf-8")


@requires_db
@pytest.mark.asyncio
async def test_mcp_old_and_new_calls_and_default_include_items(stage53_pool, monkeypatch):
    pool = stage53_pool
    user_id = await _seed_user(pool)

    async def _pool():
        return pool

    monkeypatch.setattr(server, "get_pool", _pool)
    old = await _call_json(
        "set_monthly_budget",
        {
            "user_id": user_id,
            "month": "2026-08-01",
            "category_code": "food",
            "planned_amount_uzs": 100000,
        },
    )
    assert old["ok"] is True
    default_status = await _call_json(
        "get_monthly_budget_status",
        {"user_id": user_id, "month": "2026-08-01"},
    )
    assert default_status["ok"] is True
    assert "items" not in default_status

    new = await _call_json(
        "set_monthly_budget",
        {
            "user_id": user_id,
            "month": "2026-08-01",
            "category_code": "food",
            "planned_amount_uzs": 100000,
            "items": [_item("нон", amount=100000)],
        },
    )
    assert new["ok"] is True
    detailed = await _call_json(
        "get_monthly_budget_status",
        {"user_id": user_id, "month": "2026-08-01", "include_items": True},
    )
    assert detailed["ok"] is True
    assert detailed["items"][0]["item_name_normalized"] == "нон"
