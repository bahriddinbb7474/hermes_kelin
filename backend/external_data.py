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
NEWS_FEEDS = (
    ("uza", "UzA", "https://uza.uz/ru/rss"),
    ("kun", "Kun.uz", "https://kun.uz/ru/rss"),
)

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


def _parse_feed(payload: bytes, source_key: str, source_name: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ExternalDataError(f"{source_name} returned invalid RSS") from exc
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{*}entry")
    parsed: list[dict] = []
    for item in items[:20]:
        title = unescape(_text(item, "title") or _text(item, "{*}title"))
        link = _text(item, "link")
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
        parsed.append(
            {
                "source_key": source_key,
                "source": source_name,
                "title_ru": title[:500],
                "url": link,
                "published_at": published_at,
            }
        )
    if not parsed:
        raise ExternalDataError(f"{source_name} RSS has no usable items")
    return parsed


def _fetch_news() -> dict:
    candidates: list[dict] = []
    source_errors: list[str] = []
    for source_key, source_name, url in NEWS_FEEDS:
        try:
            candidates.extend(_parse_feed(_http_get(url), source_key, source_name))
        except ExternalDataError:
            source_errors.append(source_name)
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
    return {
        "agreed_sources": ["UzA", "Kun.uz"],
        "candidates": unique[:12],
        "source_errors": source_errors,
        "selection_note": (
            "Hermes must choose 3–5 calm Uzbekistan items, paraphrase them in "
            "Uzbek Cyrillic, and keep source attribution. Do not invent facts."
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


async def get_daily_news() -> dict:
    return await _daily_cached("news_uza_kun", _fetch_news)
