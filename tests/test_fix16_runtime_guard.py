from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import yaml


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "deploy" / "hermes_plugins" / "mariyam_runtime_guard" / "__init__.py"
SNIPPET = REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "config.skill-protect.snippet.yaml"
OUTBOUND = REPO / "deploy" / "hermes_plugins" / "mariyam_outbound_filter" / "__init__.py"


def _load():
    spec = importlib.util.spec_from_file_location("mariyam_runtime_guard_test", PLUGIN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _response(*, content=None, reasoning=None, tool_calls=None, usage=None, finish="length"):
    message = SimpleNamespace(
        content=content,
        reasoning=reasoning,
        reasoning_content=None,
        reasoning_details=None,
        tool_calls=tool_calls,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=message)],
        usage=usage,
    )


def test_provider_route_is_explicit_n1n_with_luna_openrouter_fallback():
    data = yaml.safe_load(SNIPPET.read_text(encoding="utf-8"))
    assert data["model"] == {
        "default": "gpt-5.6-luna",
        "provider": "custom:n1n",
    }
    assert data["providers"]["n1n"] == {
        "name": "n1n",
        "base_url": "https://api.n1n.ai/v1",
        "key_env": "N1N_API_KEY",
        "default_model": "gpt-5.6-luna",
        "transport": "chat_completions",
    }
    assert data["fallback_providers"] == [
        {"provider": "openrouter", "model": "openai/gpt-5.6-luna"}
    ]
    enabled = data["plugins"]["enabled"]
    assert enabled.index("mariyam_runtime_guard") < enabled.index(
        "mariyam_outbound_filter"
    )


def test_terminal_provider_failure_keeps_existing_provenance_marker():
    text = OUTBOUND.read_text(encoding="utf-8")
    assert "class _ProviderFailureReply(str)" in text
    assert "PROVIDER_ERROR_REPLY_FN = \"_gateway_provider_error_reply\"" in text


def test_classifier_matches_only_empty_length_without_usage():
    guard = _load()
    assert guard.is_malformed_length_response(_response()) is True
    assert guard.is_malformed_length_response(_response(content="partial")) is False
    assert guard.is_malformed_length_response(_response(reasoning="thinking")) is False
    assert guard.is_malformed_length_response(_response(tool_calls=[object()])) is False
    assert guard.is_malformed_length_response(_response(usage={"output_tokens": 0})) is False
    assert guard.is_malformed_length_response(_response(finish="stop")) is False


def test_provider_guard_retries_once_then_returns_success():
    guard = _load()
    malformed = _response()
    success = _response(content="Хўп", usage={"output_tokens": 2}, finish="stop")

    class Agent:
        provider = "custom"
        base_url = "https://api.n1n.ai/v1"

        def _interruptible_api_call(self, _request):
            return responses.pop(0)

        def _interruptible_streaming_api_call(self, _request, *, on_first_delta=None):
            return responses.pop(0)

    responses = [malformed, success]
    guard.install_provider_guard(Agent)
    assert Agent()._interruptible_api_call({}) is success
    assert responses == []


def test_provider_guard_twice_malformed_raises_provider_failure():
    guard = _load()

    class Agent:
        provider = "custom"
        base_url = "https://api.n1n.ai/v1"

        def _interruptible_api_call(self, _request):
            return responses.pop(0)

        def _interruptible_streaming_api_call(self, _request, *, on_first_delta=None):
            return responses.pop(0)

    responses = [_response(), _response()]
    guard.install_provider_guard(Agent)
    try:
        Agent()._interruptible_api_call({})
    except guard.MalformedProviderResponseError as exc:
        assert "finish_reason=length" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("twice-malformed provider response was not raised")
    assert responses == []


def test_daily_reset_rotates_before_generic_recovery():
    guard = _load()
    old = SimpleNamespace(session_id="old", last_prompt_tokens=90000)
    fresh = SimpleNamespace(
        session_id="fresh",
        was_auto_reset=False,
        auto_reset_reason=None,
        reset_had_activity=False,
    )

    class Lock:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Store:
        _lock = Lock()
        _entries = {"telegram:dm": old}

        def _ensure_loaded_locked(self):
            pass

        def _generate_session_key(self, _source):
            return "telegram:dm"

        def _should_reset(self, _entry, _source):
            return "daily"

        def reset_session(self, key):
            assert key == "telegram:dm"
            self._entries[key] = fresh
            return fresh

        def _save_entries(self):
            self.saved = True

        def get_or_create_session(self, _source, force_new=False):
            raise AssertionError("generic DB recovery must not run on due daily reset")

    guard.install_session_guard(Store)
    store = Store()
    result = store.get_or_create_session(SimpleNamespace())
    assert result is fresh
    assert fresh.was_auto_reset is True
    assert fresh.auto_reset_reason == "daily"
    assert fresh.reset_had_activity is True
    assert store.saved is True


def test_register_defers_provider_guard_during_run_agent_import():
    guard = _load()

    class Store:
        def _generate_session_key(self):
            pass

        def _should_reset(self):
            pass

        def reset_session(self):
            pass

        def _save_entries(self):
            pass

        def get_or_create_session(self):
            pass

    fake_gateway = types.ModuleType("gateway.session")
    fake_gateway.SessionStore = Store

    class Context:
        hooks = []

        def register_hook(self, name, callback):
            self.hooks.append((name, callback))

    old_gateway = sys.modules.get("gateway.session")
    old_agent = sys.modules.pop("run_agent", None)
    sys.modules["gateway.session"] = fake_gateway
    try:
        ctx = Context()
        guard.register(ctx)
        assert [name for name, _ in ctx.hooks] == ["pre_llm_call"]
        assert getattr(Store.get_or_create_session, guard.WRAPPED_FLAG) is True
    finally:
        if old_gateway is None:
            sys.modules.pop("gateway.session", None)
        else:
            sys.modules["gateway.session"] = old_gateway
        if old_agent is not None:
            sys.modules["run_agent"] = old_agent


def test_installed_hermes_still_exposes_interception_points():
    configured = os.environ.get("MARIYAM_HERMES_PYTHON")
    if not configured:
        return
    python = Path(configured)
    assert python.is_file(), f"missing configured Hermes Python: {python}"
    probe = (
        "from run_agent import AIAgent; "
        "from gateway.session import SessionStore; "
        "names=(\"_interruptible_api_call\",\"_interruptible_streaming_api_call\"); "
        "assert all(callable(getattr(AIAgent,n,None)) for n in names); "
        "assert callable(getattr(SessionStore,\"get_or_create_session\",None)); "
        "assert callable(getattr(SessionStore,\"reset_session\",None)); "
        "assert callable(getattr(SessionStore,\"_save_entries\",None)); "
        "print(\"ok\")"
    )
    completed = subprocess.run(
        [str(python), "-c", probe],
        cwd=REPO,
        env={
            **os.environ,
            "HERMES_HOME": str(REPO / "private" / "fix16-test-home"),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().splitlines()[-1:] == ["ok"]
