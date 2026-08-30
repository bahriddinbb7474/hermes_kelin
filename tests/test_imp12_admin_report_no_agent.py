"""imp12-opus: no-agent replacement for `mariyam_admin_report_1930`.

Pure-function contract for `mariyam_admin_report_cron.py` against the exact
return shape of `backend.db.admin_report_data`. No DB/Hermes runtime needed:
`backend` imports are deferred inside functions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "scripts"
    / "mariyam_admin_report_cron.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "mariyam_admin_report_cron_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load()


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


def test_module_has_no_top_level_backend_imports():
    source = MODULE_PATH.read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("from backend", "import backend", "import asyncpg")):
            pytest.fail(f"backend import must be indented (deferred), got: {line!r}")


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
    # first category (highest sum) must be present, the tail must be cut
    assert "Группа0" in report
    assert f"Группа{mod.TOP_CATEGORIES + 2}" not in report


def test_zero_totals_are_shown_as_zero_not_omitted():
    report = mod.render_report(_data(expense_total_uzs=0, income_total_uzs=0))
    assert "0 сум" in report
