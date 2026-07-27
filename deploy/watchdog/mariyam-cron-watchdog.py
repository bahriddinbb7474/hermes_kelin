#!/usr/bin/env python3
"""Provider-independent +15 minute watchdog for critical Mariyam cron jobs."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import subprocess
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")
DEFAULT_HOME = Path("/home/timeagent/.hermes/profiles/mariyam_oyijon")
DEFAULT_CONFIG = Path(
    "/opt/hermes-mariyam/deploy/watchdog/cron_watchdog_jobs.json"
)
DEFAULT_STATE = Path("/opt/hermes-mariyam/var/watchdog/cron-watchdog.sqlite3")
DEFAULT_HERMES_PYTHON = Path(
    "/home/timeagent/.hermes/hermes-agent/venv/bin/python"
)
MAX_FILE_BYTES = 2 * 1024 * 1024
RETRY_TIMEOUT_SECONDS = 420
STALE_CLAIM_MINUTES = 10


@dataclass(frozen=True)
class JobSpec:
    name: str
    schedule: str
    grace_minutes: int
    max_lateness_minutes: int


def _regular_bounded(path: Path, *, private: bool = False) -> bytes:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"unsafe file: {path}")
    if private and os.name == "posix" and stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError(f"private file must be 0600: {path}")
    if info.st_size > MAX_FILE_BYTES:
        raise RuntimeError(f"oversize file: {path}")
    return path.read_bytes()


def load_specs(path: Path) -> list[JobSpec]:
    raw = json.loads(_regular_bounded(path).decode("utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"version", "jobs"}:
        raise RuntimeError("invalid watchdog config root")
    if raw["version"] != 1 or not isinstance(raw["jobs"], list):
        raise RuntimeError("invalid watchdog config version")
    specs: list[JobSpec] = []
    names: set[str] = set()
    for item in raw["jobs"]:
        if not isinstance(item, dict) or set(item) != {
            "name",
            "schedule",
            "grace_minutes",
            "max_lateness_minutes",
        }:
            raise RuntimeError("invalid watchdog job spec")
        spec = JobSpec(**item)
        if (
            not spec.name
            or spec.name in names
            or not isinstance(spec.grace_minutes, int)
            or not 1 <= spec.grace_minutes <= 60
            or not isinstance(spec.max_lateness_minutes, int)
            or spec.max_lateness_minutes <= spec.grace_minutes
            or spec.max_lateness_minutes > 1440
        ):
            raise RuntimeError("unsafe watchdog job spec")
        _parse_fixed_schedule(spec.schedule)
        names.add(spec.name)
        specs.append(spec)
    if len(specs) != 8:
        raise RuntimeError("watchdog must cover exactly eight critical jobs")
    return specs


def load_jobs(home: Path) -> list[dict]:
    data = json.loads(
        _regular_bounded(home / "cron/jobs.json").decode("utf-8")
    )
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
        raise RuntimeError("invalid cron jobs store")
    return jobs


def load_trusted_job_ids(path: Path) -> set[str]:
    data = json.loads(_regular_bounded(path, private=True).decode("utf-8"))
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if data.get("version") != 1 or not isinstance(jobs, dict):
        raise RuntimeError("invalid private cron mapping")
    return set(jobs)


def _parse_fixed_schedule(value: str) -> tuple[int, int, int | None]:
    fields = value.split()
    if len(fields) != 5 or fields[3:] != ["*", "*"]:
        raise RuntimeError(f"unsupported watchdog schedule: {value}")
    minute, hour, day = fields[:3]
    if not minute.isdigit() or not hour.isdigit():
        raise RuntimeError(f"unsupported watchdog schedule: {value}")
    minute_i, hour_i = int(minute), int(hour)
    day_i = None if day == "*" else int(day) if day.isdigit() else -1
    if (
        not 0 <= minute_i <= 59
        or not 0 <= hour_i <= 23
        or (day_i is not None and not 1 <= day_i <= 31)
    ):
        raise RuntimeError(f"invalid watchdog schedule: {value}")
    return minute_i, hour_i, day_i


def due_occurrence(spec: JobSpec, now: datetime) -> datetime | None:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(TASHKENT)
    minute, hour, day = _parse_fixed_schedule(spec.schedule)
    if day is not None and local.day != day:
        return None
    expected = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    earliest = expected + timedelta(minutes=spec.grace_minutes)
    latest = expected + timedelta(minutes=spec.max_lateness_minutes)
    return expected if earliest <= local <= latest else None


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def output_after(home: Path, job_id: str, expected: datetime) -> bool:
    directory = home / "cron/output" / job_id
    if not directory.is_dir() or directory.is_symlink():
        return False
    threshold = expected.timestamp() - 60
    return any(
        item.is_file()
        and not item.is_symlink()
        and item.suffix == ".md"
        and item.stat().st_mtime >= threshold
        for item in directory.iterdir()
    )


def successful_occurrence(job: dict, expected: datetime) -> bool:
    last_run = _parse_time(job.get("last_run_at"))
    return bool(
        last_run
        and last_run >= expected
        and job.get("last_status") == "ok"
        and not job.get("last_delivery_error")
    )


def _validate_production_job(
    job: dict, spec: JobSpec, trusted_ids: set[str]
) -> None:
    schedule = job.get("schedule")
    if (
        not isinstance(schedule, dict)
        or schedule.get("kind") != "cron"
        or schedule.get("expr") != spec.schedule
        or job.get("id") not in trusted_ids
        or job.get("script") is not None
        or job.get("no_agent") is not False
        or job.get("enabled") is not True
        or job.get("state") not in {"scheduled", "error"}
    ):
        raise RuntimeError(f"trusted job definition mismatch: {spec.name}")


def _connect_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS attempts (
               job_id TEXT NOT NULL,
               expected_at TEXT NOT NULL,
               status TEXT NOT NULL,
               retry_started_at TEXT NOT NULL,
               finished_at TEXT,
               last_error TEXT,
               PRIMARY KEY(job_id, expected_at)
           )"""
    )
    connection.commit()
    if os.name == "posix":
        os.chmod(path, 0o600)
    return connection


