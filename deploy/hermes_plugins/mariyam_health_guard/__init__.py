"""Deterministic Stage 7 health-alert guard for the Mariyam profile.

Detection happens in Hermes' ``pre_gateway_dispatch`` hook, before the LLM.
The backend remains storage-only and never receives arbitrary inbound messages:
only an already-detected, trusted Oyijon alert is persisted by the narrow
profile writer. Delivery uses the active Telegram adapter, independently of the
model provider.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import stat
import time
import unicodedata
from pathlib import Path


LOG = logging.getLogger("mariyam_health_guard")
MCP_PREFIX = "mcp__mariyam_backend__"
ALERT_TOOL = "save_alert_event"
STATE_FILE = "health_alert_guard.sqlite3"
MAX_TEXT_CHARS = 1000
MAX_MAPPING_BYTES = 64 * 1024

SOFT_REPLY = (
    "Ойижон, бу жиддий бўлиши мумкин. Илтимос, яқинларингизга айтинг ва "
    "тиббий ёрдамга мурожаат қилинг. Мен Ўғлингизга ҳам хабар бераман."
)
REWRITE_PREFIX = (
    "[MARIYAM_HEALTH_GUARD_RECORDED: keyword-предохранитель алертни ёзди ва "
    "Бахриддин акага хабар беришни бошлади. Техник белгини тилга олманг. "
    "save_alert_event ни қайта чақирманг ва админга иккинчи хабар юборманг. "
    "Ойижонга фақат §10.2 даги юмшоқ жавобни беринг.]\n"
)

# Narrow multi-word patterns. No standalone ёмон/ёрдам/дард/бемор/температура.
KEYWORD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "heart_pain",
        re.compile(r"\b(?:юрагим|юрак(?:\s+томоним)?)(?:\s+\S+){0,3}\s+оғри"),
    ),
    (
        "chest_pain",
        re.compile(
            # OpenAI STT consistently renders the synthetic Khorezm-accented
            # ``ko'kragim`` as ``какрагим``/``кокрагим``. Keep the expansion
            # narrow: the same token must still be followed by an оғр root.
            r"\b(?:кўкрагим|какрагим|кокрагим|кўксим|кўкрак\s+томоним)"
            r"(?:\s+\S+){0,3}\s+оғр"
        ),
    ),
    (
        "breathing_difficulty",
        re.compile(
            r"\b(?:нафас\s+ол(?:иш(?:им)?\s+(?:қийин|қийн|оғир)|олма)"
            r"|нафасим\s+қис|ҳаво\s+етмаяп|зўрға\s+нафас\s+ол)"
        ),
    ),
    ("dizziness", re.compile(r"\bбошим(?:\s+\S+){0,2}\s+айлан")),
    (
        "feeling_very_bad",
        re.compile(
            r"\b(?:ёмон\s+бўл|аҳволим\s+ёмон\s+бўл"
            r"|ўзимни\s+ёмон\s+ҳис)"
        ),
    ),
    (
        "fainting",
        re.compile(r"\b(?:ҳушим\s+кет|ҳушимни\s+йўқот|ҳушдан\s+кет)"),
    ),
    (
        "high_blood_pressure",
        re.compile(
            r"\b(?:қон\s+босим(?:им)?(?:\s+\S+){0,3}\s+"
            r"(?:баланд|юқори|кўтар)"
            r"|босимим(?:\s+\S+){0,3}\s+(?:баланд|юқори|кўтар)"
            r"|давлен\w*(?:\s+\S+){0,3}\s+(?:баланд|юқори|кўтар))"
        ),
    ),
)

_TASKS: set[asyncio.Task] = set()
_LAST_GATEWAY = None


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFC", text).lower().replace("’", "ʻ")
    value = re.sub(r"[^\w\sʻ-]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def detect_health_keyword(text: str) -> str | None:
    """Return the matched trigger id, or None for non-alert text."""
    if not isinstance(text, str) or not text or len(text) > MAX_TEXT_CHARS:
        return None
    normalized = _normalize(text)
    for trigger, pattern in KEYWORD_PATTERNS:
        if pattern.search(normalized):
            return trigger
    return None


def _mask(value: object) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return digest[:10]


def _mapping_path() -> Path | None:
    raw = os.environ.get("MARIYAM_IDENTITY_MAP_FILE")
    return Path(raw) if raw else None


def _load_mapping() -> dict | None:
    path = _mapping_path()
    if path is None or not path.is_absolute():
        return None
    try:
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None
        if os.name == "posix" and stat.S_IMODE(info.st_mode) != 0o600:
            return None
        if info.st_size > MAX_MAPPING_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data:
        return None
    for telegram_id, entry in data.items():
        if (
            not isinstance(telegram_id, str)
            or not telegram_id.isdigit()
            or not isinstance(entry, dict)
            or entry.get("role") not in {"admin", "oyijon"}
            or not isinstance(entry.get("user_id"), int)
            or isinstance(entry.get("user_id"), bool)
            or entry["user_id"] <= 0
        ):
            return None
    return data


def _trusted_route(event) -> tuple[int, str] | None:
    source = getattr(event, "source", None)
    platform = getattr(getattr(source, "platform", None), "value", None)
    sender = str(getattr(source, "user_id", "") or "")
    if platform != "telegram" or not sender.isdigit():
        return None
    mapping = _load_mapping()
    if mapping is None:
        return None
    actor = mapping.get(sender)
    if not isinstance(actor, dict) or actor.get("role") != "oyijon":
        return None
    admins = [
        telegram_id
        for telegram_id, entry in mapping.items()
        if entry.get("role") == "admin"
    ]
    if len(admins) != 1:
        return None
    return actor["user_id"], admins[0]


def _state_path() -> Path:
    home = os.environ.get("HERMES_HOME")
    if not home:
        raise RuntimeError("HERMES_HOME is missing")
    return Path(home) / STATE_FILE


def _event_key(event, text: str) -> str:
    source = event.source
    material = "\0".join(
        (
            str(getattr(getattr(source, "platform", None), "value", "")),
            str(getattr(source, "user_id", "") or ""),
            str(getattr(event, "message_id", "") or ""),
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _claim_event(key: str, trigger: str) -> bool:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   event_key TEXT PRIMARY KEY,
                   trigger TEXT NOT NULL,
                   created_at REAL NOT NULL,
                   notified INTEGER NOT NULL DEFAULT 0,
                   recorded INTEGER NOT NULL DEFAULT 0,
                   last_error TEXT
               )"""
        )
        cursor = conn.execute(
            "INSERT OR IGNORE INTO events(event_key, trigger, created_at) "
            "VALUES (?, ?, ?)",
            (key, trigger, time.time()),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()
        if os.name == "posix":
            os.chmod(path, 0o600)


def _update_event(
    key: str, *, notified: bool | None = None, recorded: bool | None = None,
    error: str | None = None,
) -> None:
    assignments = ["last_error=?"]
    values: list[object] = [error]
    if notified is not None:
        assignments.append("notified=?")
        values.append(int(notified))
    if recorded is not None:
        assignments.append("recorded=?")
        values.append(int(recorded))
    values.append(key)
    with sqlite3.connect(_state_path(), timeout=5) as conn:
        conn.execute(
            f"UPDATE events SET {', '.join(assignments)} WHERE event_key=?",
            values,
        )


def _schedule(coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except Exception:
        LOG.error("health_guard could not schedule deterministic dispatch")
        return
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def _send_admin(gateway, admin_chat_id: str, source_text: str) -> bool:
    try:
        source_platform = next(
            platform
            for platform in gateway.adapters
            if getattr(platform, "value", None) == "telegram"
        )
        adapter = gateway.adapters[source_platform]
    except Exception:
        return False
    message = (
        "Бахриддин ака, муҳим хабар: Ойижон «"
        + source_text[:MAX_TEXT_CHARS]
        + "» деди. Мен унга яқинларига айтишни ва тиббий ёрдамга "
        "мурожаат қилишни айтдим."
    )
    for delay in (0, 1, 3):
        if delay:
            await asyncio.sleep(delay)
        try:
            await adapter.send(str(admin_chat_id), message)
            return True
        except Exception:
            continue
    return False


def _writer_paths() -> tuple[str, str] | None:
    python_path = os.environ.get("MARIYAM_HEALTH_ALERT_PYTHON", "")
    script_path = os.environ.get("MARIYAM_HEALTH_ALERT_SCRIPT", "")
    if not python_path or not script_path:
        return None
    python = Path(python_path)
    script = Path(script_path)
    if (
        not python.is_absolute()
        or not script.is_absolute()
        or not python.is_file()
        or not script.is_file()
        or script.is_symlink()
    ):
        return None
    return str(python), str(script)


async def _record_keyword_alert(
    user_id: int, source_text: str, sent_to_admin: bool,
) -> bool:
    paths = _writer_paths()
    if paths is None:
        return False
    payload = json.dumps(
        {
            "user_id": user_id,
            "source_text": source_text[:MAX_TEXT_CHARS],
            "bot_response": SOFT_REPLY,
            "sent_to_admin": sent_to_admin,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    for delay in (0, 1, 3):
        if delay:
            await asyncio.sleep(delay)
        try:
            proc = await asyncio.create_subprocess_exec(
                paths[0],
                paths[1],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(payload), timeout=20
            )
            if proc.returncode == 0 and stdout.strip() == b"ALERT_RECORDED":
                return True
        except Exception:
            continue
    return False


async def _dispatch_keyword(
    gateway, event_key: str, user_id: int, admin_chat_id: str, source_text: str,
) -> None:
    notified = await _send_admin(gateway, admin_chat_id, source_text)
    _update_event(
        event_key,
        notified=notified,
        error=None if notified else "ADMIN_DELIVERY_FAILED",
    )
    recorded = await _record_keyword_alert(user_id, source_text, notified)
    _update_event(
        event_key,
        recorded=recorded,
        error=None if recorded else "ALERT_PERSIST_FAILED",
    )
    LOG.info(
        "health_guard dispatch event=%s notified=%s recorded=%s",
        _mask(event_key),
        notified,
        recorded,
    )


def on_pre_gateway_dispatch(**kwargs):
    """Detect trusted Oyijon keyword alerts before auth and LLM dispatch."""
    global _LAST_GATEWAY
    event = kwargs.get("event")
    gateway = kwargs.get("gateway")
    _LAST_GATEWAY = gateway
    text = getattr(event, "text", None)
    trigger = detect_health_keyword(text)
    if trigger is None:
        return None
    route = _trusted_route(event)
    if route is None:
        return None
    key = _event_key(event, text)
    try:
        claimed = _claim_event(key, trigger)
    except Exception:
        LOG.error("health_guard state claim failed; normal dispatch preserved")
        return None
    if claimed:
        _schedule(_dispatch_keyword(gateway, key, route[0], route[1], text))
    return {"action": "rewrite", "text": REWRITE_PREFIX + text}


def _canonical_tool_name(name):
    if isinstance(name, str) and name.startswith(MCP_PREFIX):
        return name[len(MCP_PREFIX):]
    return name


def _is_success(result) -> bool:
    if isinstance(result, dict):
        return result.get("ok") is True
    if isinstance(result, str):
        try:
            return json.loads(result).get("ok") is True
        except Exception:
            return '"ok": true' in result.lower()
    if isinstance(result, list) and result:
        text = getattr(result[0], "text", None)
        return _is_success(text)
    return False


async def _notify_llm_alert(source_text: str) -> None:
    mapping = _load_mapping()
    if mapping is None or _LAST_GATEWAY is None:
        return
    admins = [
        telegram_id
        for telegram_id, entry in mapping.items()
        if entry.get("role") == "admin"
    ]
    if len(admins) != 1:
        return
    await _send_admin(_LAST_GATEWAY, admins[0], source_text)


def on_tool_execution_middleware(**kwargs):
    """Supply independent admin delivery after a successful LLM alert save."""
    args = kwargs.get("args")
    next_call = kwargs.get("next_call")
    if not isinstance(args, dict) or not callable(next_call):
        return json.dumps({"ok": False, "error_code": "HEALTH_GUARD_ERROR"})
    result = next_call(args)
    if (
        _canonical_tool_name(kwargs.get("tool_name")) == ALERT_TOOL
        and _is_success(result)
        and isinstance(args.get("source_text"), str)
        and args.get("sent_to_admin") is True
    ):
        _schedule(_notify_llm_alert(args["source_text"][:MAX_TEXT_CHARS]))
    return result


def register(ctx) -> None:
    ctx.register_hook("pre_gateway_dispatch", on_pre_gateway_dispatch)
    ctx.register_middleware("tool_execution", on_tool_execution_middleware)
