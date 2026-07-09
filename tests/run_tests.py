"""Permanent tests for Hermes/Mariyam backend tools (раздел 15).
Запуск: DATABASE_URL=postgresql://... backend/.venv/Scripts/python.exe tests/run_tests.py
Требует живой PostgreSQL с применённой миграцией backend/sql/001_init.sql.
Печатает маркеры ALL_TOOL_TESTS_PASSED, TZ_BOUNDARY_PASSED, MCP_SMOKE_PASSED, POOL_STABLE_PASSED.
"""
import asyncio
import json
import os
import re
import sys

# allow running from repo root or tests/ dir
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# Предохранитель: тесты делают TRUNCATE ... CASCADE.
db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    sys.exit("DATABASE_URL is not set for tests")
allowed = ("localhost" in db_url or "127.0.0.1" in db_url or "_test" in db_url)
if not allowed and os.environ.get("ALLOW_DESTRUCTIVE_TESTS") != "1":
    sys.exit(
        "REFUSED: tests TRUNCATE the database; DATABASE_URL does not look like a test DB. "
        "Set ALLOW_DESTRUCTIVE_TESTS=1 only if you are absolutely sure."
    )

from backend import db
from backend.config import get_pool
from backend.server import call_tool, list_tools


async def reset_db(pool):
    await pool.execute(
        "TRUNCATE transactions, quran_progress, health_notes, alert_events, "
        "plan_notes, usage_costs, users RESTART IDENTITY CASCADE"
    )


async def test_tools(pool):
    await reset_db(pool)
    oy, created = await db.ensure_user(pool, 111, "oyijon", "Ойижон")
    ad, created_ad = await db.ensure_user(pool, 222, "admin", "Бахриддин ака")
    assert oy == 1 and ad == 2 and created and created_ad, (oy, ad, created, created_ad)
    oy2, created2 = await db.ensure_user(pool, 111, "oyijon", "Другое имя")
    assert oy2 == oy and created2 is False

    try:
        await db.ensure_user(pool, 333, "bogus", "x")
        raise AssertionError("INVALID_INPUT role not raised")
    except ValueError as e:
        assert "INVALID_INPUT" in str(e)

    # BAD_CATEGORY
    try:
        await db.save_expense(pool, oy, [{"item_name": "x", "amount_uzs": 100, "category_code": "bogus"}], None, "text")
        raise AssertionError("BAD_CATEGORY not raised")
    except ValueError as e:
        assert "BAD_CATEGORY" in str(e)

    # BAD_AMOUNT
    try:
        await db.save_expense(pool, oy, [{"item_name": "x", "amount_uzs": -5, "category_code": "food.bread"}], None, "text")
        raise AssertionError("BAD_AMOUNT not raised")
    except ValueError as e:
        assert "BAD_AMOUNT" in str(e)

    r = await db.save_expense(pool, oy, [
        {"item_name": "нон", "amount_uzs": 12000, "category_code": "food.bread"},
        {"item_name": "гўшт", "amount_uzs": 180000, "category_code": "food.meat"},
    ], "2026-07-09T00:00:00Z", "voice")
    assert r["total_uzs"] == 192000, r
    assert len(r["saved_ids"]) == 2

    r = await db.update_expense(pool, oy, None, {"amount_uzs": 150000})
    assert r["new_amount_uzs"] == 150000, r

    try:
        await db.update_expense(pool, oy, r["updated_id"], {})
        raise AssertionError("empty fields not raised")
    except ValueError as e:
        assert "INVALID_INPUT" in str(e)

    assert await db.update_expense(pool, oy, 999999, {"amount_uzs": 1}) is None

    r = await db.delete_expense(pool, oy, None)
    assert r["deleted_id"] > 0

    ri = await db.save_income(pool, oy, 2300000, "UZS", "pension", "2026-07-09T00:00:00Z", "voice")
    assert ri["income_id"] > 0

    for coro in [
        db.save_income(pool, oy, 1, "EUR", None, None, "text"),
        db.save_health_note(pool, oy, "x", "huge", None),
        db.save_alert_event(pool, oy, "medical", "critical", "x", None, "magic", False),
    ]:
        try:
            await coro
            raise AssertionError("INVALID_INPUT not raised")
        except ValueError as e:
            assert "INVALID_INPUT" in str(e)

    rep = await db.expense_report(pool, oy, "month")
    assert rep["total_uzs"] == 12000, rep
    bal = await db.balance_summary(pool, oy, "month")
    assert bal["income_uzs"] == 2300000 and bal["expense_uzs"] == 12000, bal
    assert bal["remaining_uzs"] == 2288000

    rep_custom = await db.expense_report(pool, oy, "custom", "2026-07-09", None)
    assert rep_custom["total_uzs"] == 12000, rep_custom
    for args in [("custom", None, None), ("custom", "2026-07-10", "2026-07-09")]:
        try:
            await db.expense_report(pool, oy, *args)
            raise AssertionError("custom INVALID_INPUT not raised")
        except ValueError as e:
            assert "INVALID_INPUT" in str(e)

    await db.save_quran_progress(pool, oy, "Бақара", 2, 40, "")
    q = await db.get_quran_progress(pool, oy)
    assert q["surah"] == "Бақара" and q["juz"] == 2

    await db.save_health_note(pool, oy, "бош оғриди", "low", "...")
    await db.save_alert_event(pool, oy, "medical", "critical", "юрагим оғрияпти",
                              "мягкий ответ", "both", True)
    await db.save_plan_note(pool, oy, "plan", "эртага дўхтирга", None)
    ar = await db.admin_report_data(pool, oy, "2026-07-09")
    assert ar["expense_total_uzs"] == 12000, ar
    assert ar["income_total_uzs"] == 2300000
    assert ar["quran_updated"] is False
    assert len(ar["alerts"]) == 0
    ar_today = await db.admin_report_data(pool, oy, None)
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", ar_today["date"]), ar_today
    assert ar_today["quran_updated"] is True, ar_today
    assert len(ar_today["alerts"]) > 0, ar_today

    await db.log_usage_cost(pool, "elevenlabs", "stt", 12.5, 0.03)
    st = await db.get_bot_status(pool)
    assert st["db"] == "up" and st["gateway"] == "up"

    print("ALL_TOOL_TESTS_PASSED")


