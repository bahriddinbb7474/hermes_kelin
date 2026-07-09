"""Hermes/Mariyam backend — config & DB pool.
Источник истины: TZ_Hermes_Mariyam_FINAL_v3_0.md, разделы 13-16.
Secrets only via .env / env vars (SECURITY_PRIVACY.md).
Time: all timestamps UTC ISO 8601. Day boundaries in Asia/Tashkent (UTC+5).
"""
import os
from datetime import timezone
import asyncpg

TASHKENT = timezone(offset=__import__("datetime").timedelta(hours=5))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://hermes:hermes@localhost:5432/hermes",
)


async def get_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)


def parse_dt(value: str | None):
    """Parse a UTC ISO 8601 string. Returns timezone-aware datetime (UTC)."""
    if not value:
        return None
    s = value.strip().replace("Z", "+00:00")
    from datetime import datetime

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
