"""Read-only Stage 6 external data with a daily, honest stale fallback.

The backend only fetches, validates, caches and returns source facts.  It does
not write prose or decide what Mariyam should say.
"""
from __future__ import annotations

import asyncio
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .config import TASHKENT

CACHE_VERSION = 1
MAX_RESPONSE_BYTES = 2_000_000
HTTP_TIMEOUT_SECONDS = 12
MAX_REDIRECTS = 5
# News is the only external read that is not day-scoped: RSS is public, free
# and updates through the day (Euronews itself advertises <ttl>30</ttl>).
# Weather and prayer times keep the daily contract (imp09 §1a).
NEWS_CACHE_TTL_SECONDS = 30 * 60
_FETCH_LOCKS: dict = {}
NEWS_SELECTION_NOTE = (
    "Hermes must choose 1–2 calm items close to Oyijon's interests, "
    "paraphrase them in Uzbek Cyrillic with the supplied Cyrillic "
    "source names, avoid panic and graphic details, offer details "
    "from summary_ru only on request, and never invent facts."
)
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


def _within_ttl(iso_value: str, now: datetime, ttl_seconds: int) -> bool:
    """Freshness by elapsed time — used by news only (imp09)."""
    try:
        fetched = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        if fetched.tzinfo is None:
            return False
        age = (now - fetched).total_seconds()
        return 0 <= age < ttl_seconds
    except (AttributeError, TypeError, ValueError):
        return False


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


def _public_https_target(url: str) -> tuple[object, list[str]]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ExternalDataError("feed URL must use https")
    if parsed.port not in (None, 443):
        raise ExternalDataError("feed URL must use the standard https port")
    try:
        addresses = sorted(
            {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
        )
    except socket.gaierror as exc:
        raise ExternalDataError("feed host could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise ExternalDataError("feed host resolves to a non-public address")
    return parsed, addresses


def _https_get_pinned(url: str, parsed, address: str) -> tuple[int, dict[str, str], bytes]:
    """HTTPS request pinned to the address that passed validation (anti-rebinding)."""
    sock = socket.create_connection((address, 443), timeout=HTTP_TIMEOUT_SECONDS)
    try:
        tls = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
        request_path = parsed.path or "/"
        if parsed.query:
            request_path += "?" + parsed.query
        headers = (
            f"GET {request_path} HTTP/1.1\r\nHost: {parsed.hostname}\r\n"
            "Accept: application/rss+xml, application/atom+xml, application/xml, text/xml\r\n"
            "User-Agent: Hermes-Mariyam/1.0 (+private daily-life assistant)\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        tls.sendall(headers)
        response = http.client.HTTPResponse(tls)
        response.begin()
        length = response.getheader("Content-Length")
        if length and int(length) > MAX_RESPONSE_BYTES:
            raise ExternalDataError("feed response is too large")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        return response.status, {key.casefold(): value for key, value in response.getheaders()}, payload
    except ExternalDataError:
        raise
    except Exception as exc:
        raise ExternalDataError(f"feed request failed: {type(exc).__name__}") from exc
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _safe_feed_get(url: str) -> bytes:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        parsed, addresses = _public_https_target(current)
        # The connection is pinned to a prevalidated address, so a second DNS
        # answer cannot redirect the socket to a private target.
        status, headers, payload = _https_get_pinned(current, parsed, addresses[0])
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ExternalDataError("feed response is too large")
        if status in (301, 302, 303, 307, 308):
            location = headers.get("location")
            if not location:
                raise ExternalDataError("feed redirect has no destination")
            current = urljoin(current, location)
            continue
        if not 200 <= status < 300:
            raise ExternalDataError("feed server returned an error")
        return payload
    raise ExternalDataError("feed has too many redirects")


def validate_user_news_feed(url: str, display_name: str, topics: list[str] | None) -> bytes:
    if not isinstance(url, str):
        raise ExternalDataError("feed URL is required")
    if not isinstance(display_name, str) or not 1 <= len(display_name.strip()) <= 120:
        raise ExternalDataError("feed name is required")
    if re.search(r"[A-Za-z]", display_name) or not re.search(r"[\u0400-\u04ff]", display_name):
        raise ExternalDataError("feed name must be in Uzbek Cyrillic")
    if topics is not None and (
        not isinstance(topics, list) or len(topics) > 10
        or any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 80 for item in topics)
    ):
        raise ExternalDataError("topics must be a short list")
    payload = _safe_feed_get(url)
    _parse_feed(payload, "validation", display_name.strip())
    return payload


def generated_news_source_key(user_id: int, url: str) -> str:
    digest = hashlib.sha256(f"{user_id}\0{url}".encode("utf-8")).hexdigest()[:20]
    return f"custom_{digest}"


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
        raise ExternalDataError("prayer timing is missing")
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?:\s+\([^)]*\))?\s*", value)
    if not match:
        raise ExternalDataError("prayer timing has invalid format")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ExternalDataError("prayer timing is out of range")
    return f"{hour:02d}:{minute:02d}"


