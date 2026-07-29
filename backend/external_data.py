"""Read-only Stage 6 external data with a daily, honest stale fallback.

The backend only fetches, validates, caches and returns source facts.  It does
not write prose or decide what Mariyam should say.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .config import TASHKENT

CACHE_VERSION = 1
MAX_RESPONSE_BYTES = 2_000_000
HTTP_TIMEOUT_SECONDS = 12
DEFAULT_CACHE_PATH = Path("/opt/hermes-mariyam/var/external-data-cache.json")
DEFAULT_NEWS_CONFIG_PATH = Path(__file__).with_name("news_sources.json")

_CACHE_LOCK = threading.Lock()


class ExternalDataError(RuntimeError):
    """A safe upstream/config/validation failure."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cache_path() -> Path:
    configured = os.environ.get("MARIYAM_EXTERNAL_CACHE_FILE")
    if configured:
        return Path(configured)
    if DEFAULT_CACHE_PATH.parent.is_dir():
        return DEFAULT_CACHE_PATH
    return Path(tempfile.gettempdir()) / "mariyam-external-data-cache.json"


def _read_cache() -> dict:
    path = _cache_path()
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_RESPONSE_BYTES:
            return {"version": CACHE_VERSION, "entries": {}}
        value = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("version") != CACHE_VERSION
            or not isinstance(value.get("entries"), dict)
        ):
            raise ValueError("invalid cache schema")
        return value
    except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return {"version": CACHE_VERSION, "entries": {}}


