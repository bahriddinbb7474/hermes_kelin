"""Hermes/Mariyam backend — DB access layer (storage only, no intent logic).
Источник истины: TZ_Hermes_Mariyam_FINAL_v3_0.md, разделы 13, 15.
Backend validates and stores already-parsed data; returns exact facts/numbers.
"""
from datetime import datetime, timezone
import asyncpg

from .config import TASHKENT, parse_dt


async def ensure_user(pool, telegram_id: int, role: str, display_name: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", telegram_id
    )
    if row:
        return row["id"]
    return await pool.fetchval(
        """INSERT INTO users (telegram_id, role, display_name)
           VALUES ($1, $2, $3) RETURNING id""",
        telegram_id, role, display_name,
    )


async def valid_category(pool, code: str) -> bool:
    row = await pool.fetchrow(
        "SELECT 1 FROM expense_categories WHERE code = $1 AND active", code
    )
    return row is not None


async def save_expense(pool, user_id, items, occurred_at, source_type, source_text=None):
    """items: list of {item_name, amount_uzs, category_code}. Returns saved ids + total."""
    occurred = parse_dt(occurred_at) or datetime.now(timezone.utc)
    total = 0
    saved_ids = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for it in items:
                cat = it.get("category_code")
                if cat and not await valid_category(pool, cat):
                    raise ValueError("BAD_CATEGORY:" + str(cat))
                amount = int(round(float(it["amount_uzs"])))
                if amount < 0:
                    raise ValueError("BAD_AMOUNT")
                tid = await conn.fetchval(
                    """INSERT INTO transactions
                       (user_id, type, amount, currency, category_code, item_name,
                        source_text, source_type, occurred_at)
                       VALUES ($1,'expense',$2,'UZS',$3,$4,$5,$6,$7) RETURNING id""",
                    user_id, amount, cat, it.get("item_name"),
                    source_text, source_type, occurred,
                )
                saved_ids.append(tid)
                total += amount
    return {"saved_ids": saved_ids, "total_uzs": total}


async def save_income(pool, user_id, amount, currency, source_name, occurred_at, source_type):
    occurred = parse_dt(occurred_at) or datetime.now(timezone.utc)
    amount = int(round(float(amount)))
    if amount < 0:
        raise ValueError("BAD_AMOUNT")
    tid = await pool.fetchval(
        """INSERT INTO transactions
           (user_id, type, amount, currency, item_name, source_type, occurred_at)
           VALUES ($1,'income',$2,$3,$4,$5,$6) RETURNING id""",
        user_id, amount, currency, source_name, source_type, occurred,
    )
    return {"income_id": tid}


async def last_expense_id(pool, user_id):
    return await pool.fetchval(
        "SELECT id FROM transactions WHERE user_id=$1 AND type='expense' "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        user_id,
    )


async def update_expense(pool, user_id, expense_id, fields):
    if expense_id is None:
        expense_id = await last_expense_id(pool, user_id)
        if expense_id is None:
            return None
    cat = fields.get("category_code")
    if cat and not await valid_category(pool, cat):
        raise ValueError("BAD_CATEGORY:" + str(cat))
    sets, params = [], [user_id, expense_id]
    idx = 3
    if "amount_uzs" in fields:
        amt = int(round(float(fields["amount_uzs"])))
        if amt < 0:
            raise ValueError("BAD_AMOUNT")
        sets.append(f"amount=${idx}"); params.append(amt); idx += 1
    if cat is not None:
        sets.append(f"category_code=${idx}"); params.append(cat); idx += 1
    if "item_name" in fields:
        sets.append(f"item_name=${idx}"); params.append(fields["item_name"]); idx += 1
    if not sets:
        return None
    row = await pool.fetchrow(
        f"UPDATE transactions SET {','.join(sets)} "
        "WHERE user_id=$1 AND id=$2 AND type='expense' RETURNING id, amount",
        *params,
    )
    if not row:
        return None
    return {"updated_id": row["id"], "new_amount_uzs": int(row["amount"])}


