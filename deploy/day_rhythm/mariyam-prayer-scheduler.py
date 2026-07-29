#!/usr/bin/env python3
"""Create today's prayer-care no-agent one-shots from the Aladhan cache."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import stat
import subprocess
from datetime import date, datetime, time
from pathlib import Path

from mariyam_day_rhythm import (
    SLOTS,
    TASHKENT,
    reminder_times,
    render_prayer_reminder,
    render_prayer_times,
)

from backend import external_data

PROFILE = Path(
    os.environ.get("HERMES_HOME")
    or "/home/timeagent/.hermes/profiles/mariyam_oyijon"
)
IDENTITY_MAP = Path(
    os.environ.get("MARIYAM_IDENTITY_MAP_FILE")
    or "/opt/hermes-mariyam-secrets/identity-map.json"
)
HERMES_PYTHON = Path(
    os.environ.get("MARIYAM_HERMES_PYTHON")
    or "/home/timeagent/.hermes/hermes-agent/venv/bin/python"
)
PROFILE_NAME = "mariyam_oyijon"
PRAYER_TIMES_AT = time(7, 45)
MAX_JSON_BYTES = 2 * 1024 * 1024


def _regular_json(path: Path, *, private: bool = False) -> dict:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"unsafe file: {path}")
    if private and os.name == "posix" and stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError(f"private file must be 0600: {path}")
    if info.st_size > MAX_JSON_BYTES:
        raise RuntimeError(f"oversize file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid JSON object: {path}")
    return value


def _oyijon_target() -> str:
    mapping = _regular_json(IDENTITY_MAP, private=True)
    matches = [
        telegram_id
        for telegram_id, entry in mapping.items()
        if isinstance(entry, dict)
        and entry.get("role") == "oyijon"
        and str(telegram_id).isdigit()
    ]
    if len(matches) != 1:
        raise RuntimeError("identity mapping must contain exactly one Oyijon")
    return f"telegram:{matches[0]}"


def _existing_job_names() -> set[str]:
    raw = _regular_json(PROFILE / "cron" / "jobs.json")
    jobs = raw.get("jobs", raw)
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    if not isinstance(jobs, list):
        raise RuntimeError("invalid jobs store")
    return {
        str(job.get("name"))
        for job in jobs
        if isinstance(job, dict) and isinstance(job.get("name"), str)
    }


def _message_script(message: str) -> tuple[str, Path]:
    scripts_root = PROFILE / "scripts"
    reminder_dir = scripts_root / "day_rhythm" / "reminders"
    reminder_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if scripts_root.is_symlink() or reminder_dir.is_symlink():
        raise RuntimeError("unsafe scripts directory")
    if os.name == "posix":
        os.chmod(scripts_root, 0o700)
        os.chmod(reminder_dir.parent, 0o700)
        os.chmod(reminder_dir, 0o700)
    token = secrets.token_hex(12)
    relative = f"day_rhythm/reminders/mariyam_day_rhythm_{token}.py"
    path = scripts_root / relative
    content = (
        "import sys\n"
        "from pathlib import Path\n"
        "_SELF = Path(__file__).resolve()\n"
        "sys.path.insert(0, str(_SELF.parents[2]))\n"
        f"_MESSAGE = {json.dumps(message, ensure_ascii=True)}\n"
        "try:\n"
        "    try:\n"
        "        from day_rhythm.mariyam_day_rhythm import emit_noncritical\n"
        "    except Exception:\n"
        "        emit_noncritical = None\n"
        "    if emit_noncritical is not None:\n"
        "        emit_noncritical(_MESSAGE)\n"
        "finally:\n"
        "    try:\n"
        "        _SELF.unlink()\n"
        "    except OSError:\n"
        "        pass\n"
    ).encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    if os.name == "posix":
        os.chmod(path, 0o600)
    return relative, path


def _create_job(
    *,
    when: datetime,
    name: str,
    message: str,
    target: str,
) -> None:
    relative, script = _message_script(message)
    command = [
        str(HERMES_PYTHON),
        "-m",
        "hermes_cli.main",
        "--profile",
        PROFILE_NAME,
        "cron",
        "create",
        when.isoformat(),
        message,
        "--name",
        name,
        "--deliver",
        target,
        "--repeat",
        "1",
        "--script",
        relative,
        "--no-agent",
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "HERMES_HOME": str(PROFILE)},
        )
    except Exception:
        try:
            script.unlink()
        except FileNotFoundError:
            pass
        raise


def _validated_timings(result: dict, today) -> dict[str, str]:
    if result.get("ok") is not True or result.get("cache", {}).get("stale") is True:
        raise RuntimeError("fresh Aladhan data is required")
    try:
        day, month, year = map(int, str(result["date"]).split("-"))
        source_day = date(year, month, day)
        timings = {slot: result[slot] for slot in SLOTS}
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("invalid Aladhan result") from exc
    if source_day != today:
        raise RuntimeError("Aladhan result date does not match today")
    return timings


def build_plan(now: datetime, timings: dict[str, str]) -> list[dict]:
    local = now.astimezone(TASHKENT)
    day = local.date()
    plan = [
        {
            "name": f"mariyam_prayer_times_{day:%Y%m%d}",
            "when": datetime.combine(day, PRAYER_TIMES_AT, TASHKENT),
            "message": render_prayer_times(timings),
        }
    ]
    for slot, when in reminder_times(day, timings).items():
        plan.append(
            {
                "name": f"mariyam_prayer_{slot}_{day:%Y%m%d}",
                "when": when,
                "message": render_prayer_reminder(slot, day),
            }
        )
    return [item for item in plan if item["when"] > local]


def main() -> int:
    now = datetime.now(TASHKENT)
    result = asyncio.run(external_data.get_tashkent_prayer_times())
    timings = _validated_timings(result, now.date())
    target = _oyijon_target()
    existing = _existing_job_names()
    created = 0
    skipped = 0
    for item in build_plan(now, timings):
        if item["name"] in existing:
            skipped += 1
            continue
        _create_job(target=target, **item)
        existing.add(item["name"])
        created += 1
    print(f"day_rhythm created={created} duplicate_skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
