"""Permanent tests for Hermes/Mariyam backend tools (раздел 15).
Запуск: backend/.venv/Scripts/python.exe tests/run_tests.py
Требует живой PostgreSQL (docker compose) с применённой миграцией backend/sql/001_init.sql.
Выводит маркеры ALL_TOOL_TESTS_PASSED и TZ_BOUNDARY_PASSED для автоматической проверки.
"""
import asyncio
import os
import sys

# allow running from repo root or tests/ dir
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# DATABASE_URL можно переопределить; по умолчанию локальный postgres
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql://hermes:hermes@localhost:5432/hermes"),
)

from backend import db
from backend.config import get_pool


async def test_tools(pool):
    # reset state for deterministic run
    await pool.execute(
        "TRUNCATE transactions, quran_progress, health_notes, "
        "alert_events, plan_notes, usage_costs RESTART IDENTITY CASCADE"
    )
    oy = await db.ensure_user(pool, 111, "oyijon", "Ойижон")
    ad = await db.ensure_user(pool, 222, "admin", "Бахриддин ака")
    assert oy == 1 and ad == 2, (oy, ad)

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

    # save_expense (AC example): нон 12 минг, гўшт 180 минг
    r = await db.save_expense(pool, oy, [
        {"item_name": "нон", "amount_uzs": 12000, "category_code": "food.bread"},
        {"item_name": "гўшт", "amount_uzs": 180000, "category_code": "food.meat"},
    ], "2026-07-09T00:00:00Z", "voice")
    assert r["total_uzs"] == 192000, r
    assert len(r["saved_ids"]) == 2

    # update_last_expense: "гўштни 150 минг қил"
    r = await db.update_expense(pool, oy, None, {"amount_uzs": 150000})
    assert r["new_amount_uzs"] == 150000, r

    # delete_last_expense (removes the гўшт 150k)
    r = await db.delete_expense(pool, oy, None)
    assert r["deleted_id"] > 0

    # save_income
    ri = await db.save_income(pool, oy, 2300000, "UZS", "pension", "2026-07-09T00:00:00Z", "voice")
    assert ri["income_id"] > 0

    # reports
    rep = await db.expense_report(pool, oy, "month")
    assert rep["total_uzs"] == 12000, rep  # only нон remains
    bal = await db.balance_summary(pool, oy, "month")
    assert bal["income_uzs"] == 2300000 and bal["expense_uzs"] == 12000, bal
    assert bal["remaining_uzs"] == 2288000

    # quran
    await db.save_quran_progress(pool, oy, "Бақара", 2, 40, "")
    q = await db.get_quran_progress(pool, oy)
    assert q["surah"] == "Бақара" and q["juz"] == 2

    # health + alert
    await db.save_health_note(pool, oy, "бош оғриди", "low", "...")
    await db.save_alert_event(pool, oy, "medical", "critical", "юрагим оғрияпти",
                              "мягкий ответ", "both", True)
    # plan note
    await db.save_plan_note(pool, oy, "plan", "эртага дўхтирга", None)
    # admin report for 2026-07-09
    ar = await db.admin_report_data(pool, oy, "2026-07-09")
    assert ar["expense_total_uzs"] == 12000, ar
    assert ar["income_total_uzs"] == 2300000
    assert ar["quran_updated"] is True
    assert len(ar["alerts"]) == 1

    # usage cost
    await db.log_usage_cost(pool, "elevenlabs", "stt", 12.5, 0.03)
    # bot status
    st = await db.get_bot_status(pool)
    assert st["db"] == "up" and st["gateway"] == "up"

    print("ALL_TOOL_TESTS_PASSED")


async def test_tz_boundary(pool):
    await pool.execute("TRUNCATE transactions RESTART IDENTITY CASCADE")
    oy = await db.ensure_user(pool, 111, "oyijon", "Ойижон")

    # 2026-07-09T20:00:00Z == 2026-07-10 01:00 Tashkent -> Tashkent day 2026-07-10
    # 2026-07-09T18:00:00Z == 2026-07-09 23:00 Tashkent -> Tashkent day 2026-07-09
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


async def main():
    pool = await get_pool()
    try:
        await test_tools(pool)
        await test_tz_boundary(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
