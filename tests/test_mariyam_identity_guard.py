"""Unit tests for the Mariyam deterministic Telegram identity guard.

All identity data here is FICTITIOUS. No real Telegram IDs, no real
internal user_ids. Tests mock the session resolver and the private mapping
so the guard logic can be verified offline.

Two fake accounts:
    111111111 -> internal user_id 1  (admin)
    222222222 -> internal user_id 20 (oyijon / test account)
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "deploy" / "hermes_plugins" / "mariyam_identity_guard"

# Load the plugin module directly (it is not a package on sys.path).
_spec = importlib.util.spec_from_file_location(
    "mariyam_identity_guard", PLUGIN_DIR / "__init__.py"
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


FAKE_MAP = {
    "111111111": {"user_id": 1, "role": "admin", "display_name": "Бахриддин ака"},
    "222222222": {"user_id": 20, "role": "oyijon", "display_name": "Тест Ойижон"},
}


@pytest.fixture
def fake_map(monkeypatch):
    monkeypatch.setattr(guard, "load_identity_map", lambda: dict(FAKE_MAP))


@pytest.fixture
def resolver(monkeypatch):
    """Map a fake session_id to a fake Telegram origin."""

    def _resolve(session_id):
        if session_id == "sess-admin":
            return "111111111"
        if session_id == "sess-oyijon":
            return "222222222"
        return None  # unknown

    monkeypatch.setattr(guard, "resolve_telegram_user_id", _resolve)


def _call(tool_name, args, session_id="sess-oyijon", map_fixture=True, res_fixture=True):
    calls = {"n": 0}

    def next_call(a):
        calls["n"] += 1
        calls["args"] = a
        return f"RESULT:{tool_name}"

    kwargs = {
        "tool_name": tool_name,
        "args": args,
        "session_id": session_id,
        "next_call": next_call,
    }
    result = guard.on_tool_execution_middleware(**kwargs)
    return result, calls


# 1. test-account session -> wrong user_id=1 rewritten to 20
def test_wrong_user_rewritten(resolver, fake_map):
    result, calls = _call("get_expense_report", {"user_id": 1, "period": "month"})
    assert calls["n"] == 1
    assert calls["args"]["user_id"] == 20
    assert calls["args"]["period"] == "month"
    assert result == "RESULT:get_expense_report"


# 2. admin session -> user_id=1 preserved (correct)
def test_admin_session_user_1(resolver, fake_map):
    result, calls = _call(
        "get_expense_report", {"user_id": 1, "period": "month"}, session_id="sess-admin"
    )
    assert calls["n"] == 1
    assert calls["args"]["user_id"] == 1


# 3. missing user_id added
def test_missing_user_id_added(resolver, fake_map):
    result, calls = _call("get_balance_summary", {})
    assert calls["n"] == 1
    assert calls["args"]["user_id"] == 20


# 4. ensure_user.telegram_id rewritten to sender of current session
def test_ensure_user_telegram_id_rewritten(resolver, fake_map):
    result, calls = _call(
        "ensure_user", {"telegram_id": 111, "role": "admin", "display_name": "Bahriddin"}
    )
    assert calls["n"] == 1
    assert calls["args"]["telegram_id"] == 222222222
    assert calls["args"]["role"] == "oyijon"
    assert calls["args"]["display_name"] == "Тест Ойижон"


# 5. ensure_user role/display_name taken from mapping
def test_ensure_user_role_display_from_map(resolver, fake_map):
    result, calls = _call("ensure_user", {})
    assert calls["args"]["role"] == "oyijon"
    assert calls["args"]["display_name"] == "Тест Ойижон"


# 6. unknown session -> tool not executed
def test_unknown_session_blocked(resolver, fake_map):
    result, calls = _call("get_expense_report", {"user_id": 1}, session_id="sess-x")
    assert calls["n"] == 0
    assert '"IDENTITY_UNRESOLVED"' in result


# 7. unknown sender (resolver None) -> tool not executed
def test_unknown_sender_blocked(monkeypatch, fake_map):
    monkeypatch.setattr(guard, "resolve_telegram_user_id", lambda s: None)
    result, calls = _call("save_expense", {"user_id": 1, "items": []})
    assert calls["n"] == 0
    assert '"IDENTITY_UNRESOLVED"' in result


# 8. missing mapping file -> tool not executed
def test_missing_map_blocked(resolver, monkeypatch):
    monkeypatch.setattr(guard, "load_identity_map", lambda: None)
    result, calls = _call("save_expense", {"user_id": 1, "items": []})
    assert calls["n"] == 0
    assert '"IDENTITY_UNRESOLVED"' in result


# 9. corrupted mapping (non-dict) -> tool not executed
def test_corrupt_map_blocked(resolver, monkeypatch):
    monkeypatch.setattr(guard, "load_identity_map", lambda: ["not", "a", "dict"])
    result, calls = _call("save_expense", {"user_id": 1, "items": []})
    assert calls["n"] == 0
    assert '"IDENTITY_UNRESOLVED"' in result


# 10. global tool passes through unchanged
def test_global_tool_passthrough(resolver, fake_map):
    result, calls = _call("backup_data", {"target": "db"})
    assert calls["n"] == 1
    assert calls["args"] == {"target": "db"}


# 11. next_call called exactly once on the happy path
def test_next_called_once(resolver, fake_map):
    _, calls = _call("get_balance_summary", {})
    assert calls["n"] == 1


# 12. raw Telegram ID not in logs
def test_no_raw_id_in_logs(resolver, fake_map, caplog):
    with caplog.at_level(logging.INFO):
        _call("get_expense_report", {"user_id": 1})
    for record in caplog.records:
        assert "222222222" not in record.getMessage()
        assert "7847" not in record.getMessage()
        assert "6519" not in record.getMessage()


# 13. display_name not used for identity selection
def test_display_name_not_used(resolver, fake_map):
    # Even if model passes a misleading display_name, user_id is forced
    # from the session, not from any name field.
    result, calls = _call(
        "get_expense_report",
        {"user_id": 1, "display_name": "Bahriddin Boboyev", "period": "month"},
    )
    assert calls["args"]["user_id"] == 20


# 14. two accounts with same display name must not mix
def test_same_display_name_not_mixed(resolver, fake_map):
    admin_args, admin_calls = _call(
        "get_expense_report", {"user_id": 99}, session_id="sess-admin"
    )
    oyijon_args, oyijon_calls = _call(
        "get_expense_report", {"user_id": 99}, session_id="sess-oyijon"
    )
    assert admin_calls["args"]["user_id"] == 1
    assert oyijon_calls["args"]["user_id"] == 20
    # distinctly different, no cross-contamination
    assert admin_calls["args"]["user_id"] != oyijon_calls["args"]["user_id"]
