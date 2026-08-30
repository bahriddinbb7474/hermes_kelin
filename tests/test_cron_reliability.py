"""Stage 6/8 pre-handover cron reliability contracts."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import stat
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WATCHDOG_PATH = (
    REPO / "deploy" / "watchdog" / "mariyam-cron-watchdog.py"
)
PLUGIN_PATH = (
    REPO
    / "deploy"
    / "hermes_plugins"
    / "mariyam_cron_reliability"
    / "__init__.py"
)
CONFIG_PATH = (
    REPO / "deploy" / "watchdog" / "cron_watchdog_jobs.json"
)
SOUL_PATH = REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "SOUL.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


watchdog = _load("mariyam_cron_watchdog_test", WATCHDOG_PATH)
reliability = _load("mariyam_cron_reliability_test", PLUGIN_PATH)


def _write_jobs(home: Path, jobs: list[dict]) -> None:
    cron = home / "cron"
    cron.mkdir(parents=True, exist_ok=True)
    (cron / "jobs.json").write_text(
        json.dumps({"jobs": jobs}), encoding="utf-8"
    )


def _output(
    home: Path,
    job_id: str,
    text: str = "output",
    *,
    timestamp: datetime | None = None,
) -> None:
    directory = home / "cron" / "output" / job_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "run.md"
    path.write_text(text, encoding="utf-8")
    if timestamp is not None:
        os.utime(path, (timestamp.timestamp(), timestamp.timestamp()))


def _job(
    job_id: str,
    name: str,
    schedule: str,
    last_run_at: str | None,
    status: str | None,
    delivery_error: str | None = None,
) -> dict:
    return {
        "id": job_id,
        "name": name,
        "schedule": {"kind": "cron", "expr": schedule},
        "enabled": True,
        "state": "scheduled",
        "script": None,
        "no_agent": False,
        "last_run_at": last_run_at,
        "last_status": status,
        "last_delivery_error": delivery_error,
        "fire_claim": None,
        "run_claim": None,
    }


def test_watchdog_config_covers_exact_critical_jobs():
    # imp12-opus: mariyam_obligation_reminders and mariyam_admin_report_1930
    # moved to no_agent scripts and dropped out of this LLM-turn-health list
    # (see the watchdog module docstring) — six remain, not eight.
    specs = watchdog.load_specs(CONFIG_PATH)
    assert len(specs) == 6
    assert {item.name for item in specs} == {
        "mariyam_plan_25_draft",
        "mariyam_plan_27_reminder",
        "mariyam_plan_28_escalate",
        "mariyam_plan_01a_auto",
        "mariyam_plan_01b_fallback",
        "mariyam_daily_morning",
    }
    assert all(item.grace_minutes == 15 for item in specs)


def test_no_agent_jobs_would_be_rejected_by_the_llm_health_validator():
    """Documents *why* the two jobs above had to leave this watchdog: a
    no_agent job fails `_validate_production_job`'s trusted-shape check by
    design (script is not None / no_agent is not False)."""
    spec = watchdog.JobSpec("obligations", "15 9 * * *", 15, 360)
    job = _job("c" * 12, spec.name, spec.schedule, None, None)
    job["script"] = "mariyam_obligation_reminders_cron.py"
    job["no_agent"] = True
    import pytest

    with pytest.raises(RuntimeError, match="trusted job definition mismatch"):
        watchdog._validate_production_job(job, spec, {job["id"]})


def test_successful_tick_is_silent_and_never_retried(tmp_path):
    home = tmp_path / "profile"
    expected = datetime(2026, 7, 28, 8, 30, tzinfo=watchdog.TASHKENT)
    now = expected + timedelta(minutes=15)
    spec = watchdog.JobSpec("morning", "0 8 * * *", 15, 360)
    job = _job("a" * 12, spec.name, spec.schedule, expected.isoformat(), "ok")
    _write_jobs(home, [job])
    _output(home, job["id"], timestamp=expected + timedelta(minutes=1))
    called = []
    notified = []
    result = watchdog.check_spec(
        spec,
        now,
        home=home,
        state_path=tmp_path / "state.sqlite3",
        trusted_ids={job["id"]},
        python=Path(sys.executable),
        runner=lambda *_: called.append(True) or (True, None),
        notifier=lambda *_: notified.append(True),
    )
    assert result == "healthy"
    assert called == []
    assert notified == []


def test_failed_tick_retries_once_then_stays_silent(tmp_path):
    home = tmp_path / "profile"
    expected = datetime(2026, 7, 28, 9, 15, tzinfo=watchdog.TASHKENT)
    now = expected + timedelta(minutes=15)
    spec = watchdog.JobSpec("obligations", "15 9 * * *", 15, 360)
    job = _job(
        "b" * 12, spec.name, spec.schedule, expected.isoformat(), "error"
    )
    _write_jobs(home, [job])
    calls = []
    notified = []

    def runner(*_):
        calls.append(True)
        retry_at = max(
            datetime.now(watchdog.TASHKENT),
            expected + timedelta(minutes=16),
        )
        job["last_run_at"] = retry_at.isoformat()
        job["last_status"] = "ok"
        job["last_delivery_error"] = None
        _write_jobs(home, [job])
        _output(home, job["id"], "retry output", timestamp=retry_at)
        return True, None

    state = tmp_path / "state.sqlite3"
    first = watchdog.check_spec(
        spec,
        now,
        home=home,
        state_path=state,
        trusted_ids={job["id"]},
        python=Path(sys.executable),
        runner=runner,
        notifier=lambda *_: notified.append(True),
    )
    second = watchdog.check_spec(
        spec,
        now + timedelta(minutes=5),
        home=home,
        state_path=state,
        trusted_ids={job["id"]},
        python=Path(sys.executable),
        runner=runner,
        notifier=lambda *_: notified.append(True),
    )
    assert first == "retry_ok"
    assert second == "healthy"
    assert len(calls) == 1
    assert notified == []


def test_failed_retry_notifies_admin_exactly_once(tmp_path):
    home = tmp_path / "profile"
    expected = datetime(2026, 7, 28, 19, 30, tzinfo=watchdog.TASHKENT)
    now = expected + timedelta(minutes=15)
    spec = watchdog.JobSpec("admin-report", "30 19 * * *", 15, 360)
    job = _job(
        "c" * 12, spec.name, spec.schedule, expected.isoformat(), "error"
    )
    _write_jobs(home, [job])
    calls = []
    notifications = []
    state = tmp_path / "state.sqlite3"
    kwargs = {
        "home": home,
        "state_path": state,
        "trusted_ids": {job["id"]},
        "python": Path(sys.executable),
        "runner": lambda *_: calls.append(True) or (False, "provider failed"),
        "notifier": lambda *args: notifications.append(args),
    }
    first = watchdog.check_spec(spec, now, **kwargs)
    second = watchdog.check_spec(
        spec, now + timedelta(minutes=5), **kwargs
    )
    assert first == "admin_alerted"
    assert second == "already_handled"
    assert len(calls) == 1
    assert len(notifications) == 1


def _telegram_session(home: Path, mapping: Path, role: str = "oyijon") -> str:
    home.mkdir(parents=True, exist_ok=True)
    session_id = "telegram-test-session"
    with sqlite3.connect(home / "state.db") as connection:
        connection.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, origin_json TEXT)"
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?)",
            (
                session_id,
                json.dumps(
                    {"platform": "telegram", "user_id": "222222222"}
                ),
            ),
        )
    mapping.write_text(
        json.dumps(
            {
                "222222222": {
                    "user_id": 20,
                    "role": role,
                    "display_name": "Test",
                }
            }
        ),
        encoding="utf-8",
    )
    if os.name == "posix":
        mapping.chmod(0o600)
    return session_id


def test_failed_admin_notification_is_retried_without_rerunning_job(tmp_path):
    home = tmp_path / "profile"
    expected = datetime(2026, 7, 28, 19, 30, tzinfo=watchdog.TASHKENT)
    spec = watchdog.JobSpec("admin-report", "30 19 * * *", 15, 360)
    job = _job(
        "e" * 12, spec.name, spec.schedule, expected.isoformat(), "error"
    )
    _write_jobs(home, [job])
    state = tmp_path / "state.sqlite3"
    runs = []
    notices = []

    def unavailable(*_):
        notices.append("failed")
        raise OSError("telegram unavailable")

    kwargs = {
        "home": home,
        "state_path": state,
        "trusted_ids": {job["id"]},
        "python": Path(sys.executable),
        "runner": lambda *_: runs.append(True) or (False, "provider failed"),
    }
    try:
        watchdog.check_spec(
            spec,
            expected + timedelta(minutes=15),
            notifier=unavailable,
            **kwargs,
        )
    except OSError:
        pass
    else:
        raise AssertionError("notification failure must fail the service tick")

    result = watchdog.check_spec(
        spec,
        expected + timedelta(minutes=20),
        notifier=lambda *_: notices.append("sent"),
        **kwargs,
    )
    assert result == "admin_alerted"
    assert runs == [True]
    assert notices == ["failed", "sent"]


def test_stale_retry_claim_alerts_without_duplicate_retry(tmp_path):
    home = tmp_path / "profile"
    expected = datetime(2026, 7, 28, 9, 15, tzinfo=watchdog.TASHKENT)
    spec = watchdog.JobSpec("obligations", "15 9 * * *", 15, 360)
    job = _job(
        "f" * 12, spec.name, spec.schedule, expected.isoformat(), "error"
    )
    _write_jobs(home, [job])
    state = tmp_path / "state.sqlite3"
    claimed_at = expected + timedelta(minutes=15)
    assert watchdog.claim_retry(state, job["id"], expected, claimed_at)
    runs = []
    notices = []
    result = watchdog.check_spec(
        spec,
        claimed_at + timedelta(minutes=10),
        home=home,
        state_path=state,
        trusted_ids={job["id"]},
        python=Path(sys.executable),
        runner=lambda *_: runs.append(True) or (True, None),
        notifier=lambda *args: notices.append(args),
    )
    assert result == "admin_alerted"
    assert runs == []
    assert len(notices) == 1
    assert "duplicate retry suppressed" in notices[0][2]


def test_oyijon_one_shot_becomes_private_no_agent_script(
    tmp_path, monkeypatch
):
    home = tmp_path / "profile"
    mapping = tmp_path / "identity.json"
    session_id = _telegram_session(home, mapping)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(mapping))
    captured = {}

    def downstream(args):
        captured.update(args)
        return json.dumps({"success": True, "job_id": "d" * 12})

    schedule = (
        datetime.now(watchdog.TASHKENT) + timedelta(days=1)
    ).isoformat()
    message = "Ойижон, дорингизни ичишни унутманг."
    result = reliability.on_tool_execution_middleware(
        tool_name="cronjob",
        args={
            "action": "create",
            "schedule": schedule,
            "prompt": message,
        },
        next_call=downstream,
        session_id=session_id,
    )
    assert json.loads(result)["success"] is True
    assert captured["no_agent"] is True
    assert captured["repeat"] == 1
    assert captured["deliver"] == "origin"
    assert captured["skills"] == []
    assert captured["enabled_toolsets"] == []
    assert captured["attach_to_session"] is False
    assert "model" not in captured
    script = home / "scripts" / captured["script"]
    helper_dir = home / "scripts" / "day_rhythm"
    helper_dir.mkdir(parents=True)
    (helper_dir / "__init__.py").write_text("", encoding="utf-8")
    (helper_dir / "mariyam_day_rhythm.py").write_text(
        "def emit_noncritical(message):\n    print(message, flush=True)\n",
        encoding="utf-8",
    )
    assert script.is_file()
    if os.name == "posix":
        assert stat.S_IMODE(script.stat().st_mode) == 0o600
    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == message
    assert not script.exists()


def test_admin_or_recurring_job_is_not_rewritten(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    mapping = tmp_path / "identity.json"
    session_id = _telegram_session(home, mapping, role="admin")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(mapping))
    original = {
        "action": "create",
        "schedule": "30 8 * * *",
        "prompt": "Кунлик хабар.",
    }
    captured = {}
    reliability.on_tool_execution_middleware(
        tool_name="cronjob",
        args=original,
        next_call=lambda args: captured.update(args) or "{}",
        session_id=session_id,
    )
    assert captured == original
    assert not (home / "scripts/reminders").exists()


def test_soul_requires_no_agent_one_shot_contract():
    text = SOUL_PATH.read_text(encoding="utf-8")
    assert "**untrusted no-agent**" in text
    assert "`script=mariyam_reminder.py`" in text
    assert "`no_agent=true`" in text
    # SOUL v2 (imp04): trusted-mapping isolation остаётся за profile guard,
    # промпту достаточно запрета передавать привилегированные поля.
    assert "user-scoped и MCP tools в такой job не передавай" in text


def test_manifest_and_systemd_hardening_contracts():
    manifest = PLUGIN_PATH.with_name("plugin.yaml").read_text(encoding="utf-8")
    service = (
        REPO
        / "deploy/watchdog/mariyam-cron-watchdog.service"
    ).read_text(encoding="utf-8")
    timer = (
        REPO
        / "deploy/watchdog/mariyam-cron-watchdog.timer"
    ).read_text(encoding="utf-8")
    failure = (
        REPO
        / "deploy/watchdog/mariyam-heartbeat-failure@.service"
    ).read_text(encoding="utf-8")
    profile = (
        REPO
        / "deploy/hermes_profile_mariyam_oyijon"
        / "config.skill-protect.snippet.yaml"
    ).read_text(encoding="utf-8")
    assert 'version: "1.1.0"' in manifest
    assert "NoNewPrivileges=yes" in service
    assert "ProtectSystem=strict" in service
    assert "ReadWritePaths=/opt/hermes-mariyam/var/watchdog" in service
    assert "User=timeagent" not in service
    assert "WantedBy=default.target" in service
    assert "OnCalendar=*:0/5" in timer
    assert "mariyam-heartbeat.py --failure-unit %i" in failure
    assert profile.index("- mariyam_health_guard") < profile.index(
        "- mariyam_cron_reliability"
    ) < profile.index("- mariyam_stage53_guard")
    assert 'ctx.register_hook("pre_gateway_dispatch"' in PLUGIN_PATH.read_text(
        encoding="utf-8"
    )
    assert 'ctx.register_hook("transform_llm_output"' in PLUGIN_PATH.read_text(
        encoding="utf-8"
    )