async def delete_expense(pool, user_id, expense_id):
    if expense_id is None:
        expense_id = await last_expense_id(pool, user_id)
        if expense_id is None:
            return None
    did = await pool.fetchval(
        "DELETE FROM transactions WHERE user_id=$1 AND id=$2 AND type='expense' "
        "RETURNING id", user_id, expense_id,
    )
    return {"deleted_id": did} if did else None


def _day_bounds(date_str: str | None):
    """Day boundaries in Asia/Tashkent, returned as UTC datetimes."""
    from datetime import datetime, timedelta
    if date_str:
        base = datetime.fromisoformat(date_str).date()
    else:
        base = datetime.now(TASHKENT).date()
    start = datetime(base.year, base.month, base.day, tzinfo=TASHKENT)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _period_bounds(period: str, from_dt=None, to_dt=None):
    from datetime import datetime, timedelta
    now_t = datetime.now(TASHKENT)
    if period == "today":
        return _day_bounds(None)
    if period == "week":
        start = (now_t - timedelta(days=now_t.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc), (start + timedelta(days=7)).astimezone(timezone.utc)
    if period == "month":
        start = now_t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            nxt = start.replace(year=start.year + 1, month=1)
        else:
            nxt = start.replace(month=start.month + 1)
        return start.astimezone(timezone.utc), nxt.astimezone(timezone.utc)
    # custom: date-only string -> Tashkent day bounds; ISO datetime -> as-is
    if from_dt and len(from_dt) <= 10:
        s, e = _day_bounds(from_dt)
    else:
        s = parse_dt(from_dt)
    if to_dt and len(to_dt) <= 10:
        _, e = _day_bounds(to_dt)
    else:
        e = parse_dt(to_dt)
    return s, e


async def expense_report(pool, user_id, period, from_dt=None, to_dt=None, category_code=None):
    start, end = _period_bounds(period, from_dt, to_dt)
    args = [user_id, start, end]
    cat_filter = ""
    if category_code:
        cat_filter = " AND category_code = $4"
        args.append(category_code)
    rows = await pool.fetch(
        f"""SELECT t.category_code AS category_code,
                   COALESCE(ec.name_uz, cat_root.name_uz) AS name_uz,
                   SUM(t.amount) AS sum_uzs
            FROM transactions t
            LEFT JOIN expense_categories ec ON ec.code = t.category_code
            LEFT JOIN expense_categories cat_root ON cat_root.code = split_part(t.category_code, '.', 1)
            WHERE t.user_id=$1 AND t.type='expense' AND t.occurred_at >= $2 AND t.occurred_at < $3
                  {cat_filter}
            GROUP BY t.category_code, ec.name_uz, cat_root.name_uz
            ORDER BY sum_uzs DESC""",
        *args,
    )
    total = sum(int(r["sum_uzs"]) for r in rows)
    by_cat = [
        {"category_code": r["category_code"], "name_uz": r["name_uz"],
         "sum_uzs": int(r["sum_uzs"])} for r in rows
    ]
    top = by_cat[0]["category_code"] if by_cat else None
    return {"period": period, "currency": "UZS",
            "total_uzs": total, "by_category": by_cat, "top_category": top}


async def balance_summary(pool, user_id, period):
    start, end = _period_bounds(period)
    inc = await pool.fetchval(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE user_id=$1 AND type='income' AND occurred_at >= $2 AND occurred_at < $3",
        user_id, start, end,
    )
    exp = await pool.fetchval(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE user_id=$1 AND type='expense' AND occurred_at >= $2 AND occurred_at < $3",
        user_id, start, end,
    )
    inc, exp = int(inc), int(exp)
    return {"currency": "UZS", "income_uzs": inc, "expense_uzs": exp,
            "remaining_uzs": inc - exp}


async def save_quran_progress(pool, user_id, surah, juz, page, note):
    return await pool.fetchval(
        """INSERT INTO quran_progress (user_id, surah, juz, page, note)
           VALUES ($1,$2,$3,$4,$5) RETURNING id""",
        user_id, surah, juz, page, note,
    )


async def get_quran_progress(pool, user_id):
    return await pool.fetchrow(
        "SELECT surah, juz, page, note, updated_at FROM quran_progress "
        "WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1", user_id,
    )


async def save_health_note(pool, user_id, note, severity, source_text):
    return await pool.fetchval(
        """INSERT INTO health_notes (user_id, note, severity, source_text)
           VALUES ($1,$2,$3,$4) RETURNING id""",
        user_id, note, severity, source_text,
    )


async def save_alert_event(pool, user_id, alert_type, severity, source_text,
                           bot_response, detected_by, sent_to_admin):
    return await pool.fetchval(
        """INSERT INTO alert_events
           (user_id, alert_type, severity, source_text, bot_response, detected_by, sent_to_admin)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
        user_id, alert_type, severity, source_text, bot_response, detected_by, sent_to_admin,
    )


async def save_plan_note(pool, user_id, kind, text, value_int):
    return await pool.fetchval(
        """INSERT INTO plan_notes (user_id, kind, text, value_int)
           VALUES ($1,$2,$3,$4) RETURNING id""",
        user_id, kind, text, value_int,
    )


async def admin_report_data(pool, user_id, date_str):
    start, end = _day_bounds(date_str)
    exp_total = await pool.fetchval(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE user_id=$1 AND type='expense' AND occurred_at >= $2 AND occurred_at < $3",
        user_id, start, end,
    )
    by_cat = await pool.fetch(
        """SELECT t.category_code AS category_code,
                  COALESCE(ec.name_uz, cat_root.name_uz) AS name_uz,
                  SUM(t.amount) AS sum_uzs
           FROM transactions t
           LEFT JOIN expense_categories ec ON ec.code = t.category_code
           LEFT JOIN expense_categories cat_root ON cat_root.code = split_part(t.category_code, '.', 1)
           WHERE t.user_id=$1 AND t.type='expense' AND t.occurred_at >= $2 AND t.occurred_at < $3
           GROUP BY t.category_code, ec.name_uz, cat_root.name_uz ORDER BY sum_uzs DESC""",
        user_id, start, end,
    )
    health = await pool.fetch(
        "SELECT note, severity FROM health_notes WHERE user_id=$1 "
        "AND created_at >= $2 AND created_at < $3 ORDER BY created_at DESC",
        user_id, start, end,
    )
    alerts = await pool.fetch(
        "SELECT alert_type, severity FROM alert_events WHERE user_id=$1 "
        "AND created_at >= $2 AND created_at < $3 ORDER BY created_at DESC",
        user_id, start, end,
    )
    quran = await pool.fetchval(
        "SELECT 1 FROM quran_progress WHERE user_id=$1 AND updated_at >= $2 AND updated_at < $3",
        user_id, start, end,
    )
    inc_total = await pool.fetchval(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE user_id=$1 AND type='income' AND occurred_at >= $2 AND occurred_at < $3",
        user_id, start, end,
    )
    return {
        "date": date_str,
        "expense_total_uzs": int(exp_total),
        "expense_by_category": [
            {"category_code": r["category_code"], "name_uz": r["name_uz"],
             "sum_uzs": int(r["sum_uzs"])} for r in by_cat
        ],
        "health_notes": [{"note": r["note"], "severity": r["severity"]} for r in health],
        "alerts": [{"alert_type": r["alert_type"], "severity": r["severity"]} for r in alerts],
        "quran_updated": bool(quran),
        "income_total_uzs": int(inc_total),
    }


async def log_usage_cost(pool, provider, service_type, units, estimated_cost_usd):
    await pool.execute(
        """INSERT INTO usage_costs (provider, service_type, units, estimated_cost_usd)
           VALUES ($1,$2,$3,$4)""",
        provider, service_type, float(units), float(estimated_cost_usd),
    )


async def get_bot_status(pool):
    try:
        await pool.fetchval("SELECT 1")
        db = "up"
    except Exception:
        db = "down"
    return {"gateway": "up", "db": db, "last_error": None,
            "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
