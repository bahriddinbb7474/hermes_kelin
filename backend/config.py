"""Hermes/Mariyam backend — config & DB pool.
Источник истины: TZ_Hermes_Mariyam_FINAL_v3_0.md, разделы 13-16.
Secrets only via .env / env vars (SECURITY_PRIVACY.md).
Time: all timestamps UTC ISO 8601. Day boundaries in Asia/Tashkent.
"""
import asyncio
import os
from datetime import timezone
from zoneinfo import ZoneInfo

import asyncpg

TASHKENT = ZoneInfo("Asia/Tashkent")

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure backend/.env or environment. "
            "Weak fallback credentials are forbidden (TZ §17)."
        )
    return url


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(get_database_url(), min_size=1, max_size=5)
    return _pool


def parse_dt(value: str | None):
    """Parse a UTC ISO 8601 string. Returns timezone-aware datetime (UTC)."""
    if not value:
        return None
    from datetime import datetime

    s = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
