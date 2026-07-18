"""Permanent tests for the profile-scoped Stage 5.3 execution guard.

All identities and session ids are fictitious.  The plugin is tested through
Hermes' structured ``tool_execution`` contract; user text is never inspected.
"""
from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = (
    REPO_ROOT / "deploy" / "hermes_plugins" / "mariyam_stage53_guard"
)
PLUGIN_PATH = PLUGIN_DIR / "__init__.py"
MANIFEST_PATH = PLUGIN_DIR / "plugin.yaml"
CONFIG_SNIPPET = (
    REPO_ROOT
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "config.skill-protect.snippet.yaml"
)
IDENTITY_MANIFEST = (
    REPO_ROOT
    / "deploy"
    / "hermes_plugins"
    / "mariyam_identity_guard"
    / "plugin.yaml"
)

_spec = importlib.util.spec_from_file_location("mariyam_stage53_guard", PLUGIN_PATH)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _multiprocess_duplicate_worker(state_path, start_event, downstream_count, results):
    os.environ["MARIYAM_STAGE53_STATE_FILE"] = state_path
    start_event.wait(timeout=5)

    def next_call(_effective_args):
        with downstream_count.get_lock():
            downstream_count.value += 1
        time.sleep(0.2)
        return _result(saved=True)

    value = guard.on_tool_execution_middleware(
        tool_name="save_expense",
        args={"user_id": 20, "amount": 100},
        session_id="shared-session",
        turn_id="shared-turn",
        next_call=next_call,
    )
    parsed = json.loads(value) if isinstance(value, str) else value
    results.put(parsed.get("error_code", "ok"))


def _result(**payload):
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _lookup_args(*, user_id=20, month="2026-07-01", name="кир совуни", unit="pcs"):
    return {
        "user_id": user_id,
        "month": month,
        "price_lookup_items": [
            {
                "item_name_normalized": name,
                "unit": unit,
                "price_basis": "last",
            }
        ],
    }


def _lookup_result(*, name="кир совуни", unit="pcs", price=12000):
    return _result(
        price_lookup=[
            {
                "item_name_normalized": name,
                "unit": unit,
                "last_unit_price_uzs": price,
                "last_price_as_of": "2026-07-01T10:00:00Z",
                "average_unit_price_uzs": price,
                "priced_purchase_count": 1,
                "price_basis": "last",
                "reference_unit_price_uzs": price,
                "price_as_of": "2026-07-01T10:00:00Z",
            }
        ]
    )


def _product_save_args(
    *,
    user_id=20,
    month="2026-07-01",
    name="кир совуни",
    unit="pcs",
    price=12000,
    basis="last",
    price_as_of="2026-07-01T10:00:00Z",
):
    return {
        "user_id": user_id,
        "month": month,
        "category_code": "home",
        "planned_amount_uzs": 48000,
        "items": [
            {
                "item_name_normalized": name,
                "item_name_display": "Кир совуни",
                "planned_quantity": 4,
                "unit": unit,
                "planned_amount_uzs": 48000,
                "reference_unit_price_uzs": price,
                "price_basis": basis,
                "price_as_of": price_as_of,
            }
        ],
    }


def _invoke(
    tool_name,
    args,
    *,
    session_id="session-a",
    turn_id="turn-a",
    downstream_result=None,
    counter=None,
):
    if counter is None:
        counter = {"count": 0}
    if downstream_result is None:
        downstream_result = _result(saved=True)

    def next_call(effective_args):
        counter["count"] += 1
        counter["args"] = effective_args
        return downstream_result

    value = guard.on_tool_execution_middleware(
        tool_name=tool_name,
        args=args,
        session_id=session_id,
        turn_id=turn_id,
        next_call=next_call,
    )
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed, counter


@pytest.fixture(autouse=True)
def private_state(tmp_path, monkeypatch):
    state_path = tmp_path / "private" / "stage53-state.json"
    monkeypatch.setenv("MARIYAM_STAGE53_STATE_FILE", str(state_path))
    monkeypatch.setattr(guard, "_utc_timestamp", lambda: 1_000_000.0)
    yield state_path


def _arm(session_id="session-a", user_id=20):
    result, calls = _invoke(
        "mcp__mariyam_backend__get_monthly_budget_status",
        _lookup_args(user_id=user_id),
        session_id=session_id,
        turn_id="lookup-turn",
        downstream_result=_lookup_result(),
    )
    assert result["ok"] is True
    assert calls["count"] == 1


