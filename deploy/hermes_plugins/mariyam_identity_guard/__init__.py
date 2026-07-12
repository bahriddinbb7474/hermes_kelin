"""Deterministic Telegram session identity guard for Mariyam MCP tools.

This is a Hermes ``tool_execution`` middleware plugin. It runs BEFORE the
actual MCP tool call and rewrites/forces the correct internal ``users.id``
based on the *current Telegram session*, never on model guesses, memory,
or display name.

Chain of trust (no model involvement in identity):

    Telegram session  ->  origin.user_id (from Hermes session store)
                       ->  private mapping (MARIYAM_IDENTITY_MAP_FILE)
                       ->  internal users.id
                       ->  forced into tool arguments

Fail-closed: if the sender cannot be resolved, or the mapping is missing /
corrupt, the guarded tool is NOT executed and a safe error is returned
without calling ``next_call``.

No real Telegram IDs, no internal user_ids are present in this file. The
mapping lives only in the private file referenced by
``MARIYAM_IDENTITY_MAP_FILE`` (set on the VPS, never in git).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sqlite3
from typing import Any

LOG = logging.getLogger("mariyam_identity_guard")

# Tools that MUST carry the resolved internal user_id.
USER_SCOPED_TOOLS = frozenset(
    {
        "save_expense",
        "save_income",
        "update_expense",
        "update_last_expense",
        "delete_expense",
        "delete_last_expense",
        "get_expense_report",
        "get_balance_summary",
        "save_quran_progress",
        "get_quran_progress",
        "save_health_note",
        "save_alert_event",
        "save_plan_note",
        "get_admin_report_data",
    }
)

# Special identity contract: rewrite ALL identity fields from the mapping.
ENSURE_USER = "ensure_user"

# Tools that are global/system and must pass through unchanged.
GLOBAL_TOOLS = frozenset(
    {
        "backup_data",
        "get_backup_status",
        "get_bot_status",
        "log_usage_cost",
    }
)


def _mask(value: Any) -> str:
    """Mask an identifier for logging (no raw Telegram ID ever logged)."""
    s = str(value)
    if len(s) <= 6:
        return "***"
    return f"{s[:4]}…{s[-4:]}"


def _state_db_path() -> str | None:
    """Resolve the Hermes session store (state.db) path.

    Order: explicit MARIYAM_STATE_DB, then HERMES_HOME (profile-scoped, set
    by Hermes), then the well-known profile default.
    """
    explicit = os.environ.get("MARIYAM_STATE_DB")
    if explicit:
        return explicit
    home = os.environ.get("HERMES_HOME")
    if home:
        return os.path.join(home, "state.db")
    return os.path.expanduser("~/.hermes/profiles/mariyam_oyijon/state.db")


def resolve_telegram_user_id(session_id: str | None) -> str | None:
    """Return the Telegram ``user_id`` (origin) for a Hermes session.

    Reads the official Hermes session store (state.db), column ``id`` =
    session_id, field ``origin_json.user_id``. Never uses display_name,
    chat_name, or session title.
    """
    if not session_id:
        return None
    db_path = _state_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        uri = f"file:{db_path}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            cur = con.cursor()
            cur.execute("SELECT origin_json FROM sessions WHERE id=?", (session_id,))
            row = cur.fetchone()
        finally:
            con.close()
        if not row or not row[0]:
            return None
        origin = json.loads(row[0])
        uid = origin.get("user_id")
        return str(uid) if uid is not None else None
    except Exception as exc:  # pragma: no cover - defensive
        LOG.debug("resolve_telegram_user_id failed: %s", exc)
        return None


def load_identity_map() -> dict[str, Any] | None:
    """Load the private Telegram-id -> internal-user mapping.

    Returns None if the file is missing or corrupt (fail-closed trigger).
    """
    path = os.environ.get("MARIYAM_IDENTITY_MAP_FILE")
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        return data
    except Exception as exc:  # pragma: no cover - defensive
        LOG.debug("load_identity_map failed: %s", exc)
        return None


def _safe_error(session_id: str | None, tool_name: str | None) -> str:
    """Fail-closed result: no tool executed, model sees a safe error.

    The Telegram origin is NEVER included in the message or logs.
    """
    LOG.warning(
        "identity_guard BLOCKED session=%s tool=%s (fail-closed)",
        _mask(session_id),
        tool_name,
    )
    payload = {
        "ok": False,
        "error_code": "IDENTITY_UNRESOLVED",
        "message_ru": "Не удалось безопасно определить пользователя",
        "message_uz": "Фойдаланувчини хавфсиз аниқлаб бўлмади",
    }
    return json.dumps(payload, ensure_ascii=False)


def _resolve_internal_user_id(
    session_id: str | None, id_map: dict[str, Any] | None
) -> tuple[int | None, str | None]:
    """Return (internal_user_id, telegram_id) or (None, None) on failure."""
    tg_id = resolve_telegram_user_id(session_id)
    if not tg_id:
        return None, None
    if not isinstance(id_map, dict):
        return None, tg_id
    entry = id_map.get(tg_id)
    if not isinstance(entry, dict) or "user_id" not in entry:
        return None, tg_id
    internal = entry["user_id"]
    if not isinstance(internal, int):
        return None, tg_id
    return internal, tg_id


def on_tool_execution_middleware(**kwargs: Any) -> Any:
    """tool_execution middleware: force correct identity into tool args."""
    tool_name = kwargs.get("tool_name")
    args = kwargs.get("args") or {}
    next_call = kwargs.get("next_call")
    session_id = kwargs.get("session_id")

    # Global / system tools: pass through unchanged.
    if tool_name in GLOBAL_TOOLS:
        if callable(next_call):
            return next_call(args)
        return args

    # Only guard user-scoped tools and ensure_user; everything else passes.
    guarded = tool_name in USER_SCOPED_TOOLS or tool_name == ENSURE_USER
    if not guarded:
        if callable(next_call):
            return next_call(args)
        return args

    internal_uid, tg_id = _resolve_internal_user_id(
        session_id, load_identity_map()
    )
    if internal_uid is None:
        # Fail-closed: do NOT call the tool.
        return _safe_error(session_id, tool_name)

    args = copy.deepcopy(args)

    if tool_name == ENSURE_USER:
        # Force every identity field from the private mapping; never accept
        # model-generated identity.
        id_map = load_identity_map() or {}
        entry = id_map.get(tg_id or "")
        if isinstance(entry, dict):
            if str(tg_id).isdigit():
                args["telegram_id"] = int(tg_id)
            else:
                args["telegram_id"] = tg_id
            args["role"] = entry.get("role", args.get("role"))
            args["display_name"] = entry.get("display_name", args.get("display_name"))
    else:
        # Force the resolved internal user_id, overriding any model value.
        args["user_id"] = internal_uid

    LOG.info(
        "identity_guard session=%s user_id=%s tool=%s rewritten=true",
        _mask(session_id),
        internal_uid,
        tool_name,
    )

    if callable(next_call):
        return next_call(args)
    return args


def register(ctx) -> None:  # pragma: no cover - exercised at runtime on VPS
    """Register the middleware with the Hermes plugin context."""
    ctx.register_middleware("tool_execution", on_tool_execution_middleware)
