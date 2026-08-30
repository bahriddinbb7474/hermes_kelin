"""Profile-scoped runtime recovery for Mariyam.

Two Hermes v0.18.2 edge cases are handled without modifying Hermes core:

* a daily reset can be defeated when the routed session is already ended as
  ``agent_close``: ``SessionStore`` drops the stale route and immediately
  recovers the same database row.  The wrapper performs the due daily reset
  before the generic recovery path and therefore persists a fresh route;
* some OpenAI-compatible providers return ``finish_reason=length`` with no
  content, reasoning, tool calls, or usage.  This is not a real output cap.
  The wrapper retries that provider response once.  If the retry is malformed
  too, it raises a provider-call failure so Hermes' existing retry/fallback
  path and terminal provider-error reply remain authoritative.

The interception points are intentionally named constants.  The repository
test suite checks them against the installed Hermes runtime so an upstream
rename fails loudly instead of silently disabling either protection.
"""

from __future__ import annotations

import logging
import sys
from functools import wraps
from typing import Any, Callable

LOG = logging.getLogger("mariyam_runtime_guard")

AGENT_MODULE = "run_agent"
AGENT_CLASS = "AIAgent"
NONSTREAM_METHOD = "_interruptible_api_call"
STREAM_METHOD = "_interruptible_streaming_api_call"
SESSION_MODULE = "gateway.session"
SESSION_CLASS = "SessionStore"
SESSION_METHOD = "get_or_create_session"
WRAPPED_FLAG = "_mariyam_runtime_guard_wrapped"


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def is_malformed_length_response(response: Any) -> bool:
    """Match only the provider defect, never a genuine truncated response."""
    choices = getattr(response, "choices", None)
    if not isinstance(choices, (list, tuple)) or len(choices) != 1:
        return False
    choice = choices[0]
    if str(getattr(choice, "finish_reason", "") or "").lower() != "length":
        return False
    message = getattr(choice, "message", None)
    if message is None:
        return False
    if not _is_empty(getattr(message, "content", None)):
        return False
    if not _is_empty(getattr(message, "tool_calls", None)):
        return False
    for field in ("reasoning", "reasoning_content", "reasoning_details"):
        if not _is_empty(getattr(message, field, None)):
            return False
    return getattr(response, "usage", None) is None


class MalformedProviderResponseError(RuntimeError):
    """Retryable provider-call failure consumed by Hermes' normal error path."""


def _wrap_provider_call(original: Callable[..., Any], method_name: str) -> Callable[..., Any]:
    @wraps(original)
    def guarded(self, *args, **kwargs):
        response = original(self, *args, **kwargs)
        if not is_malformed_length_response(response):
            return response

        LOG.warning(
            "mariyam_runtime_guard: malformed empty length response; "
            "retrying provider once (method=%s provider=%s base_url=%s)",
            method_name,
            getattr(self, "provider", "unknown"),
            getattr(self, "base_url", "unknown"),
        )
        retry_response = original(self, *args, **kwargs)
        if not is_malformed_length_response(retry_response):
            return retry_response

        LOG.error(
            "mariyam_runtime_guard: malformed empty length response repeated; "
            "raising provider failure for Hermes retry/fallback (method=%s)",
            method_name,
        )
        raise MalformedProviderResponseError(
            "Malformed provider response: finish_reason=length with empty "
            "content/reasoning/tool_calls and no usage"
        )

    setattr(guarded, WRAPPED_FLAG, True)
    return guarded


def install_provider_guard(agent_class: type) -> None:
    for method_name in (NONSTREAM_METHOD, STREAM_METHOD):
        original = getattr(agent_class, method_name, None)
        if not callable(original):
            raise RuntimeError(
                f"mariyam_runtime_guard: missing {AGENT_CLASS}.{method_name}"
            )
        if not getattr(original, WRAPPED_FLAG, False):
            setattr(agent_class, method_name, _wrap_provider_call(original, method_name))


def _wrap_session_lookup(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def guarded(self, source, force_new=False):
        if not force_new:
            session_key = self._generate_session_key(source)
            entry = None
            with self._lock:
                self._ensure_loaded_locked()
                entry = self._entries.get(session_key)

            if entry is not None and self._should_reset(entry, source) == "daily":
                old_session_id = entry.session_id
                fresh = self.reset_session(session_key)
                if fresh is not None:
                    fresh.was_auto_reset = True
                    fresh.auto_reset_reason = "daily"
                    fresh.reset_had_activity = bool(entry.last_prompt_tokens > 0)
                    # Persist the diagnostic flags as well as the route written
                    # by reset_session().  Both state.db and sessions.json have
                    # already been rotated at this point.
                    self._save_entries()
                    LOG.info(
                        "mariyam_runtime_guard: daily routing rotation %s -> %s",
                        old_session_id,
                        fresh.session_id,
                    )
                    return fresh
        return original(self, source, force_new=force_new)

    setattr(guarded, WRAPPED_FLAG, True)
    return guarded


def install_session_guard(session_class: type) -> None:
    original = getattr(session_class, SESSION_METHOD, None)
    if not callable(original):
        raise RuntimeError(
            f"mariyam_runtime_guard: missing {SESSION_CLASS}.{SESSION_METHOD}"
        )
    required = (
        "_generate_session_key",
        "_should_reset",
        "reset_session",
        "_save_entries",
    )
    missing = [name for name in required if not callable(getattr(session_class, name, None))]
    if missing:
        raise RuntimeError(
            "mariyam_runtime_guard: missing SessionStore interception support: "
            + ", ".join(missing)
        )
    if not getattr(original, WRAPPED_FLAG, False):
        setattr(session_class, SESSION_METHOD, _wrap_session_lookup(original))


def install() -> None:
    from gateway.session import SessionStore
    from run_agent import AIAgent

    install_provider_guard(AIAgent)
    install_session_guard(SessionStore)
    LOG.info("mariyam_runtime_guard: provider and routing guards installed")


def on_pre_llm_call(**kwargs):
    """Install provider wrappers after ``run_agent`` finished importing."""
    module = sys.modules.get(AGENT_MODULE)
    agent_class = getattr(module, AGENT_CLASS, None) if module is not None else None
    if agent_class is None:
        raise RuntimeError(
            "mariyam_runtime_guard: run_agent.AIAgent unavailable at pre_llm_call"
        )
    install_provider_guard(agent_class)
    return None


def register(ctx) -> None:  # pragma: no cover - exercised in live Hermes
    # Plugin discovery happens while run_agent.py itself is importing, so
    # importing AIAgent here creates a circular import. SessionStore is already
    # available in the gateway and must be wrapped now (before the first route
    # lookup). Provider methods are installed now only when the class already
    # exists; otherwise the first pre_llm_call is the safe late hook.
    from gateway.session import SessionStore

    install_session_guard(SessionStore)
    module = sys.modules.get(AGENT_MODULE)
    agent_class = getattr(module, AGENT_CLASS, None) if module is not None else None
    if agent_class is None:
        ctx.register_hook("pre_llm_call", on_pre_llm_call)
        LOG.info("mariyam_runtime_guard: routing installed; provider guard deferred")
    else:
        install_provider_guard(agent_class)
        LOG.info("mariyam_runtime_guard: provider and routing guards installed")