def test_manifest_and_mutation_scope_are_exact():
    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "name: mariyam_stage53_guard" in manifest
    assert "version: \"1.0.0\"" in manifest
    assert guard.MUTATING_TOOLS == frozenset(
        {
            "set_monthly_budget",
            "save_expense",
            "update_expense",
            "update_last_expense",
            "delete_last_expense",
            "save_health_note",
            "save_plan_note",
        }
    )


@pytest.mark.parametrize("tool_name", sorted(guard.MUTATING_TOOLS))
def test_each_scoped_mutation_blocks_second_identical_success(tool_name):
    counter = {"count": 0}
    args = {"user_id": 20, "marker": tool_name}
    first, _ = _invoke(tool_name, args, turn_id="same-turn", counter=counter)
    second, _ = _invoke(tool_name, args, turn_id="same-turn", counter=counter)
    assert first["ok"] is True
    assert second["error_code"] == "DUPLICATE_SUCCESS_BLOCKED"
    assert counter["count"] == 1


def test_profile_limit_plugin_order_and_identity_version_are_pinned():
    snippet = CONFIG_SNIPPET.read_text(encoding="utf-8")
    assert "max_turns: 6" in snippet
    assert snippet.index("- mariyam_identity_guard") < snippet.index(
        "- mariyam_stage53_guard"
    )
    identity_manifest = IDENTITY_MANIFEST.read_text(encoding="utf-8")
    assert 'version: "1.0.4"' in identity_manifest


def test_active_lookup_plus_omitted_items_is_blocked():
    _arm()
    args = _product_save_args()
    del args["items"]
    result, calls = _invoke("set_monthly_budget", args, turn_id="save-turn")
    assert result["ok"] is False
    assert result["error_code"] == "PRODUCT_ITEMS_REQUIRED"
    assert calls["count"] == 0


def test_active_lookup_plus_empty_items_is_blocked():
    _arm()
    args = _product_save_args()
    args["items"] = []
    result, calls = _invoke("set_monthly_budget", args, turn_id="save-turn")
    assert result["error_code"] == "PRODUCT_ITEMS_REQUIRED"
    assert calls["count"] == 0


def test_active_lookup_plus_matching_product_payload_passes_and_clears_state():
    _arm()
    result, calls = _invoke(
        "set_monthly_budget",
        _product_save_args(),
        turn_id="save-turn",
        downstream_result=_result(plan_id=7, created=True),
    )
    assert result["ok"] is True
    assert calls["count"] == 1

    category_only = _product_save_args()
    del category_only["items"]
    after, after_calls = _invoke(
        "set_monthly_budget", category_only, turn_id="later-turn"
    )
    assert after["ok"] is True
    assert after_calls["count"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("item_name_normalized", "кир кукуни"),
        ("unit", "pack"),
        ("reference_unit_price_uzs", 13000),
        ("price_basis", "average"),
        ("price_as_of", "2026-07-02T10:00:00Z"),
    ],
)
def test_active_lookup_mismatch_is_blocked(field, value):
    _arm()
    args = _product_save_args()
    args["items"][0][field] = value
    result, calls = _invoke("set_monthly_budget", args, turn_id="save-turn")
    assert result["ok"] is False
    assert result["error_code"] == "PRODUCT_LOOKUP_MISMATCH"
    assert calls["count"] == 0


def test_active_lookup_rejects_unbound_extra_item():
    _arm()
    args = _product_save_args()
    args["items"].append(
        {
            "item_name_normalized": "гуруч",
            "item_name_display": "Гуруч",
            "planned_quantity": 1,
            "unit": "kg",
            "planned_amount_uzs": 20000,
            "reference_unit_price_uzs": 20000,
            "price_basis": "last",
            "price_as_of": "2026-07-01T10:00:00Z",
        }
    )
    result, calls = _invoke("set_monthly_budget", args, turn_id="save-turn")
    assert result["error_code"] == "PRODUCT_LOOKUP_MISMATCH"
    assert calls["count"] == 0


def test_active_state_expires_after_thirty_minutes(monkeypatch):
    _arm()
    monkeypatch.setattr(guard, "_utc_timestamp", lambda: 1_001_801.0)
    args = _product_save_args()
    del args["items"]
    result, calls = _invoke("set_monthly_budget", args, turn_id="later-turn")
    assert result["ok"] is True
    assert calls["count"] == 1


def test_session_reset_removes_old_session_state():
    _arm(session_id="old-session")
    guard.on_session_reset(session_id="old-session")
    args = _product_save_args()
    del args["items"]
    result, calls = _invoke(
        "set_monthly_budget", args, session_id="old-session", turn_id="save-turn"
    )
    assert result["ok"] is True
    assert calls["count"] == 1


