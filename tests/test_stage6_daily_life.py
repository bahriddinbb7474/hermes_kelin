"""Stage 6 daily-life external facts, cache and canonical cron contracts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import external_data, server

REPO = Path(__file__).resolve().parents[1]
CRON = REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "cron"


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    path = tmp_path / "external-cache.json"
    monkeypatch.setenv("MARIYAM_EXTERNAL_CACHE_FILE", str(path))
    return path


@pytest.mark.asyncio
async def test_inventory_dispatch_and_discovery_are_29():
    tools = await server.list_tools()
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 29
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names))
    assert names[-3:] == [
        "get_tashkent_weather",
        "get_tashkent_prayer_times",
        "get_daily_news",
    ]
    schemas = {tool.name: tool.inputSchema for tool in tools}
    for name in names[-3:]:
        assert schemas[name] == {
            "type": "object",
            "properties": {},
            "required": [],
        }


@pytest.mark.asyncio
async def test_daily_cache_hit_and_honest_stale_fallback(cache_env, monkeypatch):
    first_day = datetime(2026, 7, 26, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(external_data, "_now_utc", lambda: first_day)
    calls = 0

    def fresh():
        nonlocal calls
        calls += 1
        return {"city": "Tashkent", "temperature_c": 31.0}

    first = await external_data._daily_cached("weather_test", fresh)
    second = await external_data._daily_cached("weather_test", fresh)
    assert first["ok"] and not first["cache"]["hit"]
    assert second["ok"] and second["cache"]["hit"]
    assert calls == 1

    next_day = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(external_data, "_now_utc", lambda: next_day)

    def unavailable():
        raise external_data.ExternalDataError("offline")

    stale = await external_data._daily_cached("weather_test", unavailable)
    assert stale["ok"] is True
    assert stale["temperature_c"] == 31.0
    assert stale["cache"]["stale"] is True
    assert stale["cache"]["note_uz"] == "Манба ҳозир очилмади. Бу олдинги маълумот."
    assert "offline" not in json.dumps(stale, ensure_ascii=False)


@pytest.mark.asyncio
async def test_no_cache_and_missing_weather_key_is_honest(cache_env, monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    result = await external_data.get_tashkent_weather()
    assert result["ok"] is False
    assert result["error_code"] == "EXTERNAL_DATA_UNAVAILABLE"
    assert result["cache"] == {"hit": False, "stale": False, "fetched_at": None}
    assert "тахмин қилманг" in result["message_uz"]


def test_weather_contract_uses_secret_without_leaking_it(monkeypatch):
    secret = "stage6-secret-value"
    monkeypatch.setenv("OPENWEATHER_API_KEY", secret)
    captured = {}

    def fake_json(url):
        captured["url"] = url
        return {
            "cod": 200,
            "main": {"temp": 34.2, "feels_like": 35.1, "humidity": 25},
            "weather": [{"description": "ясно"}],
            "wind": {"speed": 2.5},
            "dt": 1785049200,
        }

    monkeypatch.setattr(external_data, "_json_get", fake_json)
    value = external_data._fetch_weather()
    assert "Tashkent%2CUZ" in captured["url"]
    assert f"appid={secret}" in captured["url"]
    assert secret not in json.dumps(value)
    assert value["source"] == "OpenWeather"


def test_prayer_contract_is_tashkent_hanafi(monkeypatch):
    captured = {}

    def fake_json(url):
        captured["url"] = url
        return {
            "code": 200,
            "data": {
                "timings": {
                    "Fajr": "03:42 (+05)",
                    "Sunrise": "05:10 (+05)",
                    "Dhuhr": "12:29 (+05)",
                    "Asr": "17:23 (+05)",
                    "Maghrib": "19:47 (+05)",
                    "Isha": "21:15 (+05)",
                },
                "date": {"gregorian": {"date": "26-07-2026"}},
            },
        }

    monkeypatch.setattr(external_data, "_json_get", fake_json)
    value = external_data._fetch_prayer_times()
    assert "city=Tashkent" in captured["url"]
    assert "country=Uzbekistan" in captured["url"]
    assert "method=3" in captured["url"]
    assert "school=1" in captured["url"]
    assert value["school"] == "Hanafi"
    assert value["asr"] == "17:23"


def test_news_uses_only_agreed_sources_and_deduplicates(monkeypatch):
    assert external_data.NEWS_FEEDS == (
        ("uza", "UzA", "https://uza.uz/ru/rss"),
        ("kun", "Kun.uz", "https://kun.uz/news/rss?lang=ru"),
    )
    uza = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item><title>Calm local fact</title>
    <link>https://uza.uz/ru/posts/1</link><pubDate>Sun, 26 Jul 2026 08:00:00 +0500</pubDate>
    </item></channel></rss>"""
    kun = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
    <item><title>Calm local fact</title><link>https://kun.uz/ru/news/1</link></item>
    <item><title>Second local fact</title><link>https://kun.uz/ru/news/2</link></item>
    </channel></rss>"""

    def fake_get(url):
        return uza if "uza.uz" in url else kun

    monkeypatch.setattr(external_data, "_http_get", fake_get)
    value = external_data._fetch_news()
    assert value["agreed_sources"] == ["UzA", "Kun.uz"]
    assert [item["title_ru"] for item in value["candidates"]] == [
        "Calm local fact",
        "Second local fact",
    ]
    assert {item["source"] for item in value["candidates"]} == {"UzA", "Kun.uz"}
    assert value["source_errors"] == []


def test_daily_life_cron_prompts_are_narrow_read_only_and_cyrillic():
    expected = {
        "06_morning.md": (
            "get_tashkent_weather",
            "get_tashkent_prayer_times",
            "get_recurring_obligations",
            "get_daily_news",
        ),
        "06_evening.md": ("get_admin_report_data",),
        "06_obligation_reminders.md": ("get_recurring_obligations",),
    }
    forbidden = (
        "save_expense",
        "upsert_recurring_obligation",
        "save_plan_note",
        "terminal",
        "execute_code",
    )
    for filename, tools in expected.items():
        text = (CRON / filename).read_text(encoding="utf-8")
        for tool in tools:
            assert tool in text
        for tool in forbidden:
            assert tool not in text
        assert "user_id=0" in text
        assert "битта" in text.casefold()


def test_one_shot_contract_is_untrusted_plain_text():
    soul = (
        REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "SOUL.md"
    ).read_text(encoding="utf-8")
    assert "one-shot" in soul
    assert "untrusted" in soul
    assert "user-scoped" in soul
    assert "чистый текст" in soul
    assert "cronjob" in soul
