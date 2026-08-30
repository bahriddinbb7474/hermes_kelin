"""imp12-opus: get_daily_news hands the model at most 3 candidates.

imp07-opus's token audit found the model only ever picks 1-2 items out of
the previous 20-candidate payload (NEWS_SELECTION_NOTE already tells it to);
sending the rest cost ~2 500 tokens/turn for nothing. This pins the new cap
on the owner-scoped path (the one Mariyam's real tool call always takes,
see backend/server.py::t_get_daily_news) without touching the 30-minute
cache's own, larger internal bundle (_fetch_news keeps up to 20 unique items
so a later call with a different topic/source selection still has enough to
filter from).
"""
from __future__ import annotations

import pytest

from backend import db, external_data

RSS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>{items}</channel></rss>"""
ITEM_TEMPLATE = (
    "<item><title>{title}</title>"
    "<link>https://example.test/{n}</link></item>"
)


def _feed(prefix: str, count: int) -> bytes:
    items = "".join(
        ITEM_TEMPLATE.format(title=f"{prefix} факт {i}", n=f"{prefix}{i}")
        for i in range(count)
    )
    return RSS_TEMPLATE.format(items=items).encode("utf-8")


def _cache_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MARIYAM_EXTERNAL_CACHE_FILE", str(tmp_path / "cache.json"))


def _no_owner_extras(monkeypatch):
    """Owner has no custom feeds and no disabled defaults."""

    async def _no_sources(pool, user_id):
        return []

    async def _no_disabled(pool, user_id):
        return set()

    monkeypatch.setattr(db, "get_active_news_sources", _no_sources)
    monkeypatch.setattr(db, "get_disabled_default_keys", _no_disabled)


def test_max_digest_items_constant_is_three():
    assert external_data.MAX_NEWS_DIGEST_ITEMS == 3


@pytest.mark.asyncio
async def test_owner_scoped_daily_news_caps_at_three_even_with_many_sources(
    tmp_path, monkeypatch
):
    _cache_in(tmp_path, monkeypatch)
    _no_owner_extras(monkeypatch)

    # Four default sources, five items each: 20 unique candidates available.
    feeds = {
        "kun": _feed("kun", 5),
        "un_news_ru": _feed("un", 5),
        "dw_ru": _feed("dw", 5),
        "euronews_ru": _feed("euronews", 5),
    }

    # _fetch_news resolves source -> url via news_sources.json; patch at the
    # transport layer keyed by each source's own configured url.
    config = external_data._load_news_config()
    url_by_source = {
        key: item["url"] for key, item in config["sources_by_key"].items()
    }

    def fake_http_get_by_url(url):
        for key, feed_url in url_by_source.items():
            if url == feed_url:
                return feeds.get(key, feeds["kun"])
        return feeds["kun"]

    monkeypatch.setattr(external_data, "_http_get", fake_http_get_by_url)

    result = await external_data.get_daily_news(pool=object(), user_id=20)
    assert result["ok"] is True
    assert len(result["candidates"]) == external_data.MAX_NEWS_DIGEST_ITEMS


@pytest.mark.asyncio
async def test_fewer_than_three_candidates_are_not_padded_or_dropped(
    tmp_path, monkeypatch
):
    _cache_in(tmp_path, monkeypatch)
    _no_owner_extras(monkeypatch)
    config = external_data._load_news_config()
    only_kun = _feed("kun", 1)

    def fake_http_get(url):
        return only_kun if url == config["sources_by_key"]["kun"]["url"] else b"<rss><channel></channel></rss>"

    monkeypatch.setattr(external_data, "_http_get", fake_http_get)
    result = await external_data.get_daily_news(pool=object(), user_id=20)
    assert result["ok"] is True
    assert len(result["candidates"]) == 1
