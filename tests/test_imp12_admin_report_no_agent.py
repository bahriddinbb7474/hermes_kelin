"""imp12-opus: no-agent replacement for `mariyam_admin_report_1930`.

Same split as the obligation-reminder job: `backend/cron_admin_report.py` is
the worker (runs under the backend venv, tested here by importing the real
package), `deploy/hermes_profile_mariyam_oyijon/scripts/mariyam_admin_report_cron.py`
is the thin wrapper Hermes executes under its own (asyncpg-less) venv and
shells out to the worker as a subprocess.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend import cron_admin_report as mod

REPO = Path(__file__).resolve().parents[1]
WRAPPER_PATH = (
    REPO
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "scripts"
    / "mariyam_admin_report_cron.py"
)


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "mariyam_admin_report_cron_test", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wrapper = _load_wrapper()


def _data(**overrides) -> dict:
    base = {
        "date": "2026-08-30",
        "month": "2026-08-01",
        "expense_total_uzs": 45000,
        "income_total_uzs": 0,
        "month_expense_total_uzs": 1712208,
        "month_income_total_uzs": 2300000,
        "month_expense_by_category": [
            {"category_code": "food", "name_uz": "Озиқ-овқат", "sum_uzs": 739700},
            {"category_code": "utilities", "name_uz": "Коммунал", "sum_uzs": 300000},
        ],
        "plan": {
            "status": "waiting_oyijon",
            "source": "auto",
            "household_size": 1,
            "planned_total_uzs": 4356000,
            "actual_total_uzs": 1712208,
            "remaining_uzs": 2643792,
        },
        "due_obligations": [],
        "due_obligations_through": "2026-09-06",
        "alerts": [],
    }
    base.update(overrides)
    return base


# --- worker: pure formatting logic -------------------------------------------


def test_report_uses_only_tool_numbers_nothing_invented():
    data = _data()
    report = mod.render_report(data)
    assert "45 000" in report
    assert "1 712 208" in report
    assert "2 300 000" in report
    assert "waiting_oyijon" in report
    assert "2 643 792" in report


def test_report_shows_uzbek_category_names_inside_russian_scaffolding():
    report = mod.render_report(_data())
    assert "Озиқ-овқат" in report
    assert "Коммунал" in report


def test_no_health_note_text_or_diagnoses_can_leak():
    """admin_report_data never returns raw health text; assert the renderer
    does not reference any such field even if one were added later."""
    data = _data()
    data["health_notes"] = [{"note": "секрет", "severity": "high"}]
    report = mod.render_report(data)
    assert "секрет" not in report


def test_obligations_render_with_overdue_flag_and_no_invented_amounts():
    data = _data(
        due_obligations=[
            {
                "obligation_type": "utility",
                "name": "Сув",
                "expected_amount_uzs": 45000,
                "due_date": "2026-08-28",
                "overdue": True,
            },
            {
                "obligation_type": "utility",
                "name": "Электр",
                "expected_amount_uzs": 300000,
                "due_date": "2026-09-05",
                "overdue": False,
            },
        ]
    )
    report = mod.render_report(data)
    assert "Сув" in report and "просрочено" in report
    assert "Электр" in report
    assert "300 000" in report and "45 000" in report


def test_no_obligations_says_so_explicitly_not_silence():
    report = mod.render_report(_data(due_obligations=[]))
    assert "Обязательства: нет" in report


def test_alerts_summarize_severity_counts_and_admin_delivery():
    data = _data(
        alerts=[
            {"alert_type": "medical", "severity": "critical", "detected_by": "keyword",
             "sent_to_admin": True, "created_at": "2026-08-30T05:00:00Z"},
            {"alert_type": "medical", "severity": "low", "detected_by": "keyword",
             "sent_to_admin": False, "created_at": "2026-08-30T06:00:00Z"},
        ]
    )
    report = mod.render_report(data)
    assert "critical" in report and "low" in report
    assert "админу доставлено: 1" in report


def test_no_alerts_says_so_explicitly():
    report = mod.render_report(_data(alerts=[]))
    assert "Alerts за день: нет" in report


def test_category_list_is_capped_with_ellipsis_when_long():
    many = [
        {"category_code": f"c{i}", "name_uz": f"Группа{i}", "sum_uzs": 1000 * (10 - i)}
        for i in range(mod.TOP_CATEGORIES + 3)
    ]
    report = mod.render_report(_data(month_expense_by_category=many))
    assert "…" in report
    assert "Группа0" in report
    assert f"Группа{mod.TOP_CATEGORIES + 2}" not in report


def test_zero_totals_are_shown_as_zero_not_omitted():
    report = mod.render_report(_data(expense_total_uzs=0, income_total_uzs=0))
    assert "0 сум" in report


# --- wrapper: dependency-free, delegates via subprocess, never silent -------


def test_wrapper_has_no_top_level_backend_or_asyncio_imports():
    source = WRAPPER_PATH.read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("from backend", "import backend", "import asyncpg", "import asyncio")):
            pytest.fail(f"backend/asyncio import must not be top-level: {line!r}")


def test_wrapper_reports_missing_backend_root_instead_of_silence(monkeypatch):
    monkeypatch.delenv("MARIYAM_BACKEND_ROOT", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    message, reason = wrapper._run_worker()
    assert message is None
    assert reason  # non-empty: admin gets a reason, never bare silence


def test_wrapper_reports_worker_failure_with_stderr_tail(monkeypatch, tmp_path):
    root = tmp_path / "backend_root"
    (root / "backend").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    monkeypatch.setenv("MARIYAM_BACKEND_ROOT", str(root))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    fake_result = MagicMock(returncode=1, stdout="", stderr="Traceback...\nRuntimeError: db down")
    monkeypatch.setattr(wrapper.subprocess, "run", lambda *a, **k: fake_result)
    message, reason = wrapper._run_worker()
    assert message is None
    assert "RuntimeError" in reason


def test_wrapper_returns_stdout_on_success(monkeypatch, tmp_path):
    root = tmp_path / "backend_root"
    (root / "backend").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    monkeypatch.setenv("MARIYAM_BACKEND_ROOT", str(root))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    fake_result = MagicMock(returncode=0, stdout="Отчёт за ...\n", stderr="")
    monkeypatch.setattr(wrapper.subprocess, "run", lambda *a, **k: fake_result)
    message, reason = wrapper._run_worker()
    assert message == "Отчёт за ..."
    assert reason == ""


def test_wrapper_main_never_raises_and_always_prints_something(monkeypatch, capsys):
    """Unlike the Oyijon-facing job, admin must never get bare silence."""
    monkeypatch.setattr(
        wrapper, "_run_worker", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    wrapper.main()  # must not raise
    out = capsys.readouterr().out
    assert out.strip()
    assert "RuntimeError" in out