def _fetch_prayer_times() -> dict:
    # Fatvo.uz's published Tashkent calendar uses 15.5-degree dawn/night
    # angles plus fixed ihtiyot (precaution) minute adjustments.  Aladhan's
    # custom method keeps the calculation and Hijri date in one JSON request.
    query = urlencode(
        {
            "city": "Tashkent",
            "country": "Uzbekistan",
            "method": 99,
            "school": 1,
            "methodSettings": "15.5,null,15.5",
            # Imsak,Fajr,Sunrise,Dhuhr,Asr,Maghrib,Sunset,Isha,Midnight.
            "tune": "0,0,-5,5,0,5,0,-4,0",
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
    hijri = date_data.get("hijri") if isinstance(date_data.get("hijri"), dict) else {}
    hijri_month = hijri.get("month") if isinstance(hijri.get("month"), dict) else {}
    hijri_months_uz = (
        "МУҲАРРАМ",
        "САФАР",
        "РАБИЪУЛ АВВАЛ",
        "РАБИЪУС СОНИЙ",
        "ЖУМОДУЛ АВВАЛ",
        "ЖУМОДУС СОНИЙ",
        "РАЖАБ",
        "ШАЪБОН",
        "РАМАЗОН",
        "ШАВВОЛ",
        "ЗУЛҚАЪДА",
        "ЗУЛҲИЖЖА",
    )
    try:
        hijri_day = str(int(hijri["day"]))
        hijri_year = str(int(hijri["year"]))
        hijri_month_number = int(hijri_month["number"])
        hijri_month_uz = hijri_months_uz[hijri_month_number - 1]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ExternalDataError("Aladhan Hijri date is incomplete") from exc
    return {
        "city": "Tashkent",
        "date": gregorian.get("date"),
        "fajr": _clean_prayer_time(timings.get("Fajr")),
        "sunrise": _clean_prayer_time(timings.get("Sunrise")),
        "dhuhr": _clean_prayer_time(timings.get("Dhuhr")),
        "asr": _clean_prayer_time(timings.get("Asr")),
        "maghrib": _clean_prayer_time(timings.get("Maghrib")),
        "isha": _clean_prayer_time(timings.get("Isha")),
        "hijri_date": hijri.get("date"),
        "hijri_day": hijri_day,
        "hijri_month": hijri_month_number,
        "hijri_month_uz": hijri_month_uz,
        "hijri_year": hijri_year,
        "hijri_display_uz": f"{hijri_day} {hijri_month_uz} ({hijri_year})",
        "school": "Hanafi",
        "calculation_method": "Custom Uzbekistan: 15.5°/15.5° + Fatvo.uz ihtiyot",
        "source": "Aladhan (custom settings matched to Fatvo.uz)",
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
    # ``None`` means "the configured defaults"; an explicit empty list means the
    # owner switched every default off (imp09) and only custom feeds remain.
    requested_sources = (
        list(config["default_sources"]) if source_keys is None else list(source_keys)
    )
    if source_keys == []:
        return {
            "agreed_sources": [],
            "selected_sources": [],
            "selected_topic": topic_key or config["default_topic"],
            "available_sources": [],
            "available_topics": [
                {"key": key, "name": item["name"]} for key, item in config["topics"].items()
            ],
            "candidates": [],
            "source_errors": [],
            "selection_note": NEWS_SELECTION_NOTE,
        }
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
        "selection_note": NEWS_SELECTION_NOTE,
    }


def _cache_entry_is_fresh(entry, now: datetime, ttl_seconds: int | None) -> bool:
    if not (isinstance(entry, dict) and isinstance(entry.get("data"), dict)):
        return False
    if ttl_seconds is None:
        return _same_tashkent_day(entry.get("fetched_at"), now)
    return _within_ttl(entry.get("fetched_at"), now, ttl_seconds)


def _entry_lock(cache_key: str):
    """One in-process lock per cache key, so a single fetch serves all waiters.

    Best-effort: if no running loop owns a usable lock (different loop, exotic
    runtime) the caller simply fetches without coordination, exactly like
    before (imp09).
    """
    try:
        with _CACHE_LOCK:
            lock = _FETCH_LOCKS.get(cache_key)
            if lock is None:
                lock = asyncio.Lock()
                _FETCH_LOCKS[cache_key] = lock
            return lock
    except RuntimeError:
        return None


async def _daily_cached(cache_key: str, fetcher, *, ttl_seconds: int | None = None) -> dict:
    """Cached external read. Day-scoped by default; news passes an explicit TTL."""
    now = _now_utc()
    with _CACHE_LOCK:
        cache = _read_cache()
        entry = cache["entries"].get(cache_key)
        if _cache_entry_is_fresh(entry, now, ttl_seconds):
            return {
                "ok": True,
                **entry["data"],
                "cache": {"hit": True, "stale": False, "fetched_at": entry["fetched_at"]},
            }

    lock = _entry_lock(cache_key)
    if lock is not None:
        async with lock:
            # Another waiter may have refreshed this key while we queued.
            now = _now_utc()
            with _CACHE_LOCK:
                cache = _read_cache()
                entry = cache["entries"].get(cache_key)
                if _cache_entry_is_fresh(entry, now, ttl_seconds):
                    return {
                        "ok": True,
                        **entry["data"],
                        "cache": {
                            "hit": True, "stale": False, "fetched_at": entry["fetched_at"],
                        },
                    }
            return await _fetch_and_store(cache_key, fetcher, now)
    return await _fetch_and_store(cache_key, fetcher, now)


async def _fetch_and_store(cache_key: str, fetcher, now: datetime) -> dict:
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


def user_news_cache_key(user_id: int) -> str:
    return f"news_user:{user_id}"


def default_news_sources() -> list[dict]:
    """Feeds shipped in news_sources.json, in configured order."""
    config = _load_news_config()
    return [
        {
            "source_key": key,
            "display_name": config["sources_by_key"][key]["name"],
            "url": config["sources_by_key"][key]["url"],
        }
        for key in config["default_sources"]
    ]


def invalidate_user_news_cache(user_id: int) -> bool:
    """Drop this owner's daily news bundle so the next read refetches it.

    Called only when the owner changes their own feed set (imp09): the daily
    bundle was assembled before the change and would otherwise keep the new
    feed invisible until tomorrow. Weather and prayer caches are separate keys
    and stay untouched. Returns True when an entry was actually removed.
    """
    key = user_news_cache_key(user_id)
    with _CACHE_LOCK:
        cache = _read_cache()
        if key not in cache["entries"]:
            return False
        del cache["entries"][key]
        try:
            _write_cache(cache)
        except OSError:
            # Failing to persist the removal only costs one stale read; the
            # caller must not lose the successful feed change over it.
            return False
    return True


async def get_tashkent_weather() -> dict:
    return await _daily_cached("weather_tashkent", _fetch_weather)


async def get_tashkent_prayer_times() -> dict:
    return await _daily_cached("prayer_tashkent_fatvo_v1", _fetch_prayer_times)


async def get_daily_news(
    pool=None,
    user_id: int | None = None,
    topic: str | None = None,
    sources: list[str] | None = None,
) -> dict:
    # Backward-compatible defaults-only path used by offline unit tests.
    if pool is None or user_id is None:
        selected_sources = sources or []
        cache_key = "news:" + json.dumps(
            {"topic": topic, "sources": selected_sources}, sort_keys=True, separators=(",", ":")
        )
        return await _daily_cached(
            cache_key,
            lambda: _fetch_news(selected_sources or None, topic),
            ttl_seconds=NEWS_CACHE_TTL_SECONDS,
        )

    from . import db
    custom_sources = await db.get_active_news_sources(pool, user_id)
    # Defaults the owner switched off keep a disabled row in the same table
    # (imp09); news_sources.json and other users are unaffected.
    disabled_defaults = await db.get_disabled_default_keys(pool, user_id)
    enabled_defaults = [
        item["source_key"] for item in default_news_sources()
        if item["source_key"] not in disabled_defaults
    ]

    def fetch_all() -> dict:
        base = _fetch_news(enabled_defaults, "daily")
        all_candidates = list(base["candidates"])
        errors = list(base["source_errors"])
        for source in custom_sources:
            try:
                items = _parse_feed(
                    _safe_feed_get(source["url"]), source["source_key"], source["display_name"]
                )
                for item in items:
                    item["topics"] = source["topics"]
                all_candidates.extend(items)
            except ExternalDataError:
                errors.append(source["display_name"])
        base["candidates"] = all_candidates
        base["source_errors"] = errors
        base["available_sources"].extend(
            {"key": item["source_key"], "name": item["display_name"], "custom": True}
            for item in custom_sources
        )
        return base

    # One cache key per owner: source/topic selections only filter the daily
    # bundle in memory and therefore cannot multiply upstream requests.
    result = await _daily_cached(
        user_news_cache_key(user_id), fetch_all, ttl_seconds=NEWS_CACHE_TTL_SECONDS
    )
    if not result.get("ok"):
        return result
    available_keys = {item["key"] for item in result["available_sources"]}
    selected = sources or [item["key"] for item in result["available_sources"]]
    if not isinstance(selected, list) or not selected or len(selected) > len(available_keys) or (
        len(set(selected)) != len(selected) or any(key not in available_keys for key in selected)
    ):
        return {
            "ok": False,
            "error_code": "INVALID_NEWS_SELECTION",
            "message_ru": "Выбран неизвестный или отключённый источник новостей",
            "message_uz": "Номаълум ёки ўчирилган хабар манбаси танланди",
            "cache": result.get("cache"),
        }
    candidates = [item for item in result["candidates"] if item["source_key"] in selected]
    config = _load_news_config()
    selected_topic = topic or config["default_topic"]
    if selected_topic in config["topics"]:
        keywords = [word.casefold() for word in config["topics"][selected_topic]["keywords"]]
        if keywords:
            candidates = [
                item for item in candidates
                if any(word in f"{item['title_ru']} {item['summary_ru']}".casefold() for word in keywords)
            ]
    else:
        needle = selected_topic.strip().casefold()
        candidates = [
            item for item in candidates
            if needle in [value.casefold() for value in item.get("topics", [])]
        ]
    result["selected_sources"] = selected
    result["selected_topic"] = selected_topic
    result["candidates"] = candidates[:20]
    return result