async def test_tz_boundary(pool):
    await reset_db(pool)
    oy, _ = await db.ensure_user(pool, 111, "oyijon", "Ойижон")

    await db.save_expense(pool, oy, [{"item_name": "x", "amount_uzs": 100, "category_code": "food.bread"}],
                          "2026-07-09T20:00:00Z", "text")
    await db.save_expense(pool, oy, [{"item_name": "y", "amount_uzs": 200, "category_code": "food.bread"}],
                          "2026-07-09T18:00:00Z", "text")

    rep_09 = await db.expense_report(pool, oy, "custom", "2026-07-09", "2026-07-09")
    rep_10 = await db.expense_report(pool, oy, "custom", "2026-07-10", "2026-07-10")
    assert rep_09["total_uzs"] == 200, rep_09
    assert rep_10["total_uzs"] == 100, rep_10
    ar_09 = await db.admin_report_data(pool, oy, "2026-07-09")
    assert ar_09["expense_total_uzs"] == 200, ar_09
    print("TZ_BOUNDARY_PASSED")


def content_json(contents):
    return json.loads(contents[0].text)


async def call_json(name, args):
    return content_json(await call_tool(name, args))


async def assert_error(name, args, code):
    r = await call_json(name, args)
    assert r["ok"] is False and r["error_code"] == code, (name, r)