def claim_retry(path: Path, job_id: str, expected: datetime, now: datetime) -> bool:
    with _connect_state(path) as connection:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO attempts
               (job_id, expected_at, status, retry_started_at)
               VALUES (?, ?, 'retrying', ?)""",
            (job_id, expected.isoformat(), now.isoformat()),
        )
        return cursor.rowcount == 1


def finish_retry(
    path: Path,
    job_id: str,
    expected: datetime,
    status_value: str,
    now: datetime,
    error: str | None = None,
) -> None:
    safe_error = (error or "")[:200] or None
    with _connect_state(path) as connection:
        connection.execute(
            """UPDATE attempts
               SET status=?, finished_at=?, last_error=?
               WHERE job_id=? AND expected_at=?""",
            (
                status_value,
                now.isoformat(),
                safe_error,
                job_id,
                expected.isoformat(),
            ),
        )


def attempt_record(
    path: Path, job_id: str, expected: datetime
) -> tuple[str, datetime | None, str | None] | None:
    with _connect_state(path) as connection:
        row = connection.execute(
            """SELECT status, retry_started_at, last_error FROM attempts
               WHERE job_id=? AND expected_at=?""",
            (job_id, expected.isoformat()),
        ).fetchone()
    if not row:
        return None
    return row[0], _parse_time(row[1]), row[2]


def notify_or_defer(
    path: Path,
    job_id: str,
    job_name: str,
    expected: datetime,
    reason: str,
    now: datetime,
    notifier: Callable[[str, datetime, str], None],
) -> None:
    # Persist the alert intent before the network side effect. If this process
    # dies or Telegram is temporarily unavailable, the next timer tick resumes
    # only the alert and never repeats the user-facing cron run.
    finish_retry(path, job_id, expected, "alert_pending", now, reason)
    notifier(job_name, expected, reason)
    finish_retry(path, job_id, expected, "admin_alerted", now, reason)


def resume_pending_alert(
    path: Path,
    job_id: str,
    job_name: str,
    expected: datetime,
    now: datetime,
    notifier: Callable[[str, datetime, str], None],
) -> bool:
    record = attempt_record(path, job_id, expected)
    if record is None:
        return False
    status_value, started, stored_error = record
    if status_value == "alert_pending":
        notify_or_defer(
            path,
            job_id,
            job_name,
            expected,
            stored_error or "watchdog alert delivery interrupted",
            now,
            notifier,
        )
        return True
    if (
        status_value == "retrying"
        and started is not None
        and now - started >= timedelta(minutes=STALE_CLAIM_MINUTES)
    ):
        notify_or_defer(
            path,
            job_id,
            job_name,
            expected,
            "watchdog retry interrupted; duplicate retry suppressed",
            now,
            notifier,
        )
        return True
    return False


def run_retry(job_id: str, home: Path, python: Path) -> tuple[bool, str | None]:
    try:
        result = subprocess.run(
            [
                str(python),
                "-m",
                "hermes_cli.main",
                "--profile",
                "mariyam_oyijon",
                "cron",
                "run",
                job_id,
            ],
            env={**os.environ, "HERMES_HOME": str(home)},
            capture_output=True,
            text=True,
            timeout=RETRY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "retry timeout"
    return result.returncode == 0, None if result.returncode == 0 else "cron run failed"


def notify_admin(job_name: str, expected: datetime, reason: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    admin = os.environ["ADMIN_TELEGRAM_ID"]
    text = (
        "🚨 Mariyam cron watchdog: повтор не доставлен. "
        f"Job={job_name}, scheduled={expected.astimezone(TASHKENT):%Y-%m-%d %H:%M}, "
        f"reason={reason[:80]}."
    )
    payload = urllib.parse.urlencode({"chat_id": admin, "text": text}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError("admin notification failed")


def check_spec(
    spec: JobSpec,
    now: datetime,
    *,
    home: Path,
    state_path: Path,
    trusted_ids: set[str],
    python: Path,
    runner: Callable[[str, Path, Path], tuple[bool, str | None]] = run_retry,
    notifier: Callable[[str, datetime, str], None] = notify_admin,
) -> str:
    expected = due_occurrence(spec, now)
    if expected is None:
        return "not_due"
    matches = [job for job in load_jobs(home) if job.get("name") == spec.name]
    if len(matches) != 1:
        synthetic = f"missing:{spec.name}"
        if claim_retry(state_path, synthetic, expected, now):
            notify_or_defer(
                state_path,
                synthetic,
                spec.name,
                expected,
                "job missing or duplicated",
                now,
                notifier,
            )
        else:
            resume_pending_alert(
                state_path, synthetic, spec.name, expected, now, notifier
            )
        return "admin_alerted"
    job = matches[0]
    _validate_production_job(job, spec, trusted_ids)
    if successful_occurrence(job, expected) and output_after(
        home, job["id"], expected
    ):
        return "healthy"
    if job.get("fire_claim") or job.get("run_claim"):
        return "running"
    prior_run = _parse_time(job.get("last_run_at"))
    if (
        output_after(home, job["id"], expected)
        and (prior_run is None or prior_run < expected)
        and not job.get("last_delivery_error")
    ):
        if claim_retry(state_path, job["id"], expected, now):
            notify_or_defer(
                state_path,
                job["id"],
                spec.name,
                expected,
                "ambiguous prior delivery; retry suppressed",
                now,
                notifier,
            )
        else:
            resume_pending_alert(
                state_path, job["id"], spec.name, expected, now, notifier
            )
        return "ambiguous"
    if not claim_retry(state_path, job["id"], expected, now):
        if resume_pending_alert(
            state_path, job["id"], spec.name, expected, now, notifier
        ):
            return "admin_alerted"
        return "already_handled"

    started = datetime.now(TASHKENT)
    invoked, invoke_error = runner(job["id"], home, python)
    refreshed = next(
        (item for item in load_jobs(home) if item.get("id") == job["id"]), None
    )
    retry_ok = bool(
        invoked
        and refreshed
        and successful_occurrence(refreshed, started)
        and output_after(home, job["id"], started)
    )
    finished = datetime.now(TASHKENT)
    if retry_ok:
        finish_retry(state_path, job["id"], expected, "retry_ok", finished)
        print(f"WATCHDOG_RETRY=PASS job={spec.name}")
        return "retry_ok"

    reason = invoke_error or (
        "delivery failed"
        if refreshed and refreshed.get("last_delivery_error")
        else "retry execution failed"
    )
    notify_or_defer(
        state_path,
        job["id"],
        spec.name,
        expected,
        reason,
        finished,
        notifier,
    )
    print(f"WATCHDOG_RETRY=FAIL_ADMIN_NOTIFIED job={spec.name}")
    return "admin_alerted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", help="operator/test ISO timestamp")
    args = parser.parse_args()
    now = (
        datetime.fromisoformat(args.now)
        if args.now
        else datetime.now(TASHKENT)
    )
    if now.tzinfo is None:
        raise SystemExit("--now must include timezone")
    home = Path(os.environ.get("HERMES_HOME", str(DEFAULT_HOME)))
    config = Path(
        os.environ.get("MARIYAM_WATCHDOG_CONFIG", str(DEFAULT_CONFIG))
    )
    state_path = Path(
        os.environ.get("MARIYAM_WATCHDOG_STATE", str(DEFAULT_STATE))
    )
    mapping_path = Path(os.environ["MARIYAM_CRON_IDENTITY_MAP_FILE"])
    python = Path(
        os.environ.get("MARIYAM_HERMES_PYTHON", str(DEFAULT_HERMES_PYTHON))
    )
    trusted_ids = load_trusted_job_ids(mapping_path)
    for spec in load_specs(config):
        check_spec(
            spec,
            now,
            home=home,
            state_path=state_path,
            trusted_ids=trusted_ids,
            python=python,
        )


if __name__ == "__main__":
    main()
