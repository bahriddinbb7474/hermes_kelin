"""Hermes/Mariyam backend — DB access layer (storage only, no intent logic).
Источник истины: TZ_Hermes_Mariyam_FINAL_v3_0.md, разделы 13, 15.
Backend validates and stores already-parsed data; returns exact facts/numbers.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite

from .config import TASHKENT, parse_dt

CURRENCIES = ("UZS", "USD")
HEALTH_SEVERITIES = ("info", "low", "medium", "high", "critical")
ALERT_SEVERITIES = ("low", "medium", "high", "critical")
SOURCE_TYPES = ("text", "voice", "admin")
DETECTED_BY = ("llm", "keyword", "both")
SERVICE_TYPES = ("stt", "tts", "llm")
ROLES = ("oyijon", "admin")
# Stage 5.1 — physical quantity units (ТЗ v3.7)
CANONICAL_UNITS = ("kg", "g", "l", "ml", "pcs", "pack")
PRICE_BASES = ("last", "average", "manual")


def _one_of(field: str, value, allowed: tuple[str, ...], *, allow_none: bool = False):
    if value is None and allow_none:
        return
    if value not in allowed:
        raise ValueError(f"INVALID_INPUT: {field} must be one of {', '.join(allowed)}")


def _normalize_qty_unit(item: dict) -> tuple[float | None, str | None]:
    """Validate optional quantity/unit on a save_expense item. Returns (qty, unit)."""
    has_qty = "quantity" in item and item.get("quantity") is not None
    has_unit = "unit" in item and item.get("unit") is not None

    if not has_qty and not has_unit:
        return None, None

    if has_unit and not has_qty:
        raise ValueError("INVALID_INPUT: unit requires quantity")

    qty_raw = item.get("quantity")
    if isinstance(qty_raw, bool) or not isinstance(qty_raw, (int, float, Decimal)):
        raise ValueError("INVALID_INPUT: quantity must be a number")
    qty = float(qty_raw)
    if not isfinite(qty) or qty <= 0:
        raise ValueError("INVALID_INPUT: quantity must be finite and > 0")

    unit = None
    if has_unit:
        unit = item.get("unit")
        if not isinstance(unit, str):
            raise ValueError("INVALID_INPUT: unit must be a string")
        unit = unit.strip().lower()
        _one_of("unit", unit, CANONICAL_UNITS)
    return qty, unit


async def ensure_user(pool, telegram_id: int, role: str, display_name: str) -> tuple[int, bool]:
    _one_of("role", role, ROLES)
    row = await pool.fetchrow(
        """WITH ins AS (
               INSERT INTO users (telegram_id, role, display_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (telegram_id) DO NOTHING
               RETURNING id
           )
           SELECT id, true AS created FROM ins
           UNION ALL
           SELECT id, false AS created FROM users
           WHERE telegram_id = $1 AND NOT EXISTS (SELECT 1 FROM ins)
           LIMIT 1""",
        int(telegram_id), role, display_name,
    )
    if not row:
        raise RuntimeError("failed to ensure user")
    return row["id"], row["created"]


async def valid_category(pool, code: str) -> bool:
    row = await pool.fetchrow(
        "SELECT 1 FROM expense_categories WHERE code = $1 AND active", code
    )
    return row is not None


async def save_expense(pool, user_id, items, occurred_at, source_type, source_text=None):
    _one_of("source_type", source_type, SOURCE_TYPES)
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
                qty, unit = _normalize_qty_unit(it)
                item_norm = it.get("item_name_normalized")
                if item_norm is not None and not isinstance(item_norm, str):
                    raise ValueError("INVALID_INPUT: item_name_normalized must be a string")
                if isinstance(item_norm, str):
                    item_norm = item_norm.strip().casefold() or None
                tid = await conn.fetchval(
                    """INSERT INTO transactions
                       (user_id, type, amount, currency, category_code, item_name,
                        item_name_normalized, quantity, unit,
                        source_text, source_type, occurred_at)
                       VALUES ($1,'expense',$2,'UZS',$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id""",
                    user_id, amount, cat, it.get("item_name"),
                    item_norm, qty, unit,
                    source_text, source_type, occurred,
                )
                saved_ids.append(tid)
                total += amount
    return {"saved_ids": saved_ids, "total_uzs": total}


async def save_income(pool, user_id, amount, currency, source_name, occurred_at, source_type):
    _one_of("currency", currency, CURRENCIES)
    _one_of("source_type", source_type, SOURCE_TYPES)
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
        sets.append(f"amount=${idx}")
        params.append(amt)
        idx += 1
    if cat is not None:
        sets.append(f"category_code=${idx}")
        params.append(cat)
        idx += 1
    if "item_name" in fields:
        sets.append(f"item_name=${idx}")
        params.append(fields["item_name"])
        idx += 1
    if not sets:
        raise ValueError("INVALID_INPUT: fields is empty, nothing to update")
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
    if date_str:
        base = datetime.fromisoformat(date_str).date()
    else:
        base = datetime.now(TASHKENT).date()
    start = datetime(base.year, base.month, base.day, tzinfo=TASHKENT)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _period_bounds(period: str, from_dt=None, to_dt=None):
    now_t = datetime.now(TASHKENT)
    if period == "today":
        return _day_bounds(None)
    if period == "week":
        start = (now_t - timedelta(days=now_t.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc), (start + timedelta(days=7)).astimezone(timezone.utc)
    if period == "month":
        start = now_t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        nxt = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start.astimezone(timezone.utc), nxt.astimezone(timezone.utc)
    if period != "custom":
        raise ValueError("INVALID_INPUT: period must be one of today, week, month, custom")
    if not from_dt and not to_dt:
        raise ValueError("INVALID_INPUT: custom period requires from/to")
    if from_dt and len(from_dt) <= 10:
        s, e = _day_bounds(from_dt)
        if to_dt:
            _, e = _day_bounds(to_dt) if len(to_dt) <= 10 else (None, parse_dt(to_dt))
    else:
        s = parse_dt(from_dt)
        if from_dt and not to_dt:
            raise ValueError("INVALID_INPUT: custom datetime 'from' requires 'to'")
        e = parse_dt(to_dt) if to_dt else None
    if to_dt and not from_dt:
        e = _day_bounds(to_dt)[1] if len(to_dt) <= 10 else parse_dt(to_dt)
        s = datetime.min.replace(tzinfo=timezone.utc)
    if s is None or e is None:
        raise ValueError("INVALID_INPUT: custom period requires from/to")
    if s >= e:
        raise ValueError("INVALID_INPUT: from must be before to")
    return s, e


def _shift_month(dt_tashkent: datetime, delta: int) -> datetime:
    """Shift calendar month in Asia/Tashkent (day=1, midnight)."""
    y, m = dt_tashkent.year, dt_tashkent.month + delta
    while m > 12:
        y += 1
        m -= 12
    while m < 1:
        y -= 1
        m += 12
    return dt_tashkent.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)


def _previous_period_bounds(
    start: datetime, end: datetime, *, calendar_month: bool = False
) -> tuple[datetime, datetime]:
    """Previous period; calendar month uses exact Tashkent month boundaries."""
    if calendar_month:
        start_t = start.astimezone(TASHKENT)
        prev_start_t = _shift_month(start_t, -1)
        return prev_start_t.astimezone(timezone.utc), start_t.astimezone(timezone.utc)
    duration = end - start
    return start - duration, start


def _build_by_item(rows) -> list[dict]:
    """Group expense fact-rows into by_item analytics (only non-empty item_name_normalized)."""
    groups: dict[tuple[str, str | None], list] = {}
    for r in rows:
        name = r["item_name_normalized"]
        if not name:
            continue
        key = (name, r["category_code"])
        groups.setdefault(key, []).append(r)

    by_item = []
    for (name, cat), items in groups.items():
        total = sum(int(x["amount"]) for x in items)
        purchase_count = len(items)
        qty_by_unit: dict[str, float] = {}
        all_have_qty_unit = True
        units_seen: set[str] = set()
        for x in items:
            q, u = x["quantity"], x["unit"]
            if q is None or u is None:
                all_have_qty_unit = False
                continue
            u = str(u)
            units_seen.add(u)
            qty_by_unit[u] = qty_by_unit.get(u, 0.0) + float(q)

        avg = None
        if all_have_qty_unit and len(units_seen) == 1 and qty_by_unit:
            only_unit = next(iter(units_seen))
            qsum = qty_by_unit[only_unit]
            if qsum > 0:
                avg = round(total / qsum, 4)

        by_item.append({
            "item_name_normalized": name,
            "category_code": cat,
            "total_uzs": total,
            "purchase_count": purchase_count,
            "quantity_by_unit": {
                u: (int(v) if float(v).is_integer() else round(v, 3))
                for u, v in sorted(qty_by_unit.items())
            },
            "average_unit_price_uzs": avg,
        })
    by_item.sort(key=lambda x: (-x["total_uzs"], x["item_name_normalized"]))
    return by_item


async def expense_report(
    pool,
    user_id,
    period,
    from_dt=None,
    to_dt=None,
    category_code=None,
    compare_previous: bool = False,
    trend_months: int = 3,
):
    if not isinstance(compare_previous, bool):
        raise ValueError("INVALID_INPUT: compare_previous must be boolean")
    if isinstance(trend_months, bool) or not isinstance(trend_months, int):
        raise ValueError("INVALID_INPUT: trend_months must be integer 1..12")
    if trend_months < 1 or trend_months > 12:
        raise ValueError("INVALID_INPUT: trend_months must be integer 1..12")

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

    # Detail rows for by_item (legacy NULL normalized names excluded from groups)
    detail = await pool.fetch(
        f"""SELECT amount, category_code, item_name_normalized, quantity, unit
            FROM transactions
            WHERE user_id=$1 AND type='expense'
              AND occurred_at >= $2 AND occurred_at < $3
              {cat_filter}""",
        *args,
    )
    by_item = _build_by_item(detail)

    result = {
        "period": period,
        "currency": "UZS",
        "total_uzs": total,
        "by_category": by_cat,
        "top_category": top,
        "by_item": by_item,
    }

    if compare_previous:
        p_start, p_end = _previous_period_bounds(
            start, end, calendar_month=(period == "month")
        )
        p_args = [user_id, p_start, p_end]
        p_cat = ""
        if category_code:
            p_cat = " AND category_code = $4"
            p_args.append(category_code)
        prev_total = await pool.fetchval(
            f"""SELECT COALESCE(SUM(amount),0) FROM transactions
                WHERE user_id=$1 AND type='expense'
                  AND occurred_at >= $2 AND occurred_at < $3{p_cat}""",
            *p_args,
        )
        prev_total = int(prev_total)
        change_uzs = total - prev_total
        change_percent = None if prev_total == 0 else round(100.0 * change_uzs / prev_total, 4)
        result["previous_period"] = {
            "total_uzs": prev_total,
            "change_uzs": change_uzs,
            "change_percent": change_percent,
        }

    # monthly_series: last trend_months calendar months ending at period end (Tashkent)
    end_t = end.astimezone(TASHKENT)
    # last complete boundary is end; series months are those with month_start < end
    # use the month that contains (end - 1 microsecond) as the newest month
    newest = (end_t - timedelta(microseconds=1)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    series = []
    for i in range(trend_months - 1, -1, -1):
        m_start = _shift_month(newest, -i)
        m_end = _shift_month(m_start, 1)
        s_utc = m_start.astimezone(timezone.utc)
        e_utc = m_end.astimezone(timezone.utc)
        s_args = [user_id, s_utc, e_utc]
        s_cat = ""
        if category_code:
            s_cat = " AND category_code = $4"
            s_args.append(category_code)
        m_total = await pool.fetchval(
            f"""SELECT COALESCE(SUM(amount),0) FROM transactions
                WHERE user_id=$1 AND type='expense'
                  AND occurred_at >= $2 AND occurred_at < $3{s_cat}""",
            *s_args,
        )
        series.append({
            "month": m_start.date().isoformat(),
            "total_uzs": int(m_total),
        })
    result["monthly_series"] = series
    return result


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


def _budget_month(month: str) -> date:
    """Parse the canonical YYYY-MM-01 budget key."""
    if not isinstance(month, str):
        raise ValueError("INVALID_INPUT: month must be YYYY-MM-01")
    try:
        parsed = date.fromisoformat(month)
    except ValueError as exc:
        raise ValueError("INVALID_INPUT: month must be YYYY-MM-01") from exc
    if parsed.day != 1 or parsed.isoformat() != month:
        raise ValueError("INVALID_INPUT: month must be YYYY-MM-01")
    return parsed


def _budget_amount(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("BAD_AMOUNT")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("BAD_AMOUNT")
    return amount


def _json_number(value: Decimal | int):
    value = Decimal(value)
    return int(value) if value == value.to_integral_value() else float(value)


def _optional_decimal(value, field: str, *, positive: bool) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"INVALID_INPUT: {field} must be a number")
    result = Decimal(str(value))
    if not result.is_finite() or (result <= 0 if positive else result < 0):
        relation = "> 0" if positive else ">= 0"
        raise ValueError(f"INVALID_INPUT: {field} must be finite and {relation}")
    return result


def _normalize_plan_items(items) -> list[dict]:
    """Validate product-plan input without inventing quantities or prices."""
    if not isinstance(items, list):
        raise ValueError("INVALID_INPUT: items must be an array")

    normalized = []
    seen = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("INVALID_INPUT: every plan item must be an object")

        item_name = raw.get("item_name_normalized")
        display_name = raw.get("item_name_display")
        if not isinstance(item_name, str) or not item_name.strip():
            raise ValueError("INVALID_INPUT: item_name_normalized is required")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("INVALID_INPUT: item_name_display is required")
        item_name = item_name.strip().casefold()
        display_name = display_name.strip()
        if item_name in seen:
            raise ValueError("INVALID_INPUT: duplicate item_name_normalized")
        seen.add(item_name)

        quantity = _optional_decimal(
            raw.get("planned_quantity"), "planned_quantity", positive=True
        )
        amount = _optional_decimal(
            raw.get("planned_amount_uzs"), "planned_amount_uzs", positive=False
        )
        if quantity is None and amount is None:
            raise ValueError(
                "INVALID_INPUT: planned_quantity or planned_amount_uzs is required"
            )

        unit = raw.get("unit")
        if unit is not None:
            if not isinstance(unit, str):
                raise ValueError("INVALID_INPUT: unit must be a string")
            unit = unit.strip().lower()
            _one_of("unit", unit, CANONICAL_UNITS)
            if quantity is None:
                raise ValueError("INVALID_INPUT: unit requires planned_quantity")

        reference_price = _optional_decimal(
            raw.get("reference_unit_price_uzs"),
            "reference_unit_price_uzs",
            positive=False,
        )
        price_basis = raw.get("price_basis")
        if price_basis is not None:
            if not isinstance(price_basis, str):
                raise ValueError("INVALID_INPUT: price_basis must be a string")
            price_basis = price_basis.strip().lower()
            _one_of("price_basis", price_basis, PRICE_BASES)
        if (reference_price is not None or price_basis is not None) and unit is None:
            raise ValueError("INVALID_INPUT: reference price requires quantity and unit")
        if price_basis == "manual" and reference_price is None:
            raise ValueError("INVALID_INPUT: manual price requires reference_unit_price_uzs")

        price_as_of = raw.get("price_as_of")
        if price_as_of is not None:
            if not isinstance(price_as_of, str):
                raise ValueError("INVALID_INPUT: price_as_of must be UTC ISO 8601")
            try:
                price_as_of = parse_dt(price_as_of)
            except (TypeError, ValueError) as exc:
                raise ValueError("INVALID_INPUT: price_as_of must be UTC ISO 8601") from exc
        if reference_price is not None and price_basis is None:
            raise ValueError("INVALID_INPUT: price_basis is required with reference price")
        if price_as_of is not None and reference_price is None:
            raise ValueError("INVALID_INPUT: price_as_of requires reference_unit_price_uzs")

        normalized.append(
            {
                "item_name_normalized": item_name,
                "item_name_display": display_name,
                "planned_quantity": quantity,
                "unit": unit,
                "planned_amount_uzs": amount,
                "reference_unit_price_uzs": reference_price,
                "price_basis": price_basis,
                "price_as_of": price_as_of,
                "note": raw.get("note"),
            }
        )
    return normalized


def _normalize_price_lookup_items(items) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("INVALID_INPUT: price_lookup_items must be an array")
    if len(items) > 50:
        raise ValueError("INVALID_INPUT: price_lookup_items supports at most 50 items")

    normalized = []
    seen = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("INVALID_INPUT: price lookup item must be an object")
        if set(raw) - {"item_name_normalized", "unit", "price_basis"}:
            raise ValueError("INVALID_INPUT: unexpected price lookup item field")
        item_name = raw.get("item_name_normalized")
        unit = raw.get("unit")
        price_basis = raw.get("price_basis")
        if not isinstance(item_name, str) or not item_name.strip():
            raise ValueError("INVALID_INPUT: item_name_normalized is required")
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError("INVALID_INPUT: unit is required")
        if price_basis not in {"last", "average"}:
            raise ValueError("INVALID_INPUT: price_basis must be last or average")
        item_name = item_name.strip().casefold()
        unit = unit.strip().lower()
        _one_of("unit", unit, CANONICAL_UNITS)
        key = (item_name, unit)
        if key in seen:
            raise ValueError("INVALID_INPUT: duplicate price lookup item")
        seen.add(key)
        normalized.append(
            {
                "item_name_normalized": item_name,
                "unit": unit,
                "price_basis": price_basis,
            }
        )
    return normalized


async def _transaction_prices(conn, user_id, item_name: str, unit: str):
    """Return last and weighted-average UZS prices for one exact canonical unit."""
    prices = await conn.fetchrow(
        """WITH priced AS MATERIALIZED (
               SELECT id, amount, quantity, amount / quantity AS unit_price,
                      occurred_at
               FROM transactions
               WHERE user_id=$1 AND type='expense' AND currency='UZS'
                 AND LOWER(item_name_normalized)=LOWER($2) AND unit=$3
                 AND quantity IS NOT NULL AND quantity > 0
           )
           SELECT (ARRAY_AGG(unit_price ORDER BY occurred_at DESC, id DESC))[1]
                      AS last_price,
                  (ARRAY_AGG(occurred_at ORDER BY occurred_at DESC, id DESC))[1]
                      AS last_as_of,
                  SUM(amount) / SUM(quantity) AS average_price,
                  MAX(occurred_at) AS average_as_of,
                  COUNT(*)::integer AS purchase_count
           FROM priced""",
        user_id,
        item_name,
        unit,
    )
    return {
        "last_price": (
            None if prices["last_price"] is None else Decimal(prices["last_price"])
        ),
        "last_as_of": prices["last_as_of"],
        "average_price": (
            None
            if prices["average_price"] is None
            else Decimal(prices["average_price"])
        ),
        "average_as_of": prices["average_as_of"],
        "purchase_count": prices["purchase_count"],
    }


async def _get_price_lookup(pool, user_id, items: list[dict]) -> list[dict]:
    result = []
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            for item in items:
                prices = await _transaction_prices(
                    conn, user_id, item["item_name_normalized"], item["unit"]
                )
                price_basis = item["price_basis"]
                if price_basis == "last":
                    reference_price = prices["last_price"]
                    price_as_of = prices["last_as_of"]
                else:
                    reference_price = prices["average_price"]
                    price_as_of = prices["average_as_of"]
                result.append(
                    {
                        "item_name_normalized": item["item_name_normalized"],
                        "unit": item["unit"],
                        "last_unit_price_uzs": (
                            None
                            if prices["last_price"] is None
                            else _json_number(prices["last_price"])
                        ),
                        "last_price_as_of": _iso_utc(prices["last_as_of"]),
                        "average_unit_price_uzs": (
                            None
                            if prices["average_price"] is None
                            else _json_number(prices["average_price"])
                        ),
                        "priced_purchase_count": prices["purchase_count"],
                        "price_basis": price_basis,
                        "reference_unit_price_uzs": (
                            None
                            if reference_price is None
                            else _json_number(reference_price)
                        ),
                        "price_as_of": _iso_utc(price_as_of),
                    }
                )
    return result


async def _resolve_plan_item_price(conn, user_id, item: dict) -> dict:
    """Freeze the selected factual/manual price into a new item-plan snapshot."""
    resolved = dict(item)
    unit = item["unit"]
    if unit is None:
        resolved["reference_unit_price_uzs"] = None
        resolved["price_basis"] = None
        resolved["price_as_of"] = None
        return resolved

    basis = item["price_basis"] or "last"
    price = None
    price_as_of = None
    if basis == "manual":
        price = item["reference_unit_price_uzs"]
        price_as_of = item["price_as_of"] or datetime.now(timezone.utc)
    else:
        prices = await _transaction_prices(
            conn, user_id, item["item_name_normalized"], unit
        )
        if basis == "last":
            price = prices["last_price"]
            price_as_of = prices["last_as_of"]
        else:
            price = prices["average_price"]
            price_as_of = prices["average_as_of"]
        supplied_price = item["reference_unit_price_uzs"]
        supplied_as_of = item["price_as_of"]
        if supplied_price is not None and supplied_price != price:
            raise ValueError(
                "INVALID_INPUT: supplied reference price does not match transaction facts"
            )
        if supplied_as_of is not None and supplied_as_of != price_as_of:
            raise ValueError(
                "INVALID_INPUT: supplied price_as_of does not match transaction facts"
            )

    if price is None:
        resolved["reference_unit_price_uzs"] = None
        resolved["price_basis"] = None
        resolved["price_as_of"] = None
    else:
        resolved["reference_unit_price_uzs"] = price
        resolved["price_basis"] = basis
        resolved["price_as_of"] = price_as_of
        derived_amount = (resolved["planned_quantity"] * price).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if resolved["planned_amount_uzs"] is None:
            resolved["planned_amount_uzs"] = derived_amount
        elif resolved["planned_amount_uzs"] != derived_amount:
            raise ValueError(
                "INVALID_INPUT: planned_amount_uzs must equal quantity × reference price"
            )
    return resolved


_ITEMS_OMITTED = object()


async def set_monthly_budget(
    pool,
    user_id,
    month,
    category_code,
    planned_amount_uzs,
    note=None,
    items=_ITEMS_OMITTED,
):
    if items is not _ITEMS_OMITTED and (
        not isinstance(items, list) or not items
    ):
        raise ValueError("INVALID_INPUT: items must be omitted or non-empty")
    month_date = _budget_month(month)
    amount = _budget_amount(planned_amount_uzs)
    normalized_items = (
        None if items is _ITEMS_OMITTED else _normalize_plan_items(items)
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            if not await valid_category(conn, category_code):
                raise ValueError("BAD_CATEGORY:" + str(category_code))
            row = await conn.fetchrow(
                """WITH ins AS (
                       INSERT INTO monthly_budget_plans
                           (user_id, month, category_code, planned_amount_uzs, note)
                       VALUES ($1,$2,$3,$4,$5)
                       ON CONFLICT (user_id, month, category_code) DO NOTHING
                       RETURNING id
                   ), upd AS (
                       UPDATE monthly_budget_plans
                       SET planned_amount_uzs=$4, note=$5, updated_at=now()
                       WHERE user_id=$1 AND month=$2 AND category_code=$3
                         AND NOT EXISTS (SELECT 1 FROM ins)
                       RETURNING id
                   )
                   SELECT id, true AS created FROM ins
                   UNION ALL
                   SELECT id, false AS created FROM upd
                   LIMIT 1""",
                user_id,
                month_date,
                category_code,
                amount,
                note,
            )
            if normalized_items is not None:
                resolved_items = [
                    await _resolve_plan_item_price(conn, user_id, item)
                    for item in normalized_items
                ]
                await conn.execute(
                    """DELETE FROM monthly_budget_items
                       WHERE user_id=$1 AND month=$2 AND category_code=$3""",
                    user_id,
                    month_date,
                    category_code,
                )
                for item in resolved_items:
                    await conn.execute(
                        """INSERT INTO monthly_budget_items
                           (user_id, month, category_code, item_name_normalized,
                            item_name_display, planned_quantity, unit,
                            planned_amount_uzs, reference_unit_price_uzs,
                            price_basis, price_as_of, note)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                        user_id,
                        month_date,
                        category_code,
                        item["item_name_normalized"],
                        item["item_name_display"],
                        item["planned_quantity"],
                        item["unit"],
                        item["planned_amount_uzs"],
                        item["reference_unit_price_uzs"],
                        item["price_basis"],
                        item["price_as_of"],
                        item["note"],
                    )
    if not row:
        raise RuntimeError("monthly budget upsert returned no row")
    return {"plan_id": row["id"], "created": row["created"]}


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _get_monthly_budget_items(
    pool, user_id, month_date: date, start_utc: datetime, end_utc: datetime
):
    plan_rows = await pool.fetch(
        """SELECT item_name_normalized, item_name_display, category_code,
                  planned_quantity, unit, planned_amount_uzs,
                  reference_unit_price_uzs, price_basis, price_as_of
           FROM monthly_budget_items
           WHERE user_id=$1 AND month=$2
           ORDER BY category_code, item_name_normalized""",
        user_id,
        month_date,
    )
    result = []
    for plan in plan_rows:
        actual_rows = await pool.fetch(
            """SELECT amount, quantity, unit
               FROM transactions
               WHERE user_id=$1 AND type='expense' AND currency='UZS'
                 AND item_name_normalized=$2
                 AND occurred_at >= $3 AND occurred_at < $4
                 AND (
                     category_code=$5
                     OR ($5='food' AND category_code LIKE 'food.%')
                 )""",
            user_id,
            plan["item_name_normalized"],
            start_utc,
            end_utc,
            plan["category_code"],
        )
        actual_amount = sum((Decimal(row["amount"]) for row in actual_rows), Decimal(0))
        actual_quantity = None
        actual_unit = None
        if actual_rows and all(
            row["quantity"] is not None and row["unit"] is not None
            for row in actual_rows
        ):
            units = {row["unit"] for row in actual_rows}
            if len(units) == 1:
                actual_unit = units.pop()
                actual_quantity = sum(
                    (Decimal(row["quantity"]) for row in actual_rows), Decimal(0)
                )

        unit = plan["unit"]
        prices = None
        if unit is not None:
            prices = await _transaction_prices(
                pool, user_id, plan["item_name_normalized"], unit
            )
        planned_amount = plan["planned_amount_uzs"]
        result.append(
            {
                "item_name_normalized": plan["item_name_normalized"],
                "item_name_display": plan["item_name_display"],
                "planned_quantity": (
                    None
                    if plan["planned_quantity"] is None
                    else _json_number(plan["planned_quantity"])
                ),
                "planned_unit": unit,
                "planned_amount_uzs": (
                    None if planned_amount is None else _json_number(planned_amount)
                ),
                "actual_quantity": (
                    None
                    if actual_quantity is None
                    else _json_number(actual_quantity)
                ),
                "actual_unit": actual_unit,
                "actual_amount_uzs": _json_number(actual_amount),
                "remaining_amount_uzs": (
                    None
                    if planned_amount is None
                    else _json_number(Decimal(planned_amount) - actual_amount)
                ),
                "last_unit_price_uzs": (
                    None
                    if prices is None or prices["last_price"] is None
                    else _json_number(prices["last_price"])
                ),
                "average_unit_price_uzs": (
                    None
                    if prices is None or prices["average_price"] is None
                    else _json_number(prices["average_price"])
                ),
                "reference_unit_price_uzs": (
                    None
                    if plan["reference_unit_price_uzs"] is None
                    else _json_number(plan["reference_unit_price_uzs"])
                ),
                "price_basis": plan["price_basis"],
                "price_as_of": _iso_utc(plan["price_as_of"]),
            }
        )
    return result


async def get_monthly_budget_status(
    pool, user_id, month, include_items=False, price_lookup_items=None
):
    if not isinstance(include_items, bool):
        raise ValueError("INVALID_INPUT: include_items must be boolean")
    normalized_lookup = (
        None
        if price_lookup_items is None
        else _normalize_price_lookup_items(price_lookup_items)
    )
    month_date = _budget_month(month)
    start_t = datetime(month_date.year, month_date.month, 1, tzinfo=TASHKENT)
    end_t = _shift_month(start_t, 1)
    start_utc = start_t.astimezone(timezone.utc)
    end_utc = end_t.astimezone(timezone.utc)
    rows = await pool.fetch(
        """WITH planned AS (
               SELECT category_code, planned_amount_uzs AS planned_uzs
               FROM monthly_budget_plans
               WHERE user_id=$1 AND month=$2
           ), actual AS (
               SELECT CASE
                          WHEN EXISTS (
                              SELECT 1 FROM planned exact_plan
                              WHERE exact_plan.category_code = t.category_code
                          ) THEN t.category_code
                          WHEN t.category_code LIKE 'food.%'
                               AND EXISTS (
                                   SELECT 1 FROM planned parent_plan
                                   WHERE parent_plan.category_code = 'food'
                               ) THEN 'food'
                          ELSE t.category_code
                      END AS category_code,
                      SUM(t.amount)::numeric AS actual_uzs
               FROM transactions t
               WHERE t.user_id=$1 AND t.type='expense' AND t.currency='UZS'
                 AND t.occurred_at >= $3 AND t.occurred_at < $4
               GROUP BY 1
           )
           SELECT COALESCE(p.category_code, a.category_code) AS category_code,
                  COALESCE(p.planned_uzs, 0)::numeric AS planned_uzs,
                  COALESCE(a.actual_uzs, 0)::numeric AS actual_uzs
           FROM planned p
           FULL OUTER JOIN actual a ON a.category_code = p.category_code
           ORDER BY COALESCE(p.category_code, a.category_code) NULLS LAST""",
        user_id,
        month_date,
        start_utc,
        end_utc,
    )
    planned_total = Decimal(0)
    actual_total = Decimal(0)
    by_category = []
    for row in rows:
        planned = Decimal(row["planned_uzs"])
        actual = Decimal(row["actual_uzs"])
        planned_total += planned
        actual_total += actual
        usage = None if planned == 0 else round(float(actual / planned * 100), 4)
        by_category.append({
            "category_code": row["category_code"],
            "planned_uzs": _json_number(planned),
            "actual_uzs": _json_number(actual),
            "difference_uzs": _json_number(planned - actual),
            "usage_percent": usage,
        })
    result = {
        "month": month_date.isoformat(),
        "planned_total_uzs": _json_number(planned_total),
        "actual_total_uzs": _json_number(actual_total),
        "remaining_uzs": _json_number(planned_total - actual_total),
        "by_category": by_category,
    }
    if include_items:
        result["items"] = await _get_monthly_budget_items(
            pool, user_id, month_date, start_utc, end_utc
        )
    if normalized_lookup is not None:
        result["price_lookup"] = await _get_price_lookup(
            pool, user_id, normalized_lookup
        )
    return result


# ---------------------------------------------------------------------------
# Stage 5.3A — monthly plan approval cycle (deterministic state machine).
# Backend stores/validates only; identity (self-only oyijon, admin narrow
# cross-target allowlist) is enforced by the identity guard before backend.
# ---------------------------------------------------------------------------
APPROVAL_SOURCES = ("oyijon", "admin", "auto")
_APPROVAL_TARGET_STATUS = {
    "oyijon": "approved_by_oyijon",
    "admin": "approved_by_admin",
    "auto": "auto_approved",
}
_CYCLE_TERMINAL = {"approved_by_oyijon", "approved_by_admin", "auto_approved"}
_CYCLE_NON_TERMINAL = {"draft", "waiting_oyijon", "waiting_admin"}


def _cycle_err(code: str) -> dict:
    return {"_cycle_error": code}


def _cycle_result(month_date: date, row, *, idempotent: bool, plan_copied: bool) -> dict:
    return {
        "month": month_date.isoformat(),
        "status": row["status"],
        "source": row["source"],
        "household_size": row["household_size"],
        "approved_by_user_id": row["approved_by_user_id"],
        "approved_at": _iso_utc(row["approved_at"]),
        "idempotent": idempotent,
        "plan_copied": plan_copied,
    }


async def _plan_is_valid(conn, user_id, month_date: date) -> bool:
    """A valid (non-empty) draft has >=1 category plan row with positive total."""
    row = await conn.fetchrow(
        """SELECT COUNT(*) AS cnt, COALESCE(SUM(planned_amount_uzs), 0) AS total
           FROM monthly_budget_plans WHERE user_id=$1 AND month=$2""",
        user_id, month_date,
    )
    return row["cnt"] > 0 and Decimal(row["total"]) > 0


async def _last_approved_month(conn, user_id, before_month: date):
    return await conn.fetchval(
        """SELECT c.month FROM monthly_plan_cycles c
           WHERE c.user_id=$1 AND c.month < $2
             AND c.status IN ('approved_by_oyijon','approved_by_admin','auto_approved')
             AND EXISTS (SELECT 1 FROM monthly_budget_plans p
                         WHERE p.user_id=$1 AND p.month=c.month)
           ORDER BY c.month DESC LIMIT 1""",
        user_id, before_month,
    )


async def _copy_plan(conn, user_id, src_month: date, dst_month: date):
    """Copy category plans and product items from src_month into dst_month."""
    await conn.execute(
        """INSERT INTO monthly_budget_plans (user_id, month, category_code, planned_amount_uzs, note)
           SELECT user_id, $3, category_code, planned_amount_uzs, note
           FROM monthly_budget_plans WHERE user_id=$1 AND month=$2""",
        user_id, src_month, dst_month,
    )
    await conn.execute(
        """INSERT INTO monthly_budget_items
           (user_id, month, category_code, item_name_normalized, item_name_display,
            planned_quantity, unit, planned_amount_uzs, reference_unit_price_uzs,
            price_basis, price_as_of, note)
           SELECT user_id, $3, category_code, item_name_normalized, item_name_display,
                  planned_quantity, unit, planned_amount_uzs, reference_unit_price_uzs,
                  price_basis, price_as_of, note
           FROM monthly_budget_items WHERE user_id=$1 AND month=$2""",
        user_id, src_month, dst_month,
    )


async def approve_monthly_plan(
    pool, user_id, month, source,
    approved_by_user_id=None, household_size=None, now=None,
):
    _one_of("source", source, APPROVAL_SOURCES)
    month_date = _budget_month(month)

    if household_size is not None and (
        isinstance(household_size, bool)
        or not isinstance(household_size, int)
        or household_size <= 0
    ):
        raise ValueError("INVALID_INPUT: household_size must be a positive integer")
    if approved_by_user_id is not None and (
        isinstance(approved_by_user_id, bool) or not isinstance(approved_by_user_id, int)
    ):
        raise ValueError("INVALID_INPUT: approved_by_user_id must be an integer")

    now_utc = now or datetime.now(timezone.utc)
    now_t = now_utc.astimezone(TASHKENT)
    month_start_t = datetime(month_date.year, month_date.month, 1, tzinfo=TASHKENT)
    target_status = _APPROVAL_TARGET_STATUS[source]

    # Backend-level identity guard rails (guard also enforces these upstream).
    if source == "oyijon":
        if approved_by_user_id is not None and approved_by_user_id != user_id:
            return _cycle_err("SELF_ONLY_VIOLATION")
        approver = user_id
    elif source == "admin":
        if approved_by_user_id is None or approved_by_user_id == user_id:
            return _cycle_err("ADMIN_TARGET_REQUIRED")
        approver = approved_by_user_id
    else:
        if approved_by_user_id is not None:
            return _cycle_err("INVALID_APPROVER")
        approver = None

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT status, source, household_size, approved_by_user_id, approved_at
                   FROM monthly_plan_cycles WHERE user_id=$1 AND month=$2 FOR UPDATE""",
                user_id, month_date,
            )
            current_status = row["status"] if row else None

            # Idempotent replay: already in the exact target status → no write,
            # even if the month has since started (retry/cron safety).
            if current_status == target_status:
                return _cycle_result(month_date, row, idempotent=True, plan_copied=False)
            # Any other terminal status is an illegal transition.
            if current_status in _CYCLE_TERMINAL:
                return _cycle_err("INVALID_STATUS_TRANSITION")

            # Deterministic month-boundary gate (Asia/Tashkent), before any write.
            if source in ("oyijon", "admin"):
                # Manual approval only strictly BEFORE the planned month begins.
                if now_t >= month_start_t:
                    return _cycle_err("MONTH_ALREADY_STARTED")
            else:  # auto: cron "1st" safety net, only on the first calendar day.
                if now_t < month_start_t:
                    return _cycle_err("MONTH_NOT_STARTED")
                if now_t >= month_start_t + timedelta(days=1):
                    return _cycle_err("MONTH_ALREADY_STARTED")

            plan_copied = False
            if row is None:
                if source == "auto":
                    prev = await _last_approved_month(conn, user_id, month_date)
                    if prev is None:
                        return _cycle_err("NO_PLAN_SOURCE")
                    await _copy_plan(conn, user_id, prev, month_date)
                    plan_copied = True
                    cycle_source = "copied_previous"
                else:
                    return _cycle_err("NO_DRAFT")
            else:
                cycle_source = row["source"]

            if not await _plan_is_valid(conn, user_id, month_date):
                return _cycle_err("EMPTY_DRAFT")

            if row is None:
                new = await conn.fetchrow(
                    """INSERT INTO monthly_plan_cycles
                       (user_id, month, status, household_size, source,
                        approved_at, approved_by_user_id)
                       VALUES ($1,$2,$3,$4,$5,$6,$7)
                       RETURNING status, source, household_size,
                                 approved_by_user_id, approved_at""",
                    user_id, month_date, target_status, household_size,
                    cycle_source, now_utc, approver,
                )
            else:
                new = await conn.fetchrow(
                    """UPDATE monthly_plan_cycles
                       SET status=$3, approved_at=$4, approved_by_user_id=$5,
                           household_size=COALESCE($6, household_size), updated_at=now()
                       WHERE user_id=$1 AND month=$2
                       RETURNING status, source, household_size,
                                 approved_by_user_id, approved_at""",
                    user_id, month_date, target_status, now_utc, approver, household_size,
                )
    return _cycle_result(month_date, new, idempotent=False, plan_copied=plan_copied)


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
    _one_of("severity", severity, HEALTH_SEVERITIES)
    return await pool.fetchval(
        """INSERT INTO health_notes (user_id, note, severity, source_text)
           VALUES ($1,$2,$3,$4) RETURNING id""",
        user_id, note, severity, source_text,
    )


async def save_alert_event(pool, user_id, alert_type, severity, source_text,
                           bot_response, detected_by, sent_to_admin):
    _one_of("severity", severity, ALERT_SEVERITIES)
    _one_of("detected_by", detected_by, DETECTED_BY, allow_none=True)
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
    report_date = date_str or datetime.now(TASHKENT).date().isoformat()
    start, end = _day_bounds(report_date)
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
        "date": report_date,
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
    _one_of("service_type", service_type, SERVICE_TYPES)
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
