"""imp12-opus: no-agent replacement for `mariyam_obligation_reminders`.

Two files, two dependency profiles:

- `backend/cron_obligation_reminder.py` — the worker; runs under the
  backend's own venv (asyncpg/mcp available), tested here directly by
  importing the real package (this file lives in `tests/`, so `backend` is
  already importable the normal way).
- `deploy/hermes_profile_mariyam_oyijon/scripts/mariyam_obligation_reminders_cron.py`
  — the thin wrapper Hermes actually executes under its OWN venv (no
  asyncpg there); it shells out to the worker as a subprocess. Loaded via
  importlib and exercised with a stubbed `subprocess.run` so no real
  process or DB is needed.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend import cron_obligation_reminder as mod

REPO = Path(__file__).resolve().parents[1]
WRAPPER_PATH = (
    REPO
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "scripts"
    / "mariyam_obligation_reminders_cron.py"
)


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "mariyam_obligation_reminders_cron_test", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wrapper = _load_wrapper()


def _obligation(**overrides) -> dict:
    base = {
        "obligation_id": 1,
        "name": "Электр",
        "expected_amount_uzs": 300000,
        "due_date": "2026-09-10",
        "reminder_lead_days": 3,
        "active": True,
        "paid": False,
    }
    base.update(overrides)
    return base


# --- worker: pure date-window / message-building logic ----------------------


@pytest.mark.parametrize(
    "today_offset,lead,expected",
    [
        (-3, 3, "advance"),   # today == due - lead
        (0, 3, "due_today"),  # today == due
        (1, 3, "overdue"),    # today == due + 1
        (-4, 3, None),        # too early
        (2, 3, None),         # more than one day late: not this job's concern
    ],
)
def test_classify_three_mutually_exclusive_windows(today_offset, lead, expected):
    due = date(2026, 9, 10)
    today = date(2026, 9, 10 + today_offset)
    obligation = _obligation(due_date=due.isoformat(), reminder_lead_days=lead)
    assert mod.classify(today, obligation) == expected


def test_build_message_is_none_when_nothing_matches():
    today = date(2026, 9, 1)
    obligations = [_obligation(due_date="2026-09-20")]
    assert mod.build_message(today, obligations) is None


def test_build_message_skips_inactive_and_paid_even_if_date_matches():
    today = date(2026, 9, 10)
    obligations = [
        _obligation(due_date="2026-09-10", active=False),
        _obligation(due_date="2026-09-10", paid=True),
    ]
    assert mod.build_message(today, obligations) is None


def test_build_message_combines_multiple_matches_into_one_message():
    today = date(2026, 9, 10)
    obligations = [
        _obligation(name="Электр", due_date="2026-09-10", expected_amount_uzs=300000),
        _obligation(name="Сув", due_date="2026-09-11", reminder_lead_days=1,
                    expected_amount_uzs=45000),
    ]
    message = mod.build_message(today, obligations)
    assert message is not None
    assert message.count(".") == 1  # one message, ends with exactly one full stop
    assert "Электр" in message and "Сув" in message
    assert "300 000" in message and "45 000" in message


def test_amount_is_never_invented_when_missing_or_zero():
    today = date(2026, 9, 10)
    for missing in (None, 0, -5, "не число"):
        obligations = [_obligation(due_date="2026-09-10", expected_amount_uzs=missing)]
        message = mod.build_message(today, obligations)
        assert message is not None
        assert "сум" not in message
        assert "None" not in message


def test_opener_rotates_deterministically_by_day_of_year():
    seen = {
        mod.build_message(date(2026, 9, 10 + i), [
            _obligation(due_date=(date(2026, 9, 10 + i)).isoformat())
        ])
        for i in range(len(mod._OPENERS))
    }
    assert len(seen) > 1


def test_rendered_message_is_pure_uzbek_cyrillic_and_ascii_digits_only():
    today = date(2026, 9, 10)
    obligations = [_obligation(due_date="2026-09-10")]
    message = mod.build_message(today, obligations)
    assert message
    assert not re.search(r"[A-Za-z]", message)
    assert re.search(r"[Ѐ-ӿ]", message)


def test_overdue_window_is_exactly_one_day_not_open_ended():
    """A obligation more than one day late must fall silent, not spam daily."""
    today = date(2026, 9, 12)
    obligation = _obligation(due_date="2026-09-10")  # 2 days late
    assert mod.classify(today, obligation) is None


def test_worker_module_never_needs_a_running_event_loop_at_import_time():
    """Import must succeed without a DB/asyncio context — main() is opt-in."""
    assert hasattr(mod, "main")
    assert callable(mod.main)


# --- wrapper: dependency-free, delegates via subprocess ----------------------


def test_wrapper_has_no_top_level_backend_or_asyncio_imports():
    """The wrapper runs under Hermes' own venv, which has no asyncpg/mcp."""
    source = WRAPPER_PATH.read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("from backend", "import backend", "import asyncpg", "import asyncio")):
            pytest.fail(f"backend/asyncio import must not be top-level: {line!r}")


def test_wrapper_silent_when_backend_root_env_missing(monkeypatch):
    monkeypatch.delenv("MARIYAM_BACKEND_ROOT", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    assert wrapper._run_worker() is None


def test_wrapper_silent_on_nonzero_worker_exit(monkeypatch, tmp_path):
    root = tmp_path / "backend_root"
    (root / "backend").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    fake_python = root / ".venv" / "bin" / "python"
    fake_python.write_text("", encoding="utf-8")
    monkeypatch.setenv("MARIYAM_BACKEND_ROOT", str(root))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    fake_result = MagicMock(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(
        wrapper.subprocess, "run", lambda *a, **k: fake_result
    )
    assert wrapper._run_worker() is None


def test_wrapper_returns_stripped_stdout_on_success(monkeypatch, tmp_path):
    root = tmp_path / "backend_root"
    (root / "backend").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    monkeypatch.setenv("MARIYAM_BACKEND_ROOT", str(root))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    fake_result = MagicMock(returncode=0, stdout="Ойижон, эслатма.\n", stderr="")
    monkeypatch.setattr(
        wrapper.subprocess, "run", lambda *a, **k: fake_result
    )
    assert wrapper._run_worker() == "Ойижон, эслатма."


def test_wrapper_main_never_raises_when_everything_fails(monkeypatch):
    """Whatever goes wrong, main() must not propagate an exception (which
    Hermes would surface as a raw error alert in Oyijon's chat)."""
    monkeypatch.setattr(
        wrapper, "_run_worker", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    wrapper.main()  # must not raise
