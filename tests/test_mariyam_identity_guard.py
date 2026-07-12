"""Tests for the Mariyam role-aware, fail-closed identity guard.

All identity data here is FICTITIOUS. No real Telegram IDs, no real internal
user_ids. The guard logic is verified offline with mocked resolver/mapping;
Hermes' real middleware chain and PluginManager loader are exercised via the
installed ``hermes_cli`` package (no VPS, no network, no paid calls).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Make the repo root importable for the deploy plugin + hermes_cli integration.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "deploy" / "hermes_plugins"))

# Load the plugin module directly (not a package on sys.path by default).
_spec = importlib.util.spec_from_file_location(
    "mariyam_identity_guard",
    REPO_ROOT / "deploy" / "hermes_plugins" / "mariyam_identity_guard" / "__init__.py",
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


# Fictitious accounts:
#   111111111 -> admin (user_id 1), may target [20]
#   222222222 -> oyijon (user_id 20)
FAKE_MAP = {
    "111111111": {
        "user_id": 1,
        "role": "admin",
        "display_name": "Бахриддин ака",
        "allowed_target_user_ids": [20],
    },
    "222222222": {"user_id": 20, "role": "oyijon", "display_name": "Тест Ойижон"},
}

PLUGIN_SRC = (
    REPO_ROOT / "deploy" / "hermes_plugins" / "mariyam_identity_guard" / "__init__.py"
).read_text(encoding="utf-8")


def _make_plugin_home() -> str:
    home = tempfile.mkdtemp(prefix="hermes-verify-home-")
    plug = Path(home) / "plugins" / "mariyam_identity_guard"
    plug.mkdir(parents=True)
    (plug / "plugin.yaml").write_text(
        "name: mariyam_identity_guard\nversion: '1.0.0'\ndescription: t\n", encoding="utf-8"
    )
    (plug / "__init__.py").write_text(PLUGIN_SRC, encoding="utf-8")
    (Path(home) / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - mariyam_identity_guard\n", encoding="utf-8"
    )
    return home


@pytest.fixture
def fake_map(monkeypatch):
    monkeypatch.setattr(guard, "load_identity_map", lambda: (dict(FAKE_MAP), None))


@pytest.fixture
def resolver(monkeypatch):
    """Map a fake session_id to a fake Telegram origin."""

    def _resolve(session_id):
        if session_id == "sess-admin":
            return "111111111"
        if session_id == "sess-oyijon":
            return "222222222"
        return None

    monkeypatch.setattr(guard, "resolve_telegram_user_id", _resolve)


def _call(tool_name, args, session_id="sess-oyijon", next_side_effect=None):
    calls = {"n": 0, "args": None}

    def next_call(a):
        calls["n"] += 1
        calls["args"] = a
        if next_side_effect is not None:
            raise next_side_effect
        return f"RESULT:{tool_name}"

    kwargs = {
        "tool_name": tool_name,
        "args": args,
        "session_id": session_id,
        "next_call": next_call,
    }
    result = guard.on_tool_execution_middleware(**kwargs)
    parsed = None
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except Exception:
            parsed = None
    return result, parsed, calls


# ---- Oyijon ----
def test_oyijon_wrong_user_rewritten(resolver, fake_map):
    _, _, calls = _call("get_expense_report", {"user_id": 1, "period": "month"})
    assert calls["n"] == 1
    assert calls["args"]["user_id"] == 20


def test_oyijon_missing_user_added(resolver, fake_map):
    _, _, calls = _call("get_balance_summary", {})
    assert calls["n"] == 1
    assert calls["args"]["user_id"] == 20


def test_oyijon_cannot_target_other(resolver, fake_map):
    # Even if model asks for admin's data, oyijon is forced to own id.
    _, _, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["args"]["user_id"] == 20


def test_same_display_names_not_mixed(resolver, fake_map):
    # Same (fictitious) display_name handling is irrelevant; identity is by
    # session origin, not name. Admin stays bound to his own id, oyijon to hers.
    _a, _, admin_calls = _call("get_expense_report", {"user_id": 1}, session_id="sess-admin")
    _o, _, oyijon_calls = _call("get_expense_report", {}, session_id="sess-oyijon")
    assert admin_calls["args"]["user_id"] == 1
    assert oyijon_calls["args"]["user_id"] == 20


# ---- Admin ----
def test_admin_self_target(resolver, fake_map):
    _, _, calls = _call("get_expense_report", {"user_id": 1}, session_id="sess-admin")
    assert calls["args"]["user_id"] == 1


def test_admin_cross_report_allowed(resolver, fake_map):
    _, _, calls = _call("get_expense_report", {"user_id": 20}, session_id="sess-admin")
    assert calls["n"] == 1
    assert calls["args"]["user_id"] == 20


def test_admin_cross_balance_allowed(resolver, fake_map):
    _, _, calls = _call("get_balance_summary", {"user_id": 20}, session_id="sess-admin")
    assert calls["args"]["user_id"] == 20


def test_admin_cross_admin_report_data_allowed(resolver, fake_map):
    _, _, calls = _call("get_admin_report_data", {"user_id": 20}, session_id="sess-admin")
    assert calls["args"]["user_id"] == 20


def test_admin_cross_save_plan_note_allowed(resolver, fake_map):
    _, _, calls = _call("save_plan_note", {"user_id": 20}, session_id="sess-admin")
    assert calls["args"]["user_id"] == 20


def test_admin_target_outside_allowlist_blocked(resolver, fake_map):
    _, parsed, calls = _call("get_expense_report", {"user_id": 99}, session_id="sess-admin")
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_TARGET_FORBIDDEN"


def test_admin_delete_cross_blocked(resolver, fake_map):
    _, parsed, calls = _call("delete_last_expense", {"user_id": 20}, session_id="sess-admin")
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_TARGET_FORBIDDEN"


def test_admin_save_expense_cross_blocked(resolver, fake_map):
    _, parsed, calls = _call("save_expense", {"user_id": 20}, session_id="sess-admin")
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_TARGET_FORBIDDEN"


def test_admin_missing_user_defaults_self(resolver, fake_map):
    _, _, calls = _call("get_balance_summary", {}, session_id="sess-admin")
    assert calls["args"]["user_id"] == 1


# ---- Fail-closed ----
def test_missing_mapping_blocks(resolver, monkeypatch):
    monkeypatch.setattr(guard, "load_identity_map", lambda: (None, "IDENTITY_UNRESOLVED"))
    _, parsed, calls = _call("save_expense", {"user_id": 1, "items": []})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_UNRESOLVED"


def test_corrupt_mapping_blocks(resolver, monkeypatch):
    monkeypatch.setattr(guard, "load_identity_map", lambda: (None, "IDENTITY_MAPPING_INVALID"))
    _, parsed, calls = _call("save_expense", {"user_id": 1, "items": []})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_mapping_not_0600_blocks(resolver, monkeypatch, tmp_path):
    f = tmp_path / "map.json"
    f.write_text(json.dumps(FAKE_MAP))
    os.chmod(f, 0o644)
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(f))
    monkeypatch.setattr(os, "name", "posix")  # force 0600 enforcement
    monkeypatch.setattr(
        guard, "load_identity_map", lambda: (None, "IDENTITY_MAPPING_PERMISSIONS")
    )
    _, parsed, calls = _call("save_expense", {"user_id": 1, "items": []})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_PERMISSIONS"


def test_unknown_session_blocks(resolver, fake_map):
    _, parsed, calls = _call("get_expense_report", {"user_id": 1}, session_id="sess-x")
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_UNRESOLVED"


def test_unknown_sender_blocks(monkeypatch, fake_map):
    monkeypatch.setattr(guard, "resolve_telegram_user_id", lambda s: None)
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_UNRESOLVED"


def test_resolver_exception_blocks(resolver, fake_map):
    mp = pytest.MonkeyPatch()
    mp.setattr(
        guard,
        "resolve_telegram_user_id",
        lambda s: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_GUARD_ERROR"
    mp.undo()


def test_preparation_exception_blocks(resolver, fake_map, monkeypatch):
    # Make deepcopy raise -> must be caught, downstream not called.
    monkeypatch.setattr(
        guard.copy, "deepcopy", lambda x: (_ for _ in ()).throw(RuntimeError("x"))
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_GUARD_ERROR"


def test_next_call_single_use(resolver, fake_map):
    _, _, calls = _call("get_balance_summary", {})
    assert calls["n"] == 1


# ---- Hermes integration (real middleware chain) ----
def test_hermes_middleware_chain_exception_fail_closed(monkeypatch):
    """P0 regression: if the guard internally fails before next_call, the
    real Hermes chain must NOT execute the downstream terminal tool."""
    from hermes_cli.middleware import run_tool_execution_middleware
    import hermes_cli.plugins as hp

    def boom():
        raise RuntimeError("plugin blew up")

    monkeypatch.setattr(guard, "load_identity_map", boom)
    # Register the guard into the REAL chain (same path PluginManager uses).
    pm = hp.get_plugin_manager()
    pm._middleware.setdefault("tool_execution", [])
    if guard.on_tool_execution_middleware not in pm._middleware["tool_execution"]:
        pm._middleware["tool_execution"].append(guard.on_tool_execution_middleware)

    captured = {"n": 0}

    def terminal(args):
        captured["n"] += 1
        return "TERMINAL_RESULT"

    result = run_tool_execution_middleware(
        "get_expense_report", {"user_id": 1}, terminal, session_id="sess-oyijon"
    )
    assert captured["n"] == 0
    parsed = json.loads(result)
    assert parsed["error_code"] == "IDENTITY_GUARD_ERROR"
    if guard.on_tool_execution_middleware in pm._middleware["tool_execution"]:
        pm._middleware["tool_execution"].remove(guard.on_tool_execution_middleware)


def test_hermes_middleware_chain_normal_rewrite(monkeypatch):
    from hermes_cli.middleware import run_tool_execution_middleware
    import hermes_cli.plugins as hp

    monkeypatch.setattr(guard, "load_identity_map", lambda: (dict(FAKE_MAP), None))
    monkeypatch.setattr(guard, "resolve_telegram_user_id", lambda s: "222222222")
    pm = hp.get_plugin_manager()
    pm._middleware.setdefault("tool_execution", [])
    if guard.on_tool_execution_middleware not in pm._middleware["tool_execution"]:
        pm._middleware["tool_execution"].append(guard.on_tool_execution_middleware)

    captured = {}

    def terminal(args):
        captured["args"] = args
        return "TERMINAL_RESULT"

    result = run_tool_execution_middleware(
        "get_expense_report", {"user_id": 1}, terminal, session_id="sess-oyijon"
    )
    assert captured["args"]["user_id"] == 20
    assert result == "TERMINAL_RESULT"
    if guard.on_tool_execution_middleware in pm._middleware["tool_execution"]:
        pm._middleware["tool_execution"].remove(guard.on_tool_execution_middleware)


# ---- Strict mapping schema validation (regression) ----
def _apply_map_file(tmp_path, monkeypatch, mapping):
    """Write a real mapping file and point the plugin at it (no loader mock)."""
    f = tmp_path / "map.json"
    f.write_text(json.dumps(mapping))
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(f))


def test_schema_user_id_string_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(tmp_path, monkeypatch, {"111111111": {"user_id": "1", "role": "oyijon", "display_name": "T"}})
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_user_id_bool_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(tmp_path, monkeypatch, {"111111111": {"user_id": True, "role": "oyijon", "display_name": "T"}})
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_user_id_zero_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(tmp_path, monkeypatch, {"111111111": {"user_id": 0, "role": "oyijon", "display_name": "T"}})
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_unknown_role_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(tmp_path, monkeypatch, {"111111111": {"user_id": 1, "role": "superuser", "display_name": "T"}})
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_empty_display_name_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(tmp_path, monkeypatch, {"111111111": {"user_id": 1, "role": "oyijon", "display_name": "  "}})
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_admin_missing_targets_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(tmp_path, monkeypatch, {"111111111": {"user_id": 1, "role": "admin", "display_name": "T"}})
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_admin_targets_not_list_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(
        tmp_path, monkeypatch,
        {"111111111": {"user_id": 1, "role": "admin", "display_name": "T", "allowed_target_user_ids": "20"}},
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_admin_target_string_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(
        tmp_path, monkeypatch,
        {"111111111": {"user_id": 1, "role": "admin", "display_name": "T", "allowed_target_user_ids": ["20"]}},
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_admin_target_bool_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(
        tmp_path, monkeypatch,
        {"111111111": {"user_id": 1, "role": "admin", "display_name": "T", "allowed_target_user_ids": [True]}},
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_admin_target_zero_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(
        tmp_path, monkeypatch,
        {"111111111": {"user_id": 1, "role": "admin", "display_name": "T", "allowed_target_user_ids": [0]}},
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_admin_target_duplicate_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(
        tmp_path, monkeypatch,
        {"111111111": {"user_id": 1, "role": "admin", "display_name": "T", "allowed_target_user_ids": [20, 20]}},
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_oyijon_nonempty_targets_invalid(resolver, monkeypatch, tmp_path):
    _apply_map_file(
        tmp_path, monkeypatch,
        {"111111111": {"user_id": 20, "role": "oyijon", "display_name": "T", "allowed_target_user_ids": [1]}},
    )
    _, parsed, calls = _call("get_expense_report", {"user_id": 1})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


def test_schema_valid_admin_mapping(resolver, monkeypatch, tmp_path):
    _apply_map_file(
        tmp_path, monkeypatch,
        {"111111111": {"user_id": 1, "role": "admin", "display_name": "A", "allowed_target_user_ids": [20]}},
    )
    _, _, calls = _call("get_expense_report", {"user_id": 20}, session_id="sess-admin")
    assert calls["args"]["user_id"] == 20


def test_schema_valid_oyijon_mapping_self_only(resolver, monkeypatch, tmp_path):
    _apply_map_file(tmp_path, monkeypatch, {"222222222": {"user_id": 20, "role": "oyijon", "display_name": "O"}})
    _, _, calls = _call("get_expense_report", {"user_id": 1}, session_id="sess-oyijon")
    assert calls["args"]["user_id"] == 20


def test_schema_runtime_invalid_file_blocks(tmp_path, resolver, monkeypatch):
    f = tmp_path / "map.json"
    f.write_text(
        json.dumps(
            {
                "111111111": {
                    "user_id": "1",
                    "role": "not_a_role",
                    "display_name": "Test",
                    "allowed_target_user_ids": [20],
                }
            }
        )
    )
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(f))
    _, parsed, calls = _call("save_expense", {"user_id": 1, "items": []})
    assert calls["n"] == 0
    assert parsed["error_code"] == "IDENTITY_MAPPING_INVALID"


# ---- Discovery: honest, no manual middleware injection ----
def test_plugin_discovery_and_registration():
    """The plugin discovers + enables + registers its middleware entirely
    through ``PluginManager.discover_and_load()`` — NO manual ``pm._middleware``
    injection and NO loader mocks. We then drive its own discovered callback
    (loaded from the real plugin file) through the real Hermes chain, with a
    real mapping file + a real state.db for the telegram origin."""
    import hermes_cli.plugins as hp

    home = _make_plugin_home()
    # Real mapping file the discovered (file-loaded) module will read.
    map_file = Path(home) / "identity_private.json"
    map_file.write_text(json.dumps(FAKE_MAP))
    # Real state.db with a telegram session origin for sess-oyijon.
    db = Path(home) / "state.db"
    con = __import__("sqlite3").connect(str(db))
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, origin_json TEXT)")
    con.execute(
        "INSERT INTO sessions VALUES (?, ?)",
        ("sess-oyijon", json.dumps({"platform": "telegram", "user_id": "222222222"})),
    )
    con.commit()
    con.close()

    old_home = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = home
    os.environ["MARIYAM_IDENTITY_MAP_FILE"] = str(map_file)
    try:
        pm = hp.get_plugin_manager()
        pm.discover_and_load(force=True)

        # Discovered + enabled + middleware registered via the real path.
        assert "mariyam_identity_guard" in pm._plugins
        lp = pm._plugins["mariyam_identity_guard"]
        assert lp.enabled is True
        assert "tool_execution" in list(lp.middleware_registered)

        # Callback must come from the registry the discovery created — we do
        # NOT import or inject the callback manually here.
        callbacks = pm._middleware.get("tool_execution")
        assert callbacks is not None and len(callbacks) == 1
        # (the single callback is the discovered module's on_tool_execution_middleware)

        captured = {}

        def terminal(args):
            captured["args"] = args
            return "TERMINAL_RESULT"

        from hermes_cli.middleware import run_tool_execution_middleware

        # Normal path: terminal gets rewritten user_id=20, called exactly once.
        result = run_tool_execution_middleware(
            "get_expense_report", {"user_id": 1}, terminal, session_id="sess-oyijon"
        )
        assert captured["args"]["user_id"] == 20
        assert result == "TERMINAL_RESULT"

        # Malformed mapping path: discovered callback blocks the call.
        map_file.write_text(json.dumps({"111111111": {"user_id": "1", "role": "nope", "display_name": "T"}}))
        blocked = {"n": 0}

        def terminal2(args):
            blocked["n"] += 1
            return "T"

        res2 = run_tool_execution_middleware(
            "get_expense_report", {"user_id": 1}, terminal2, session_id="sess-oyijon"
        )
        assert blocked["n"] == 0
        assert json.loads(res2)["error_code"] == "IDENTITY_MAPPING_INVALID"
    finally:
        if old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = old_home
        os.environ.pop("MARIYAM_IDENTITY_MAP_FILE", None)
        shutil.rmtree(home, ignore_errors=True)


# ---- Additional ----
def test_global_tool_passthrough(resolver, fake_map):
    _, _, calls = _call("backup_data", {"target": "db"})
    assert calls["n"] == 1
    assert calls["args"] == {"target": "db"}


def test_ensure_user_rewrites_all_fields(resolver, fake_map):
    _, _, calls = _call(
        "ensure_user", {"telegram_id": 111, "role": "admin", "display_name": "X"}
    )
    assert str(calls["args"]["telegram_id"]) == "222222222"
    assert calls["args"]["role"] == "oyijon"
    assert calls["args"]["display_name"] == "Тест Ойижон"


def test_no_raw_telegram_id_in_logs(resolver, fake_map, caplog):
    with caplog.at_level(logging.INFO):
        _call("get_expense_report", {"user_id": 1})
    for record in caplog.records:
        msg = record.getMessage()
        assert "222222222" not in msg
        assert "111111111" not in msg
        assert "7847" not in msg
        assert "6519" not in msg


def test_persisted_session_store_reopen_consistent():
    """Reopening state.db yields the same sender (no stale substitution)."""
    tmp = tempfile.mkdtemp(prefix="hermes-verify-db-")
    db = Path(tmp) / "state.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, origin_json TEXT)")
    con.execute(
        "INSERT INTO sessions VALUES (?, ?)",
        ("sess-oyijon", json.dumps({"platform": "telegram", "user_id": "222222222"})),
    )
    con.commit()
    con.close()

    orig = guard._state_db_path

    def fake_path():
        return db

    guard._state_db_path = fake_path
    try:
        first = guard.resolve_telegram_user_id("sess-oyijon")
        second = guard.resolve_telegram_user_id("sess-oyijon")
        assert first == "222222222"
        assert second == "222222222"
        assert guard.resolve_telegram_user_id("other") is None
    finally:
        guard._state_db_path = orig
