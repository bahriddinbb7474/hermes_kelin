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
async def test_inventory_dispatch_and_discovery_are_30():
    tools = await server.list_tools()
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 30
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names))
    assert names[-4:] == [
        "get_tashkent_weather",
        "get_tashkent_prayer_times",
        "get_daily_news",
        "manage_news_sources",
    ]
    schemas = {tool.name: tool.inputSchema for tool in tools}
    for name in ("get_tashkent_weather", "get_tashkent_prayer_times"):
        assert schemas[name] == {
            "type": "object",
            "properties": {},
            "required": [],
        }
    assert set(schemas["get_daily_news"]["properties"]) == {"user_id", "topic", "sources"}
    assert schemas["get_daily_news"]["required"] == ["user_id"]


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
                "date": {
                    "gregorian": {"date": "02-08-2026"},
                    "hijri": {
                        "date": "19-02-1448",
                        "day": "19",
                        "month": {"number": 2, "en": "Safar"},
                        "year": "1448",
                    },
                },
            },
        }

    monkeypatch.setattr(external_data, "_json_get", fake_json)
    value = external_data._fetch_prayer_times()
    assert "city=Tashkent" in captured["url"]
    assert "country=Uzbekistan" in captured["url"]
    assert "method=99" in captured["url"]
    assert "school=1" in captured["url"]
    assert "methodSettings=15.5%2Cnull%2C15.5" in captured["url"]
    assert "tune=0%2C0%2C-5%2C5%2C0%2C5%2C0%2C-4%2C0" in captured["url"]
    assert value["school"] == "Hanafi"
    assert value["asr"] == "17:23"
    assert value["hijri_display_uz"] == "19 САФАР (1448)"
    assert value["source"] == "Aladhan (custom settings matched to Fatvo.uz)"


def test_prayer_custom_method_matches_fatvo_calendar_on_ten_seasonal_dates():
    # Captured 2026-08-02 from the public Fatvo API and the Fatvo calendar's
    # published ihtiyot adjustments: sunrise -5, dhuhr +5, maghrib +1,
    # isha -4.  Values were checked live on 2026-08-02.
    references = {
        "15-01-2026": ("06:23", "07:42", "12:37", "15:37", "17:23", "18:38"),
        "15-02-2026": ("05:59", "07:13", "12:42", "16:14", "18:02", "19:12"),
        "15-03-2026": ("05:17", "06:30", "12:37", "16:42", "18:34", "19:44"),
        "15-04-2026": ("04:20", "05:39", "12:28", "17:06", "19:08", "20:23"),
        "15-05-2026": ("03:29", "05:00", "12:24", "17:24", "19:40", "21:06"),
        "15-06-2026": ("03:03", "04:44", "12:29", "17:39", "20:03", "21:40"),
        "02-08-2026": ("03:45", "05:14", "12:34", "17:31", "19:44", "21:09"),
        "15-09-2026": ("04:43", "05:58", "12:23", "16:43", "18:38", "19:49"),
        "15-10-2026": ("05:16", "06:29", "12:14", "15:59", "17:48", "18:57"),
        "15-12-2026": ("06:16", "07:37", "12:23", "15:13", "16:59", "18:16"),
    }
    custom = {
        "15-01-2026": ("06:23", "07:42", "12:37", "15:37", "17:24", "18:38"),
        "15-02-2026": ("05:59", "07:13", "12:42", "16:13", "18:02", "19:12"),
        "15-03-2026": ("05:17", "06:30", "12:37", "16:42", "18:34", "19:44"),
        "15-04-2026": ("04:20", "05:39", "12:28", "17:05", "19:08", "20:23"),
        "15-05-2026": ("03:30", "05:00", "12:25", "17:24", "19:40", "21:06"),
        "15-06-2026": ("03:04", "04:45", "12:29", "17:39", "20:03", "21:39"),
        "02-08-2026": ("03:46", "05:14", "12:34", "17:32", "19:44", "21:08"),
        "15-09-2026": ("04:43", "05:58", "12:23", "16:44", "18:38", "19:49"),
        "15-10-2026": ("05:16", "06:29", "12:14", "16:00", "17:48", "18:57"),
        "15-12-2026": ("06:16", "07:36", "12:23", "15:14", "17:00", "18:16"),
    }

    def minutes(value):
        hour, minute = map(int, value.split(":"))
        return hour * 60 + minute

    assert references.keys() == custom.keys()
    assert all(
        abs(minutes(actual) - minutes(expected)) <= 1
        for day in references
        for actual, expected in zip(custom[day], references[day])
    )


