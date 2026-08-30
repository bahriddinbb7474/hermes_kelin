"""imp12-opus: no-agent replacement for `mariyam_obligation_reminders`.

Pure-function contract for `mariyam_obligation_reminders_cron.py`. The
module defers every `backend`/`asyncpg` import inside functions, so it loads
and is fully testable without a live database or Hermes runtime.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "scripts"
    / "mariyam_obligation_reminders_cron.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "mariyam_obligation_reminders_cron_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load()


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


def test_module_has_no_top_level_backend_or_network_imports():
    """The script must stay importable without Hermes/asyncpg installed.

    `backend`/`asyncio` imports are deferred inside functions on purpose
    (module-level import would make even the pure formatting helpers below
    require a live DB driver to test).
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("from backend", "import backend", "import asyncpg")):
            pytest.fail(f"backend import must be indented (deferred), got: {line!r}")


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
    obligations = [_obligation(due_date="2026-09-10")]
    seen = {
        mod.build_message(date(2026, 9, 10 + i), [
            _obligation(due_date=(date(2026, 9, 10 + i)).isoformat())
        ])
        for i in range(len(mod._OPENERS))
    }
    # Not every day must differ (mod arithmetic can repeat for other lengths),
    # but with a run exactly as long as the tuple we must see it exercised
    # beyond a single hardcoded phrase.
    assert len(seen) > 1


def test_rendered_message_is_pure_uzbek_cyrillic_and_ascii_digits_only():
    today = date(2026, 9, 10)
    obligations = [_obligation(due_date="2026-09-10")]
    message = mod.build_message(today, obligations)
    assert message
    # No Latin letters anywhere (SOUL rule 1 applies to every Oyijon-facing
    # surface, not only LLM output).
    assert not re.search(r"[A-Za-z]", message)
    assert re.search(r"[Ѐ-ӿ]", message)


def test_overdue_window_is_exactly_one_day_not_open_ended():
    """A obligation more than one day late must fall silent, not spam daily."""
    today = date(2026, 9, 12)
    obligation = _obligation(due_date="2026-09-10")  # 2 days late
    assert mod.classify(today, obligation) is None