def test_identical_successful_mutation_calls_downstream_once():
    counter = {"count": 0}
    args = {"user_id": 20, "items": [{"amount_uzs": 12000}]}
    first, _ = _invoke(
        "save_expense", args, turn_id="same-turn", counter=counter
    )
    second, _ = _invoke(
        "save_expense", args, turn_id="same-turn", counter=counter
    )
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error_code"] == "DUPLICATE_SUCCESS_BLOCKED"
    assert "заверш" in second["message_ru"].casefold()
    assert counter["count"] == 1


def test_posix_concurrent_processes_claim_before_downstream(private_state):
    if os.name != "posix":
        return
    private_state.parent.mkdir(mode=0o700)
    private_state.parent.chmod(0o700)
    context = multiprocessing.get_context("fork")
    start_event = context.Event()
    downstream_count = context.Value("i", 0)
    results = context.Queue()
    workers = [
        context.Process(
            target=_multiprocess_duplicate_worker,
            args=(str(private_state), start_event, downstream_count, results),
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    start_event.set()
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0
    outcomes = sorted(results.get(timeout=2) for _ in workers)
    assert downstream_count.value == 1
    assert outcomes == ["DUPLICATE_SUCCESS_BLOCKED", "ok"]


def test_different_mutation_args_are_not_duplicates():
    counter = {"count": 0}
    _invoke(
        "save_expense",
        {"user_id": 20, "amount": 100},
        turn_id="same-turn",
        counter=counter,
    )
    second, _ = _invoke(
        "save_expense",
        {"amount": 200, "user_id": 20},
        turn_id="same-turn",
        counter=counter,
    )
    assert second["ok"] is True
    assert counter["count"] == 2


def test_failed_mutation_is_not_recorded_as_success():
    counter = {"count": 0}
    failure = json.dumps({"ok": False, "error_code": "INVALID_INPUT"})
    args = {"user_id": 20, "amount": 100}
    _invoke(
        "save_expense",
        args,
        turn_id="same-turn",
        counter=counter,
        downstream_result=failure,
    )
    second, _ = _invoke(
        "save_expense", args, turn_id="same-turn", counter=counter
    )
    assert second["ok"] is True
    assert counter["count"] == 2


def test_post_success_ledger_failure_does_not_allow_second_downstream(
    monkeypatch,
):
    counter = {"count": 0}
    args = {"user_id": 20, "amount": 100}

    def fail_record(*_args, **_kwargs):
        raise OSError("simulated ledger write failure")

    monkeypatch.setattr(guard, "_record_success", fail_record)
    first, _ = _invoke(
        "save_expense", args, turn_id="same-turn", counter=counter
    )
    second, _ = _invoke(
        "save_expense", args, turn_id="same-turn", counter=counter
    )
    assert first["ok"] is True
    assert second["error_code"] == "DUPLICATE_SUCCESS_BLOCKED"
    assert counter["count"] == 1


def test_downstream_exception_keeps_claim_for_unknown_mutation_outcome():
    counter = {"count": 0}
    args = {"user_id": 20, "amount": 100}

    def raises_after_possible_mutation(_effective_args):
        counter["count"] += 1
        raise RuntimeError("unknown downstream outcome")

    with pytest.raises(RuntimeError, match="unknown downstream outcome"):
        guard.on_tool_execution_middleware(
            tool_name="save_expense",
            args=args,
            session_id="session-a",
            turn_id="same-turn",
            next_call=raises_after_possible_mutation,
        )
    second, _ = _invoke(
        "save_expense", args, turn_id="same-turn", counter=counter
    )
    assert second["error_code"] == "DUPLICATE_SUCCESS_BLOCKED"
    assert counter["count"] == 1


def test_sessions_and_trusted_users_are_isolated():
    counter = {"count": 0}
    _invoke(
        "save_expense",
        {"user_id": 20, "amount": 100},
        session_id="session-a",
        turn_id="same-turn",
        counter=counter,
    )
    second, _ = _invoke(
        "save_expense",
        {"user_id": 21, "amount": 100},
        session_id="session-b",
        turn_id="same-turn",
        counter=counter,
    )
    assert second["ok"] is True
    assert counter["count"] == 2


def test_private_state_file_is_mode_0600(private_state):
    _arm()
    if os.name == "posix":
        assert private_state.stat().st_mode & 0o777 == 0o600


def test_posix_state_write_fsyncs_file_and_parent(private_state, monkeypatch):
    if os.name != "posix":
        return
    fsync_calls = []
    monkeypatch.setattr(guard.os, "fsync", lambda fd: fsync_calls.append(fd))
    _arm()
    assert len(fsync_calls) >= 2


def test_posix_permissive_state_parent_fails_closed(private_state):
    if os.name != "posix":
        return
    private_state.parent.mkdir(mode=0o755)
    private_state.parent.chmod(0o755)
    result, _calls = _invoke(
        "get_monthly_budget_status",
        _lookup_args(),
        downstream_result=_lookup_result(),
    )
    assert result["error_code"] == "STAGE53_GUARD_ERROR"
    assert not private_state.exists()


def test_posix_symlink_state_file_fails_closed(private_state):
    if os.name != "posix":
        return
    private_state.parent.mkdir(mode=0o700)
    private_state.symlink_to(private_state.parent / "missing-target.json")
    result, _calls = _invoke(
        "get_monthly_budget_status",
        _lookup_args(),
        downstream_result=_lookup_result(),
    )
    assert result["error_code"] == "STAGE53_GUARD_ERROR"


def test_register_uses_separate_middleware_and_reset_hook():
    class Context:
        def __init__(self):
            self.middleware = []
            self.hooks = []

        def register_middleware(self, kind, callback):
            self.middleware.append((kind, callback))

        def register_hook(self, kind, callback):
            self.hooks.append((kind, callback))

    ctx = Context()
    guard.register(ctx)
    assert ctx.middleware == [("tool_execution", guard.on_tool_execution_middleware)]
    assert ctx.hooks == [("on_session_reset", guard.on_session_reset)]


def test_real_hermes_chain_orders_identity_before_stage53_and_blocks_duplicate(
    tmp_path, monkeypatch
):
    import hermes_cli.plugins as hp
    from agent.tool_executor import _run_agent_tool_execution_middleware

    home = tmp_path / "profile"
    plugins = home / "plugins"
    plugins.mkdir(parents=True)
    for name in ("mariyam_identity_guard", "mariyam_stage53_guard"):
        shutil.copytree(REPO_ROOT / "deploy" / "hermes_plugins" / name, plugins / name)
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n"
        "    - mariyam_identity_guard\n"
        "    - mariyam_stage53_guard\n",
        encoding="utf-8",
    )
    mapping = home / "identity-private.json"
    mapping.write_text(
        json.dumps(
            {
                "222222222": {
                    "user_id": 20,
                    "role": "oyijon",
                    "display_name": "Тест Ойижон",
                }
            }
        ),
        encoding="utf-8",
    )
    state_db = home / "state.db"
    con = sqlite3.connect(state_db)
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, origin_json TEXT)")
    con.execute(
        "INSERT INTO sessions VALUES (?, ?)",
        (
            "session-runtime",
            json.dumps({"platform": "telegram", "user_id": "222222222"}),
        ),
    )
    con.commit()
    con.close()

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(mapping))
    monkeypatch.setenv(
        "MARIYAM_STAGE53_STATE_FILE", str(tmp_path / "private" / "stage53.json")
    )
    pm = hp.get_plugin_manager()
    pm.discover_and_load(force=True)
    callbacks = pm._middleware["tool_execution"]
    callback_modules = [callback.__module__ for callback in callbacks]
    assert "mariyam_identity_guard" in callback_modules[0]
    assert "mariyam_identity_guard" in callback_modules[1]
    assert "mariyam_stage53_guard" in callback_modules[2]

    count = {"value": 0}

    def execute(effective_args):
        count["value"] += 1
        assert effective_args["user_id"] == 20
        return _result(saved_id=1)

    agent = type(
        "RuntimeAgent",
        (),
        {
            "session_id": "session-runtime",
            "_current_turn_id": "turn-runtime",
            "_current_api_request_id": "request-runtime",
        },
    )()
    first, _ = _run_agent_tool_execution_middleware(
        agent,
        function_name="mcp__mariyam_backend__save_expense",
        function_args={"user_id": 1, "amount": 48000},
        effective_task_id="task-runtime",
        tool_call_id="tool-1",
        execute=execute,
    )
    second, _ = _run_agent_tool_execution_middleware(
        agent,
        function_name="mcp__mariyam_backend__save_expense",
        function_args={"user_id": 1, "amount": 48000},
        effective_task_id="task-runtime",
        tool_call_id="tool-2",
        execute=execute,
    )
    assert json.loads(first)["ok"] is True
    assert json.loads(second)["error_code"] == "DUPLICATE_SUCCESS_BLOCKED"
    assert count["value"] == 1