def test_news_uses_configured_sources_without_uza_and_deduplicates(monkeypatch):
    config = external_data._load_news_config()
    assert set(config["default_sources"]) == {
        "kun",
        "un_news_ru",
        "dw_ru",
        "euronews_ru",
    }
    assert all("uza.uz" not in item["url"] for item in config["sources"])
    first = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item><title>Calm local fact</title>
    <description>&lt;p&gt;Detail   sentence.&lt;/p&gt;</description>
    <link>https://kun.uz/ru/posts/1</link><pubDate>Sun, 26 Jul 2026 08:00:00 +0500</pubDate>
    </item></channel></rss>"""
    other = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
    <item><title>Calm local fact</title><link>https://kun.uz/ru/news/1</link></item>
    <item><title>Second local fact</title><link>https://kun.uz/ru/news/2</link></item>
    </channel></rss>"""

    def fake_get(url):
        return first if "kun.uz" in url else other

    monkeypatch.setattr(external_data, "_http_get", fake_get)
    value = external_data._fetch_news()
    assert value["agreed_sources"] == [
        "Кун.уз",
        "Новости ООН",
        "Дойче Велле",
        "Евроньюс",
    ]
    assert [item["title_ru"] for item in value["candidates"]] == [
        "Calm local fact",
        "Second local fact",
    ]
    assert {item["source"] for item in value["candidates"]} == {
        "Кун.уз",
        "Новости ООН",
    }
    assert value["source_errors"] == []
    # Stage 6.1: описание нужно, чтобы Мариям могла предложить «батафсил айтайми?»
    assert value["candidates"][0]["summary_ru"] == "Detail sentence."
    assert value["candidates"][1]["summary_ru"] == ""
    assert "summary_ru" in value["selection_note"]


def test_news_rdf_and_middle_east_topic_filter(monkeypatch):
    rdf = """<?xml version="1.0" encoding="UTF-8"?>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
             xmlns="http://purl.org/rss/1.0/">
      <item><title>Иран ва АҚШ музокаралари</title>
        <link>https://example.test/iran</link></item>
      <item><title>Европада об-ҳаво</title>
        <link>https://example.test/weather</link></item>
    </rdf:RDF>""".encode("utf-8")
    monkeypatch.setattr(external_data, "_http_get", lambda _url: rdf)
    value = external_data._fetch_news(["dw_ru"], "middle_east")
    assert value["selected_sources"] == ["dw_ru"]
    assert value["selected_topic"] == "middle_east"
    assert [item["title_ru"] for item in value["candidates"]] == [
        "Иран ва АҚШ музокаралари"
    ]


def test_daily_life_cron_prompts_are_narrow_read_only_and_cyrillic():
    expected = {
        "06_morning.md": (
            "get_tashkent_weather",
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
        if filename != "06_morning.md":
            assert "user_id=0" in text
        assert "битта" in text.casefold()
    morning = (CRON / "06_morning.md").read_text(encoding="utf-8")
    assert "соат 08:00" in morning
    assert "get_tashkent_prayer_times" not in morning
    assert "get_recurring_obligations" not in morning
    assert "1–2 та" in morning


def test_one_shot_contract_is_untrusted_plain_text():
    soul = (
        REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "SOUL.md"
    ).read_text(encoding="utf-8")
    assert "one-shot" in soul
    assert "untrusted" in soul
    assert "user-scoped" in soul
    assert "чистый текст" in soul
    assert "cronjob" in soul
