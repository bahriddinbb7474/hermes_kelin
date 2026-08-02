"""imp09: news cache freshness, cache reset on change, disabling shipped feeds.

Three live defects this file pins down:

1. a feed added today stayed invisible until tomorrow — the owner's daily
   bundle had already been assembled (`invalidate_user_news_cache`);
2. shipped feeds (Кун.уз, Новости ООН, Дойче Велле, Евроньюс) could not be
   switched off at all — now a disabled default is stored as a row with the
   default's own key and `active=false`;
3. news were cached for a whole day; they now expire after 30 minutes, while
   weather and prayer times keep the daily contract.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from backend import db, external_data, server
from tests.db_guard import validate_destructive_test_target

REPO = Path(__file__).resolve().parents[1]
SQL_001 = REPO / "backend" / "sql" / "001_init.sql"
SQL_006 = REPO / "backend" / "sql" / "006_user_news_sources.sql"

BASE_NOW = datetime(2026, 8, 2, 6, 0, tzinfo=timezone.utc)
RSS = (
    "<rss><channel><item><title>Хабар</title>"
    "<link>https://news.example/item</link></item></channel></rss>"
).encode("utf-8")


def _cache_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MARIYAM_EXTERNAL_CACHE_FILE", str(tmp_path / "cache.json"))


def _freeze(monkeypatch, moment: datetime):
    monkeypatch.setattr(external_data, "_now_utc", lambda: moment)


# --- 1a. news TTL is 30 minutes, weather/prayer stay daily -------------------


@pytest.mark.asyncio
async def test_news_bundle_expires_after_thirty_minutes(tmp_path, monkeypatch):
    _cache_in(tmp_path, monkeypatch)
    calls = []

    def fetcher():
        calls.append(1)
        return {"candidates": [], "source_errors": [], "available_sources": []}

    _freeze(monkeypatch, BASE_NOW)
    await external_data._daily_cached(
        "news_user:1", fetcher, ttl_seconds=external_data.NEWS_CACHE_TTL_SECONDS
    )
    assert len(calls) == 1

    _freeze(monkeypatch, BASE_NOW + timedelta(minutes=25))
    result = await external_data._daily_cached(
        "news_user:1", fetcher, ttl_seconds=external_data.NEWS_CACHE_TTL_SECONDS
    )
    assert len(calls) == 1, "inside the TTL the bundle must be reused"
    assert result["cache"]["hit"] is True

    _freeze(monkeypatch, BASE_NOW + timedelta(minutes=31))
    result = await external_data._daily_cached(
        "news_user:1", fetcher, ttl_seconds=external_data.NEWS_CACHE_TTL_SECONDS
    )
    assert len(calls) == 2, "after 30 minutes the feed must be refetched"
    assert result["cache"]["hit"] is False


@pytest.mark.asyncio
async def test_weather_and_prayer_keep_the_daily_contract(tmp_path, monkeypatch):
    _cache_in(tmp_path, monkeypatch)
    calls = []

    def fetcher():
        calls.append(1)
        return {"temperature_c": 31.0}

    _freeze(monkeypatch, BASE_NOW)
    await external_data._daily_cached("weather_tashkent", fetcher)
    _freeze(monkeypatch, BASE_NOW + timedelta(hours=6))
    await external_data._daily_cached("weather_tashkent", fetcher)
    assert len(calls) == 1, "same Tashkent day must stay cached"

    # Next Tashkent day (UTC+5): 2026-08-02 06:00Z is 11:00 local, so +14h
    # crosses local midnight.
    _freeze(monkeypatch, BASE_NOW + timedelta(hours=14))
    await external_data._daily_cached("weather_tashkent", fetcher)
    assert len(calls) == 2


def test_news_ttl_is_thirty_minutes():
    assert external_data.NEWS_CACHE_TTL_SECONDS == 30 * 60


# --- 1. changing feeds drops only this owner's bundle -----------------------


@pytest.mark.asyncio
async def test_cache_reset_touches_only_this_owner(tmp_path, monkeypatch):
    _cache_in(tmp_path, monkeypatch)
    _freeze(monkeypatch, BASE_NOW)

    async def seed(key):
        await external_data._daily_cached(key, lambda: {"candidates": []})

    await seed(external_data.user_news_cache_key(20))
    await seed(external_data.user_news_cache_key(21))
    await seed("weather_tashkent")
    await seed("prayer_tashkent_fatvo_v1")

    assert external_data.invalidate_user_news_cache(20) is True
    entries = external_data._read_cache()["entries"]
    assert external_data.user_news_cache_key(20) not in entries
    assert external_data.user_news_cache_key(21) in entries, "other owners untouched"
    assert "weather_tashkent" in entries, "weather cache must survive"
    assert "prayer_tashkent_fatvo_v1" in entries, "prayer cache must survive"

    # Idempotent: nothing to drop the second time.
    assert external_data.invalidate_user_news_cache(20) is False


# --- 2. shipped feeds can be switched off ----------------------------------


def test_defaults_are_exposed_with_key_name_and_url():
    defaults = external_data.default_news_sources()
    keys = [item["source_key"] for item in defaults]
    assert keys == ["kun", "un_news_ru", "dw_ru", "euronews_ru"]
    assert all(item["url"].startswith("https://") for item in defaults)
    assert all(item["display_name"].strip() for item in defaults)


def test_empty_default_selection_returns_an_empty_bundle():
    """All defaults off + only custom feeds: the base bundle must stay valid."""
    bundle = external_data._fetch_news([], "daily")
    assert bundle["candidates"] == []
    assert bundle["available_sources"] == []
    assert bundle["selection_note"] == external_data.NEWS_SELECTION_NOTE
    assert bundle["available_topics"], "topics still come from the config"


def test_tool_schema_accepts_enable_and_source_key():
    entry = next(item for item in server.TOOLS if item[0] == "manage_news_sources")
    properties = entry[2]["properties"]
    assert set(properties["action"]["enum"]) == {"add", "disable", "enable", "list"}
    assert properties["source_key"]["pattern"] == "^[a-z0-9_]{2,40}$"
    assert "LAST_SOURCE" in server.NEWS_SOURCE_ERRORS


def test_custom_prefix_separates_the_two_kinds_of_rows():
    key = external_data.generated_news_source_key(20, "https://example.com/rss")
    assert key.startswith(db.CUSTOM_SOURCE_PREFIX)
    assert not any(
        item["source_key"].startswith(db.CUSTOM_SOURCE_PREFIX)
        for item in external_data.default_news_sources()
    )


# --- database-backed behaviour ---------------------------------------------


def _db_available() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return False
    try:
        validate_destructive_test_target(url)
    except Exception:
        return False
    return True


@pytest_asyncio.fixture
async def news_pool():
    if not _db_available():
        pytest.skip("requires disposable PostgreSQL test database")
    import asyncpg

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            await conn.execute(SQL_001.read_text(encoding="utf-8"))
            await conn.execute(SQL_006.read_text(encoding="utf-8"))
            await conn.execute("DELETE FROM user_news_sources")
            await conn.execute(
                """INSERT INTO users (id, telegram_id, role, display_name)
                   VALUES (901, 99000901, 'oyijon', 'Тест Ойижон')
                   ON CONFLICT (id) DO NOTHING"""
            )
        yield pool
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM user_news_sources WHERE user_id=901")
        await pool.close()


DEFAULTS = [
    {"source_key": "kun", "display_name": "Кун.уз", "url": "https://kun.uz/news/rss?lang=ru"},
    {"source_key": "euronews_ru", "display_name": "Евроньюс", "url": "https://euronews.example/rss"},
]


@pytest.mark.asyncio
async def test_disabling_a_default_hides_it_only_for_this_owner(news_pool):
    result = await db.manage_news_sources(
        news_pool, 901, "disable", source_key="euronews_ru",
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert result["kind"] == "default" and result["active"] is False

    assert await db.get_disabled_default_keys(news_pool, 901) == {"euronews_ru"}
    assert await db.get_disabled_default_keys(news_pool, 1) == set()
    # A disabled default is never mistaken for a feed to fetch.
    assert await db.get_active_news_sources(news_pool, 901) == []

    listing = await db.manage_news_sources(
        news_pool, 901, "list", defaults=DEFAULTS,
    )
    states = {item["source_key"]: item["active"] for item in listing["sources"]}
    assert states == {"kun": True, "euronews_ru": False}
    assert all(item["kind"] == "default" for item in listing["sources"])


@pytest.mark.asyncio
async def test_enabling_a_default_removes_the_disable_row(news_pool):
    await db.manage_news_sources(
        news_pool, 901, "disable", source_key="euronews_ru",
        added_by="oyijon", defaults=DEFAULTS,
    )
    again = await db.manage_news_sources(
        news_pool, 901, "disable", source_key="euronews_ru",
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert again["idempotent"] is True

    result = await db.manage_news_sources(
        news_pool, 901, "enable", source_key="euronews_ru",
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert result["active"] is True and result["idempotent"] is False
    assert await db.get_disabled_default_keys(news_pool, 901) == set()

    repeat = await db.manage_news_sources(
        news_pool, 901, "enable", source_key="euronews_ru",
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert repeat["idempotent"] is True


@pytest.mark.asyncio
async def test_last_active_source_cannot_be_switched_off(news_pool):
    await db.manage_news_sources(
        news_pool, 901, "disable", source_key="kun",
        added_by="oyijon", defaults=DEFAULTS,
    )
    blocked = await db.manage_news_sources(
        news_pool, 901, "disable", source_key="euronews_ru",
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert blocked == {"_news_source_error": "LAST_SOURCE"}
    assert await db.get_disabled_default_keys(news_pool, 901) == {"kun"}


@pytest.mark.asyncio
async def test_custom_feed_survives_as_the_last_source(news_pool):
    added = await db.manage_news_sources(
        news_pool, 901, "add",
        source_key=external_data.generated_news_source_key(901, "https://habr.example/rss"),
        display_name="Технология хабарлари", url="https://habr.example/rss",
        topics=["технология"], added_by="oyijon", defaults=DEFAULTS,
    )
    assert added["active"] is True

    for key in ("kun", "euronews_ru"):
        await db.manage_news_sources(
            news_pool, 901, "disable", source_key=key,
            added_by="oyijon", defaults=DEFAULTS,
        )

    listing = await db.manage_news_sources(news_pool, 901, "list", defaults=DEFAULTS)
    assert listing["active_total"] == 1
    custom = [item for item in listing["sources"] if item["kind"] == "custom"]
    assert len(custom) == 1 and custom[0]["active"] is True

    blocked = await db.manage_news_sources(
        news_pool, 901, "disable", source_id=custom[0]["source_id"],
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert blocked == {"_news_source_error": "LAST_SOURCE"}


@pytest.mark.asyncio
async def test_custom_feed_can_be_disabled_and_enabled_again(news_pool):
    added = await db.manage_news_sources(
        news_pool, 901, "add",
        source_key=external_data.generated_news_source_key(901, "https://habr.example/rss"),
        display_name="Технология хабарлари", url="https://habr.example/rss",
        topics=["технология"], added_by="oyijon", defaults=DEFAULTS,
    )
    off = await db.manage_news_sources(
        news_pool, 901, "disable", source_id=added["source_id"],
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert off["active"] is False and off["kind"] == "custom"
    assert await db.get_active_news_sources(news_pool, 901) == []

    on = await db.manage_news_sources(
        news_pool, 901, "enable", source_id=added["source_id"],
        added_by="oyijon", defaults=DEFAULTS,
    )
    assert on["active"] is True
    assert len(await db.get_active_news_sources(news_pool, 901)) == 1
