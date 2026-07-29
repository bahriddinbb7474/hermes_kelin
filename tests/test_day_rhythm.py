"""fix02 deterministic prayer care, quiet windows and no-agent contracts."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DAY_DIR = REPO / "deploy" / "day_rhythm"
MODULE_PATH = DAY_DIR / "mariyam_day_rhythm.py"
SCHEDULER_PATH = DAY_DIR / "mariyam-prayer-scheduler.py"
PLUGIN_PATH = (
    REPO
    / "deploy"
    / "hermes_plugins"
    / "mariyam_cron_reliability"
    / "__init__.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rhythm = _load("mariyam_day_rhythm_test", MODULE_PATH)


def _write_cache(path: Path, now: datetime, timings: dict[str, str]) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    "prayer_tashkent_hanafi": {
                        "fetched_at": now.isoformat(),
                        "data": timings,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_each_prayer_slot_has_ten_cyrillic_rotating_templates():
    assert set(rhythm.PRAYER_TEMPLATES) == set(rhythm.SLOTS)
    day = date(2026, 7, 29)
    for slot, templates in rhythm.PRAYER_TEMPLATES.items():
        assert len(templates) == 10
        assert len(set(templates)) == 10
        assert all("Ойижон" in text for text in templates)
        assert all("Бирор хизмат бўлса, шу ердаман." in text for text in templates)
        assert all(re.search(r"[А-Яа-яЎўҚқҒғҲҳ]", text) for text in templates)
        assert all(not re.search(r"[A-Za-z]", text) for text in templates)
        assert rhythm.render_prayer_reminder(slot, day) != (
            rhythm.render_prayer_reminder(slot, day - timedelta(days=1))
        )
    assert all(
        text.startswith("Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ")
        and "Намоз уйқудан афзал" in text
        for text in rhythm.PRAYER_TEMPLATES["fajr"]
    )


def test_reminders_are_ten_minutes_before_and_times_message_is_separate():
    timings = {
        "fajr": "04:10",
        "dhuhr": "12:30",
        "asr": "17:20",
        "maghrib": "19:45",
        "isha": "21:15",
    }
    day = date(2026, 7, 29)
    reminders = rhythm.reminder_times(day, timings)
    assert reminders["fajr"].strftime("%H:%M") == "04:00"
    assert reminders["maghrib"].strftime("%H:%M") == "19:35"
    message = rhythm.render_prayer_times(timings)
    assert message.count("\n• ") == 5
    assert "Ҳар намоздан 10 дақиқа олдин эслатаман." in message


def test_sleep_and_quran_quiet_windows_are_private_and_deterministic(
    tmp_path, monkeypatch
):
    state = tmp_path / "quiet.json"
    cache = tmp_path / "cache.json"
    monkeypatch.setenv("MARIYAM_QUIET_STATE_FILE", str(state))
    monkeypatch.setenv("MARIYAM_EXTERNAL_CACHE_FILE", str(cache))
    sleep_now = datetime(2026, 7, 29, 22, 0, tzinfo=rhythm.TASHKENT)
    assert rhythm.activate_quiet("ухлаяпман", now=sleep_now) == "sleep"
    value = json.loads(state.read_text(encoding="utf-8"))
    assert value["until"].startswith("2026-07-30T08:00:00")
    assert rhythm.should_deliver_noncritical(now=sleep_now) is False
    assert rhythm.should_deliver_noncritical(
        now=sleep_now, critical=True
    ) is True
    if sys.platform != "win32":
        assert state.stat().st_mode & 0o777 == 0o600

    quran_now = datetime(2026, 7, 30, 10, 0, tzinfo=rhythm.TASHKENT)
    assert rhythm.activate_quiet("Қуръон ўқияпман", now=quran_now) == "quran"
    value = json.loads(state.read_text(encoding="utf-8"))
    assert value["until"].startswith("2026-07-30T11:30:00")
    assert rhythm.should_deliver_noncritical(
        now=quran_now + timedelta(minutes=89)
    ) is False
    assert rhythm.should_deliver_noncritical(
        now=quran_now + timedelta(minutes=91)
    ) is True


def test_prayer_window_suppresses_noncritical_without_blocking_health(
    tmp_path, monkeypatch
):
    state = tmp_path / "quiet.json"
    cache = tmp_path / "cache.json"
    monkeypatch.setenv("MARIYAM_QUIET_STATE_FILE", str(state))
    monkeypatch.setenv("MARIYAM_EXTERNAL_CACHE_FILE", str(cache))
    now = datetime(2026, 7, 29, 12, 35, tzinfo=rhythm.TASHKENT)
    _write_cache(
        cache,
        now,
        {
            "fajr": "04:10",
            "dhuhr": "12:30",
            "asr": "17:20",
            "maghrib": "19:45",
            "isha": "21:15",
        },
    )
    assert rhythm.should_deliver_noncritical(now=now) is False
    assert rhythm.should_deliver_noncritical(now=now, critical=True) is True
    assert rhythm.should_deliver_noncritical(
        now=now + timedelta(minutes=16)
    ) is True


def test_plugin_records_quiet_inbound_and_silences_only_oyijon_cron(
    tmp_path, monkeypatch
):
    home = tmp_path / "profile"
    helper = home / "scripts" / "day_rhythm"
    helper.mkdir(parents=True)
    shutil.copy2(MODULE_PATH, helper / "mariyam_day_rhythm.py")
    (helper / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv(
        "MARIYAM_QUIET_STATE_FILE", str(tmp_path / "quiet.json")
    )
    monkeypatch.setenv(
        "MARIYAM_EXTERNAL_CACHE_FILE", str(tmp_path / "cache.json")
    )
    with sqlite3.connect(home / "state.db") as connection:
        connection.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, title TEXT)"
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            ("cron-morning", "cron", "mariyam_daily_morning · test"),
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            ("cron-admin", "cron", "mariyam_admin_report_1930 · test"),
        )
    plugin = _load("mariyam_cron_reliability_quiet_test", PLUGIN_PATH)
    event = type("Event", (), {"text": "сплю"})()
    assert plugin.on_pre_gateway_dispatch(event=event)["action"] == "skip"
    assert (
        plugin.on_transform_llm_output(session_id="cron-morning")
        == "[SILENT]"
    )
    assert plugin.on_transform_llm_output(session_id="cron-admin") is None
    health_event = type("Event", (), {"text": "юрагим оғрияпти"})()
    assert plugin.on_pre_gateway_dispatch(event=health_event) is None


def test_scheduler_and_systemd_are_no_agent_hardened_contracts():
    source = SCHEDULER_PATH.read_text(encoding="utf-8")
    service = (DAY_DIR / "mariyam-prayer-scheduler.service").read_text(
        encoding="utf-8"
    )
    timer = (DAY_DIR / "mariyam-prayer-scheduler.timer").read_text(
        encoding="utf-8"
    )
    assert '"--no-agent"' in source
    assert '"--repeat",\n        "1"' in source
    assert "fresh Aladhan data is required" in source
    assert "NoNewPrivileges=yes" in service
    assert "ProtectSystem=strict" in service
    assert "OnCalendar=*-*-* 00:20:00 Asia/Tashkent" in timer
    assert "Persistent=true" in timer


def test_controlled_deploy_has_backup_fingerprint_and_rollback_gates():
    deploy = (REPO / "deploy" / "fix02_deploy.sh").read_text(encoding="utf-8")
    watchdog = json.loads(
        (REPO / "deploy" / "watchdog" / "cron_watchdog_jobs.json").read_text(
            encoding="utf-8"
        )
    )
    assert 'MODE="${1:-}"' in deploy
    assert '"--rollback"' in deploy
    assert "cron-identity-map.json" in deploy
    assert "imp04_refresh_cron_fingerprints.py" in deploy
    assert '--schedule "0 8 * * *"' in deploy
    assert 'enable --now "$PRAYER_TIMER"' in deploy
    morning = next(
        item for item in watchdog["jobs"] if item["name"] == "mariyam_daily_morning"
    )
    assert morning["schedule"] == "0 8 * * *"