async def test_mcp_smoke(pool):
    await reset_db(pool)
    tools = await list_tools()
    names = [t.name for t in tools]
    expected = [
        "ensure_user", "save_expense", "save_income", "update_expense", "update_last_expense",
        "delete_expense", "delete_last_expense", "get_expense_report", "get_balance_summary",
        "save_quran_progress", "get_quran_progress", "save_health_note", "save_alert_event",
        "save_plan_note", "get_admin_report_data", "backup_data", "get_backup_status",
        "get_bot_status", "log_usage_cost",
    ]
    assert names == expected, names
    required_sets = [tuple(t.inputSchema.get("required", [])) for t in tools]
    assert len(tools) == 19
    assert all("required" in t.inputSchema for t in tools)
    assert len(set(required_sets)) > 10, required_sets

    r = await call_json("ensure_user", {"telegram_id": 111, "role": "oyijon", "display_name": "Ойижон"})
    assert r["ok"] and r["created"] is True, r
    oy = r["user_id"]
    r2 = await call_json("ensure_user", {"telegram_id": 111, "role": "oyijon", "display_name": "Другое"})
    assert r2["ok"] and r2["user_id"] == oy and r2["created"] is False, r2
    await assert_error("ensure_user", {"telegram_id": 999, "role": "bogus", "display_name": "x"}, "INVALID_INPUT")

    r = await call_json("save_expense", {"user_id": oy, "items": [
        {"item_name": "нон", "amount_uzs": 12000, "category_code": "food.bread"},
        {"item_name": "гўшт", "amount_uzs": 180000, "category_code": "food.meat"},
    ], "occurred_at": "2026-07-09T00:00:00Z", "source_type": "voice"})
    assert r["ok"] and r["total_uzs"] == 192000, r
    first_id, second_id = r["saved_ids"]

    assert (await call_json("save_income", {"user_id": oy, "amount": 2300000, "currency": "UZS", "source_type": "voice"}))["ok"]
    assert (await call_json("update_expense", {"user_id": oy, "expense_id": first_id, "fields": {"amount_uzs": 13000}}))["ok"]
    assert (await call_json("update_last_expense", {"user_id": oy, "fields": {"amount_uzs": 150000}}))["ok"]
    assert (await call_json("delete_expense", {"user_id": oy, "expense_id": first_id}))["ok"]
    assert (await call_json("save_expense", {"user_id": oy, "items": [{"item_name": "чой", "amount_uzs": 5000, "category_code": "food"}]}))["ok"]
    assert (await call_json("delete_last_expense", {"user_id": oy}))["ok"]
    assert (await call_json("get_expense_report", {"user_id": oy, "period": "custom", "from": "2026-07-09"}))["ok"]
    assert (await call_json("get_balance_summary", {"user_id": oy}))["ok"]
    assert (await call_json("save_quran_progress", {"user_id": oy, "surah": "Бақара", "juz": 2, "page": 40}))["ok"]
    assert (await call_json("get_quran_progress", {"user_id": oy}))["ok"]
    assert (await call_json("save_health_note", {"user_id": oy, "note": "яхши", "severity": "info"}))["ok"]
    assert (await call_json("save_alert_event", {"user_id": oy, "alert_type": "medical", "severity": "critical", "source_text": "юрагим оғри", "detected_by": "keyword"}))["ok"]
    assert (await call_json("save_plan_note", {"user_id": oy, "text": "эртага бозор"}))["ok"]
    ar = await call_json("get_admin_report_data", {"user_id": oy})
    assert ar["ok"] and re.match(r"^\d{4}-\d{2}-\d{2}$", ar["date"]), ar
    assert (await call_json("get_bot_status", {}))["ok"]
    assert (await call_json("log_usage_cost", {"provider": "openai", "service_type": "llm", "units": 1, "estimated_cost_usd": 0.01}))["ok"]

    for tool_name in ["backup_data", "get_backup_status"]:
        r = await call_json(tool_name, {})
        assert r["ok"] is False and r["error_code"] == "NOT_CONFIGURED", r

    await assert_error("save_expense", {"user_id": oy}, "INVALID_INPUT")
    await assert_error("save_expense", {"user_id": oy, "items": [{"amount_uzs": 1, "category_code": "bogus"}]}, "BAD_CATEGORY")
    await assert_error("save_expense", {"user_id": oy, "items": [{"amount_uzs": -1, "category_code": "food.bread"}]}, "BAD_AMOUNT")
    await assert_error("update_expense", {"user_id": oy, "expense_id": 999999, "fields": {"amount_uzs": 1}}, "NOT_FOUND")
    await assert_error("update_expense", {"user_id": oy, "expense_id": second_id, "fields": {}}, "INVALID_INPUT")
    await assert_error("save_income", {"user_id": oy, "amount": 1, "currency": "EUR"}, "INVALID_INPUT")
    await assert_error("save_health_note", {"user_id": oy, "note": "x", "severity": "huge"}, "INVALID_INPUT")
    await assert_error("save_alert_event", {"user_id": oy, "alert_type": "medical", "severity": "critical", "source_text": "x", "detected_by": "magic"}, "INVALID_INPUT")
    await assert_error("get_expense_report", {"user_id": oy, "period": "custom"}, "INVALID_INPUT")
    await assert_error("unknown_tool", {}, "UNKNOWN_TOOL")

    for _ in range(50):
        r = await call_json("get_bot_status", {})
        assert r["ok"], r
    conn_count = await pool.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    assert conn_count <= 6, conn_count
    print("POOL_STABLE_PASSED")
    print("MCP_SMOKE_PASSED")


async def main():
    pool = await get_pool()
    try:
        await test_tools(pool)
        await test_tz_boundary(pool)
        await test_mcp_smoke(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
