"""Provider-independent no-agent one-shot reminders for the Mariyam profile."""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path

MAX_MESSAGE_CHARS = 500
MAX_MAPPING_BYTES = 64 * 1024
BLOCKED_MESSAGE_MARKERS = (
    "mcp__",
    "user_id",
    "cronjob",
    "terminal",
    "http://",
    "https://",
    "`",
)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁёЎўҚқҒғҲҳ]")


def _safe_error(code: str) -> str:
    return json.dumps(
        {
            "success": False,
            "error": code,
            "message": "One-shot reminder was not scheduled.",
        }
    )


def _home() -> Path | None:
    raw = os.environ.get("HERMES_HOME")
    path = Path(raw) if raw else None
    return path if path and path.is_absolute() else None


def _regular_private_json(path: Path) -> dict | None:
    try:
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None
        if os.name == "posix" and stat.S_IMODE(info.st_mode) != 0o600:
            return None
        if info.st_size > MAX_MAPPING_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, TypeError, ValueError):
        return None


def _session_telegram_id(session_id: object) -> str | None:
    home = _home()
    if home is None or not isinstance(session_id, str) or not session_id:
        return None
    database = home / "state.db"
    try:
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT origin_json FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        if not row or not row[0]:
            return None
        origin = json.loads(row[0])
        user_id = origin.get("user_id")
        if origin.get("platform") != "telegram":
            return None
        value = str(user_id)
        return value if value.isdigit() else None
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None


def _trusted_oyijon(session_id: object) -> bool:
    telegram_id = _session_telegram_id(session_id)
    raw_mapping = os.environ.get("MARIYAM_IDENTITY_MAP_FILE")
    if telegram_id is None or not raw_mapping:
        return False
    mapping = _regular_private_json(Path(raw_mapping))
    entry = mapping.get(telegram_id) if mapping else None
    return bool(
        isinstance(entry, dict)
        and entry.get("role") == "oyijon"
        and isinstance(entry.get("user_id"), int)
        and not isinstance(entry.get("user_id"), bool)
        and entry["user_id"] > 0
    )


def _is_one_shot(schedule: object) -> bool:
    if not isinstance(schedule, str) or not schedule.strip():
        return False
    try:
        parsed = datetime.fromisoformat(schedule.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    now = datetime.now(timezone.utc)
    delta = parsed.astimezone(timezone.utc) - now
    return 0 < delta.total_seconds() <= 366 * 24 * 3600


def _clean_message(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    message = value.strip()
    lowered = message.lower()
    if (
        not message
        or len(message) > MAX_MESSAGE_CHARS
        or "\n" in message
        or "\r" in message
        or any(ord(char) < 32 for char in message)
        or any(marker in lowered for marker in BLOCKED_MESSAGE_MARKERS)
        or len(CYRILLIC_RE.findall(message)) < 3
    ):
        return None
    return message


def _create_reminder_script(message: str) -> tuple[str, Path]:
    home = _home()
    if home is None:
        raise RuntimeError("HERMES_HOME missing")
    scripts = home / "scripts"
    reminders = scripts / "reminders"
    scripts.mkdir(mode=0o700, parents=True, exist_ok=True)
    reminders.mkdir(mode=0o700, parents=True, exist_ok=True)
    if scripts.is_symlink() or reminders.is_symlink():
        raise RuntimeError("unsafe scripts directory")
    if os.name == "posix":
        os.chmod(scripts, 0o700)
        os.chmod(reminders, 0o700)
    token = secrets.token_hex(12)
    relative = f"reminders/mariyam_reminder_{token}.py"
    path = scripts / relative
    literal = json.dumps(message, ensure_ascii=True)
    content = (
        "from pathlib import Path\n"
        f"_MESSAGE = {literal}\n"
        "print(_MESSAGE, flush=True)\n"
        "try:\n"
        "    Path(__file__).unlink()\n"
        "except OSError:\n"
        "    pass\n"
    ).encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    if os.name == "posix":
        os.chmod(path, 0o600)
    return relative, path


def _explicit_failure(result: object) -> bool:
    value = result
    if isinstance(result, str):
        try:
            value = json.loads(result)
        except (TypeError, ValueError):
            return False
    return isinstance(value, dict) and value.get("success") is False


def on_tool_execution_middleware(**kwargs):
    tool_name = kwargs.get("tool_name")
    args = kwargs.get("args")
    next_call = kwargs.get("next_call")
    session_id = kwargs.get("session_id")
    if not callable(next_call):
        return _safe_error("REMINDER_GUARD_ERROR")
    if (
        tool_name != "cronjob"
        or not isinstance(args, dict)
        or args.get("action") != "create"
        or not _is_one_shot(args.get("schedule"))
        or not _trusted_oyijon(session_id)
    ):
        return next_call(args)
    message = _clean_message(args.get("prompt"))
    if message is None:
        return _safe_error("REMINDER_TEXT_INVALID")
    try:
        relative, path = _create_reminder_script(message)
    except (OSError, RuntimeError):
        return _safe_error("REMINDER_SCRIPT_FAILED")
    effective = copy.deepcopy(args)
    effective.update(
        {
            "prompt": message,
            "name": "mariyam_one_shot_reminder",
            "repeat": 1,
            "deliver": "origin",
            "script": relative,
            "no_agent": True,
            "skills": [],
            "enabled_toolsets": [],
            "attach_to_session": False,
        }
    )
    for field in ("skill", "model", "provider", "base_url", "context_from", "workdir"):
        effective.pop(field, None)
    try:
        result = next_call(effective)
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    if _explicit_failure(result):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return result


def register(ctx) -> None:  # pragma: no cover - exercised by Hermes loader
    ctx.register_middleware("tool_execution", on_tool_execution_middleware)
