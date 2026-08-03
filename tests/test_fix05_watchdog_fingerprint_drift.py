"""fix05: watchdog сам замечает разошедшийся отпечаток cron-задачи.

Гейт в скриптах деплоя закрывает только деплой. Определение задачи меняют и
мимо них — `hermes cron edit`, перепривязка доставки при handover. Тогда guard
молча отказывает инструментам, задача отрабатывает «успешно» и доставляет
пустое сообщение: прежняя логика watchdog такую поломку увидеть не могла.
Здесь проверяется, что теперь видит — в тот же тик и с уведомлением админу.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WATCHDOG_PATH = REPO / "deploy" / "watchdog" / "mariyam-cron-watchdog.py"
GUARD_PATH = (
    REPO / "deploy" / "hermes_plugins" / "mariyam_identity_guard" / "__init__.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


watchdog = _load("mariyam_cron_watchdog_fix05", WATCHDOG_PATH)
guard = _load("mariyam_identity_guard_fix05", GUARD_PATH)

NOW = datetime(2026, 8, 4, 8, 20, tzinfo=watchdog.TASHKENT)


def _job(job_id: str, name: str, deliver: str = "telegram:111") -> dict:
    return {
        "id": job_id,
        "name": name,
        "prompt": "эрталабки хабар",
        "schedule": {"kind": "cron", "expr": "0 8 * * *"},
        "repeat": {"completed": 3, "times": None},
        "deliver": deliver,
        "origin": None,
        "skills": [],
        "script": None,
        "no_agent": False,
        "context_from": None,
        "enabled_toolsets": None,
        "workdir": None,
        "model": None,
        "provider": None,
        "base_url": None,
        "enabled": True,
        "state": "scheduled",
        # волатильные поля: меняются каждый запуск и в отпечаток не входят
        "last_run_at": "2026-08-04T08:00:11+05:00",
        "last_status": "ok",
        "last_delivery_error": None,
    }


def _write(home: Path, mapping: Path, jobs: list[dict]) -> None:
    (home / "cron").mkdir(parents=True, exist_ok=True)
    (home / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": jobs}), encoding="utf-8"
    )
    entries = {
        job["id"]: {
            "purpose": job["name"],
            "user_id": 20,
            "role": "oyijon",
            "allowed_tools": ["get_daily_news"],
            "job_fingerprint_sha256": guard.cron_job_fingerprint(job),
            "prompt_sha256": guard._sha256_text(job["prompt"]),
        }
        for job in jobs
    }
    mapping.write_text(
        json.dumps({"version": 1, "jobs": entries}), encoding="utf-8"
    )
    if os.name == "posix":
        os.chmod(mapping, 0o600)


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    mapping = tmp_path / "cron-identity.json"
    monkeypatch.setenv("MARIYAM_IDENTITY_GUARD", str(GUARD_PATH))
    return home, mapping, tmp_path / "state.sqlite3"


def _skip_if_mode_unenforceable(mapping: Path) -> None:
    if os.name != "posix" and stat.S_IMODE(mapping.stat().st_mode) != 0o600:
        pytest.skip("private-mode check is POSIX-only")


def test_matching_fingerprints_are_silent(env):
    home, mapping, state = env
    _write(home, mapping, [_job("a" * 12, "mariyam_daily_morning")])
    notices = []
    result = watchdog.check_fingerprints(
        NOW,
        home=home,
        mapping_path=mapping,
        state_path=state,
        notifier=lambda *args: notices.append(args),
    )
    assert result == "trusted"
    assert notices == []


def test_changed_deliver_is_detected_and_admin_alerted(env):
    """Ровно случай handover: сменился адрес доставки, промпт не менялся."""
    home, mapping, state = env
    job = _job("a" * 12, "mariyam_daily_morning")
    _write(home, mapping, [job])
    rebound = dict(job, deliver="telegram:320418599")
    (home / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": [rebound]}), encoding="utf-8"
    )

    notices = []
    result = watchdog.check_fingerprints(
        NOW,
        home=home,
        mapping_path=mapping,
        state_path=state,
        notifier=lambda *args: notices.append(args),
    )
    assert result == "admin_alerted"
    assert len(notices) == 1
    assert notices[0][0] == ["mariyam_daily_morning"]


def test_the_same_drift_alerts_once_a_day_then_again_the_next_day(env):
    home, mapping, state = env
    job = _job("a" * 12, "mariyam_daily_morning")
    _write(home, mapping, [job])
    (home / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": [dict(job, deliver="telegram:999")]}), encoding="utf-8"
    )
    notices = []
    kwargs = dict(
        home=home,
        mapping_path=mapping,
        state_path=state,
        notifier=lambda *args: notices.append(args),
    )

    assert watchdog.check_fingerprints(NOW, **kwargs) == "admin_alerted"
    # следующие тики того же дня молчат — иначе это спам каждые 15 минут
    for minutes in (15, 30, 45):
        assert (
            watchdog.check_fingerprints(NOW + timedelta(minutes=minutes), **kwargs)
            == "already_alerted"
        )
    assert len(notices) == 1
    # назавтра, если не починили, напоминает снова
    assert watchdog.check_fingerprints(NOW + timedelta(days=1), **kwargs) == (
        "admin_alerted"
    )
    assert len(notices) == 2


def test_a_new_drift_alerts_immediately_even_on_the_same_day(env):
    home, mapping, state = env
    first = _job("a" * 12, "mariyam_daily_morning")
    second = _job("b" * 12, "mariyam_obligation_reminders")
    _write(home, mapping, [first, second])
    notices = []
    kwargs = dict(
        home=home,
        mapping_path=mapping,
        state_path=state,
        notifier=lambda *args: notices.append(args),
    )

    jobs_path = home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps({"jobs": [dict(first, deliver="telegram:999"), second]}),
        encoding="utf-8",
    )
    assert watchdog.check_fingerprints(NOW, **kwargs) == "admin_alerted"

    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    dict(first, deliver="telegram:999"),
                    dict(second, deliver="telegram:999"),
                ]
            }
        ),
        encoding="utf-8",
    )
    assert watchdog.check_fingerprints(NOW + timedelta(minutes=15), **kwargs) == (
        "admin_alerted"
    )
    assert len(notices) == 2
    assert notices[1][0] == ["mariyam_daily_morning", "mariyam_obligation_reminders"]


def test_a_job_that_vanished_from_jobs_json_is_reported(env):
    home, mapping, state = env
    job = _job("a" * 12, "mariyam_daily_morning")
    _write(home, mapping, [job])
    (home / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": []}), encoding="utf-8"
    )
    notices = []
    result = watchdog.check_fingerprints(
        NOW,
        home=home,
        mapping_path=mapping,
        state_path=state,
        notifier=lambda *args: notices.append(args),
    )
    assert result == "admin_alerted"
    assert notices[0][0] == ["missing:" + "a" * 12]


def test_volatile_run_fields_never_cause_a_false_alarm(env):
    """last_run_at, repeat.completed, снапшоты модели меняются каждый запуск."""
    home, mapping, state = env
    job = _job("a" * 12, "mariyam_daily_morning")
    _write(home, mapping, [job])
    noisy = dict(
        job,
        last_run_at="2026-08-05T08:00:31+05:00",
        last_status="ok",
        repeat={"completed": 99, "times": None},
        model_snapshot="gpt-5.6-luna",
        provider_snapshot="custom",
        next_run_at="2026-08-06T08:00:00+05:00",
        state="scheduled",
    )
    (home / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": [noisy]}), encoding="utf-8"
    )
    notices = []
    assert (
        watchdog.check_fingerprints(
            NOW,
            home=home,
            mapping_path=mapping,
            state_path=state,
            notifier=lambda *args: notices.append(args),
        )
        == "trusted"
    )
    assert notices == []


def test_check_flag_exits_nonzero_on_drift_and_writes_nothing(env, monkeypatch):
    home, mapping, state = env
    job = _job("a" * 12, "mariyam_daily_morning")
    _write(home, mapping, [job])
    (home / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": [dict(job, deliver="telegram:999")]}), encoding="utf-8"
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MARIYAM_CRON_IDENTITY_MAP_FILE", str(mapping))
    monkeypatch.setenv("MARIYAM_WATCHDOG_STATE", str(state))
    monkeypatch.setattr(sys, "argv", ["watchdog", "--check"])

    with pytest.raises(SystemExit) as excinfo:
        watchdog.main()
    assert "mariyam_daily_morning" in str(excinfo.value)
    assert not state.exists(), "--check must not touch watchdog state"


def test_check_flag_is_quiet_and_zero_when_current(env, monkeypatch, capsys):
    home, mapping, state = env
    _write(home, mapping, [_job("a" * 12, "mariyam_daily_morning")])
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MARIYAM_CRON_IDENTITY_MAP_FILE", str(mapping))
    monkeypatch.setenv("MARIYAM_WATCHDOG_STATE", str(state))
    monkeypatch.setattr(sys, "argv", ["watchdog", "--check"])

    watchdog.main()
    assert "current" in capsys.readouterr().out
    assert not state.exists()


def test_fingerprint_check_uses_the_guard_and_not_a_local_copy():
    source = WATCHDOG_PATH.read_text(encoding="utf-8")
    assert "guard.cron_job_fingerprint(job)" in source
    assert "CRON_JOB_FINGERPRINT_FIELDS" not in source, (
        "watchdog must not re-implement the fingerprint: a copy would drift "
        "from the guard and report healthy while the guard refuses"
    )