def _write_cache(cache: dict) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(cache, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(temp_path, "wb") as handle:
            os.chmod(temp_path, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _same_tashkent_day(iso_value: str, now: datetime) -> bool:
    try:
        fetched = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        if fetched.tzinfo is None:
            return False
        return fetched.astimezone(TASHKENT).date() == now.astimezone(TASHKENT).date()
    except (AttributeError, TypeError, ValueError):
        return False


def _http_get(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json, application/rss+xml, application/xml, text/xml",
            "User-Agent": "Hermes-Mariyam/1.0 (+private daily-life assistant)",
        },
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except Exception as exc:
        raise ExternalDataError(f"upstream request failed: {type(exc).__name__}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ExternalDataError("upstream response too large")
    return payload


def _json_get(url: str) -> dict:
    try:
        value = json.loads(_http_get(url).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalDataError("upstream returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ExternalDataError("upstream returned invalid JSON shape")
    return value


def _number(value, field: str) -> float:
    if isinstance(value, bool):
        raise ExternalDataError(f"invalid {field}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ExternalDataError(f"invalid {field}") from exc
    if not -1000 < result < 1000:
        raise ExternalDataError(f"invalid {field}")
    return round(result, 1)


def _fetch_weather() -> dict:
    api_key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        raise ExternalDataError("OPENWEATHER_API_KEY is not configured")
    query = urlencode(
        {
            "q": "Tashkent,UZ",
            "appid": api_key,
            "units": "metric",
            "lang": "ru",
        }
    )
    value = _json_get(f"https://api.openweathermap.org/data/2.5/weather?{query}")
    if value.get("cod") not in (None, 200, "200"):
        raise ExternalDataError("OpenWeather rejected the request")
    main = value.get("main")
    weather = value.get("weather")
    wind = value.get("wind") or {}
    if not isinstance(main, dict) or not isinstance(weather, list) or not weather:
        raise ExternalDataError("OpenWeather response is incomplete")
    description = weather[0].get("description") if isinstance(weather[0], dict) else None
    if not isinstance(description, str) or not description.strip():
        raise ExternalDataError("OpenWeather condition is missing")
    observed = value.get("dt")
    observed_at = None
    if isinstance(observed, int) and not isinstance(observed, bool):
        observed_at = datetime.fromtimestamp(observed, timezone.utc).isoformat()
    return {
        "city": "Tashkent",
        "temperature_c": _number(main.get("temp"), "temperature"),
        "feels_like_c": _number(main.get("feels_like"), "feels_like"),
        "condition_ru": description.strip(),
        "humidity_percent": int(_number(main.get("humidity"), "humidity")),
        "wind_m_s": _number(wind.get("speed", 0), "wind"),
        "observed_at": observed_at,
        "source": "OpenWeather",
        "source_url": "https://openweathermap.org/city/1512569",
    }


def _clean_prayer_time(value) -> str:
    if not isinstance(value, str):
        raise ExternalDataError("Aladhan timing is missing")
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?:\s+\([^)]*\))?\s*", value)
    if not match:
        raise ExternalDataError("Aladhan timing has invalid format")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ExternalDataError("Aladhan timing is out of range")
    return f"{hour:02d}:{minute:02d}"


def _fetch_prayer_times() -> dict:
    query = urlencode(
        {
            "city": "Tashkent",
            "country": "Uzbekistan",
            "method": 3,
            "school": 1,
        }
    )
    value = _json_get(f"https://api.aladhan.com/v1/timingsByCity?{query}")
    if value.get("code") != 200:
        raise ExternalDataError("Aladhan rejected the request")
    data = value.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("timings"), dict):
        raise ExternalDataError("Aladhan response is incomplete")
    timings = data["timings"]
    date_data = data.get("date") if isinstance(data.get("date"), dict) else {}
    gregorian = (
        date_data.get("gregorian")
        if isinstance(date_data.get("gregorian"), dict)
        else {}
    )
    return {
        "city": "Tashkent",
        "date": gregorian.get("date"),
        "fajr": _clean_prayer_time(timings.get("Fajr")),
        "sunrise": _clean_prayer_time(timings.get("Sunrise")),
        "dhuhr": _clean_prayer_time(timings.get("Dhuhr")),
        "asr": _clean_prayer_time(timings.get("Asr")),
        "maghrib": _clean_prayer_time(timings.get("Maghrib")),
        "isha": _clean_prayer_time(timings.get("Isha")),
        "school": "Hanafi",
        "calculation_method": "Muslim World League",
        "source": "Aladhan",
        "source_url": "https://aladhan.com/prayer-times-api",
    }


def _text(element, child_name: str) -> str:
    child = element.find(child_name)
    return (child.text or "").strip() if child is not None else ""


def _plain_text(raw: str) -> str:
    """RSS descriptions carry HTML; store readable plain text only."""
    without_tags = re.sub(r"<[^>]+>", " ", unescape(raw or ""))
    return re.sub(r"\s+", " ", without_tags).strip()


def _news_config_path() -> Path:
    configured = os.environ.get("MARIYAM_NEWS_CONFIG_FILE")
    return Path(configured) if configured else DEFAULT_NEWS_CONFIG_PATH


def _load_news_config() -> dict:
    path = _news_config_path()
    try:
        raw = path.read_bytes()
        if len(raw) > 128 * 1024:
            raise ValueError("news config is too large")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ExternalDataError("news config is unavailable") from exc
    if (
        not isinstance(value, dict)
        or value.get("version") != 1
        or not isinstance(value.get("sources"), list)
        or not isinstance(value.get("topics"), dict)
        or not isinstance(value.get("default_sources"), list)
        or not isinstance(value.get("default_topic"), str)
    ):
        raise ExternalDataError("news config has invalid shape")
    sources: dict[str, dict] = {}
    for item in value["sources"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"key", "name", "url", "enabled"}
            or not isinstance(item["key"], str)
            or not re.fullmatch(r"[a-z0-9_]{2,40}", item["key"])
            or item["key"] in sources
            or not isinstance(item["name"], str)
            or not item["name"].strip()
            or not isinstance(item["url"], str)
            or not item["url"].startswith("https://")
            or not isinstance(item["enabled"], bool)
        ):
            raise ExternalDataError("news config has invalid source")
        sources[item["key"]] = item
    if not sources or any(key not in sources for key in value["default_sources"]):
        raise ExternalDataError("news config has invalid defaults")
    topics: dict[str, dict] = {}
    for key, item in value["topics"].items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[a-z0-9_]{2,40}", key)
            or not isinstance(item, dict)
            or set(item) != {"name", "keywords"}
            or not isinstance(item["name"], str)
            or not item["name"].strip()
            or not isinstance(item["keywords"], list)
            or not all(
                isinstance(keyword, str) and 1 <= len(keyword.strip()) <= 80
                for keyword in item["keywords"]
            )
        ):
            raise ExternalDataError("news config has invalid topic")
        topics[key] = item
    if value["default_topic"] not in topics:
        raise ExternalDataError("news config has invalid default topic")
    return {**value, "sources_by_key": sources, "topics": topics}


def _parse_feed(payload: bytes, source_key: str, source_name: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ExternalDataError(f"{source_name} returned invalid RSS") from exc
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{*}item")
    if not items:
        items = root.findall(".//{*}entry")
    parsed: list[dict] = []
    for item in items[:20]:
        title = unescape(_text(item, "title") or _text(item, "{*}title"))
        link = _text(item, "link") or _text(item, "{*}link")
        if not link:
            link_node = item.find("{*}link")
            if link_node is not None:
                link = (link_node.get("href") or "").strip()
        published = (
            _text(item, "pubDate")
            or _text(item, "{*}published")
            or _text(item, "{*}updated")
        )
        title = re.sub(r"\s+", " ", title).strip()
        if not title or not link.startswith(("https://", "http://")):
            continue
        published_at = published
        if published:
            try:
                published_at = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                try:
                    published_at = datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    ).astimezone(timezone.utc).isoformat()
                except (TypeError, ValueError):
                    published_at = None
        summary = _plain_text(
            _text(item, "description")
            or _text(item, "{*}summary")
            or _text(item, "{*}content")
        )
        parsed.append(
            {
                "source_key": source_key,
                "source": source_name,
                "title_ru": title[:500],
                # Stage 6.1: без текста новости Hermes не может предложить
                # «батафсил айтайми?» — отдаём короткое описание из RSS.
                "summary_ru": summary[:600],
                "url": link,
                "published_at": published_at,
            }
        )
    if not parsed:
        raise ExternalDataError(f"{source_name} RSS has no usable items")
    return parsed


def _fetch_news(
    source_keys: list[str] | None = None,
    topic_key: str | None = None,
) -> dict:
    config = _load_news_config()
    sources_by_key = config["sources_by_key"]
    requested_sources = source_keys or list(config["default_sources"])
    if (
        not isinstance(requested_sources, list)
        or not requested_sources
        or len(requested_sources) > len(sources_by_key)
        or not all(
            isinstance(key, str)
            and key in sources_by_key
            and sources_by_key[key]["enabled"]
            for key in requested_sources
        )
        or len(set(requested_sources)) != len(requested_sources)
    ):
        raise ExternalDataError("unsupported news source selection")
    selected_topic = topic_key or config["default_topic"]
    if selected_topic not in config["topics"]:
        raise ExternalDataError("unsupported news topic")
    by_source: list[list[dict]] = []
    source_errors: list[str] = []
    for source_key in requested_sources:
        source = sources_by_key[source_key]
        source_name = source["name"]
        try:
            by_source.append(
                _parse_feed(_http_get(source["url"]), source_key, source_name)
            )
        except ExternalDataError:
            source_errors.append(source_name)
    candidates = [
        items[index]
        for index in range(max((len(items) for items in by_source), default=0))
        for items in by_source
        if index < len(items)
    ]
    if not candidates:
        raise ExternalDataError("all agreed news sources are unavailable")
    unique: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = re.sub(r"\W+", " ", item["title_ru"].casefold()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item)
    keywords = [
        keyword.casefold() for keyword in config["topics"][selected_topic]["keywords"]
    ]
    if keywords:
        unique = [
            item
            for item in unique
            if any(
                keyword in f"{item['title_ru']} {item['summary_ru']}".casefold()
                for keyword in keywords
            )
        ]
    available_sources = [
        {"key": key, "name": item["name"]}
        for key, item in sources_by_key.items()
        if item["enabled"]
    ]
    available_topics = [
        {"key": key, "name": item["name"]}
        for key, item in config["topics"].items()
    ]
    return {
        "agreed_sources": [sources_by_key[key]["name"] for key in requested_sources],
        "selected_sources": requested_sources,
        "selected_topic": selected_topic,
        "available_sources": available_sources,
        "available_topics": available_topics,
        "candidates": unique[:20],
        "source_errors": source_errors,
        "selection_note": (
            "Hermes must choose 1–2 calm items close to Oyijon's interests, "
            "paraphrase them in Uzbek Cyrillic with the supplied Cyrillic "
            "source names, avoid panic and graphic details, offer details "
            "from summary_ru only on request, and never invent facts."
        ),
    }


async def _daily_cached(cache_key: str, fetcher) -> dict:
    now = _now_utc()
    with _CACHE_LOCK:
        cache = _read_cache()
        entry = cache["entries"].get(cache_key)
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("data"), dict)
            and _same_tashkent_day(entry.get("fetched_at"), now)
        ):
            return {
                "ok": True,
                **entry["data"],
                "cache": {"hit": True, "stale": False, "fetched_at": entry["fetched_at"]},
            }
    try:
        data = await asyncio.to_thread(fetcher)
    except ExternalDataError as exc:
        with _CACHE_LOCK:
            cache = _read_cache()
            stale = cache["entries"].get(cache_key)
        if isinstance(stale, dict) and isinstance(stale.get("data"), dict):
            return {
                "ok": True,
                **stale["data"],
                "cache": {
                    "hit": True,
                    "stale": True,
                    "fetched_at": stale.get("fetched_at"),
                    "note_uz": "Манба ҳозир очилмади. Бу олдинги маълумот.",
                    "note_ru": "Источник сейчас недоступен. Это предыдущие данные.",
                },
            }
        return {
            "ok": False,
            "error_code": "EXTERNAL_DATA_UNAVAILABLE",
            "message_ru": f"Источник данных сейчас недоступен: {exc}",
            "message_uz": "Маълумот манбаси ҳозир очилмади. Маълумотни тахмин қилманг.",
            "cache": {"hit": False, "stale": False, "fetched_at": None},
        }
    fetched_at = now.isoformat()
    with _CACHE_LOCK:
        cache = _read_cache()
        cache["entries"][cache_key] = {"fetched_at": fetched_at, "data": data}
        try:
            _write_cache(cache)
        except OSError:
            # Fresh source facts are still safe to return; the next invocation
            # will refetch instead of pretending they were persisted.
            pass
    return {
        "ok": True,
        **data,
        "cache": {"hit": False, "stale": False, "fetched_at": fetched_at},
    }


async def get_tashkent_weather() -> dict:
    return await _daily_cached("weather_tashkent", _fetch_weather)


async def get_tashkent_prayer_times() -> dict:
    return await _daily_cached("prayer_tashkent_hanafi", _fetch_prayer_times)


async def get_daily_news(
    topic: str | None = None,
    sources: list[str] | None = None,
) -> dict:
    selected_sources = sources or []
    cache_key = "news:" + json.dumps(
        {"topic": topic, "sources": selected_sources},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return await _daily_cached(
        cache_key,
        lambda: _fetch_news(selected_sources or None, topic),
    )
