"""Deterministic, role-aware, fail-closed Telegram identity guard.

Hermes ``tool_execution`` middleware. Runs BEFORE the MCP tool call and forces
the correct internal ``users.id`` into tool arguments so that user-scoped MCP
tools always operate on the correct internal owner's data — independent of
what the LLM puts in ``user_id``.

Fail-closed: any internal error or malformed configuration blocks the tool
(no assumption, no admin fallback). The LLM is never trusted for identity.

Layout
------
This module is loaded by the Hermes PluginManager and registered via
``register(ctx)``. It imports nothing from Hermes core at module import time,
so the heavy ``hermes_cli`` import only happens inside
``resolve_telegram_user_id`` (lazy, testable).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import stat
from pathlib import Path

# ---------------------------------------------------------------------------
# Tool classification
# ---------------------------------------------------------------------------
# user-scoped tools: identity must be enforced (user_id = internal owner).
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

# Global tools: not user-scoped, pass straight through (no rewriting, no block).
GLOBAL_TOOLS = frozenset(
    {
        "backup_data",
        "get_backup_status",
        "get_bot_status",
        "log_usage_cost",
    }
)

# The account-creation tool: identity taken from the session's verified sender.
ENSURE_USER = "ensure_user"

# Admin cross-target allowlist. Only these tools may be driven by admin against
# an Oyijon-owned user_id (and only if that id is in allowed_target_user_ids).
# NOT a general allowlist — admin cannot touch arbitrary Oyijon write tools.
ADMIN_CROSS_TARGET_TOOLS = frozenset(
    {
        "get_expense_report",
        "get_balance_summary",
        "get_admin_report_data",
        "save_plan_note",
    }
)

# Safe error codes (fail-closed; never reveal internals/telegram ids in detail).
SAFE_ERROR_CODES = frozenset(
    {
        "IDENTITY_UNRESOLVED",
        "IDENTITY_TARGET_FORBIDDEN",
        "IDENTITY_MAPPING_INVALID",
        "IDENTITY_MAPPING_PERMISSIONS",
        "IDENTITY_GUARD_ERROR",
    }
)

LOG = logging.getLogger("mariyam_identity_guard")

VALID_ROLES = ("admin", "oyijon")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _mask(value):
    """Mask a raw Telegram ID for logs (never expose the real value)."""
    s = str(value)
    if len(s) <= 2:
        return "**"
    return s[0] + "*" * (len(s) - 2) + s[-1]


def _is_pos_int(value):
    """True if value is a positive int (bool is explicitly rejected)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _state_db_path() -> Path | None:
    """Resolve the Hermes state.db path from HERMES_HOME (no fallback guessing)."""
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        return Path(hermes_home) / "state.db"
    return None


# ---------------------------------------------------------------------------
# Mapping schema validation
# ---------------------------------------------------------------------------
def _validate_actor_entry(entry) -> bool:
    """Validate a single mapping entry against the strict schema.

    Does NOT log the entry contents (fail-closed, no raw id leakage).
    """
    if not isinstance(entry, dict):
        return False

    uid = entry.get("user_id")
    if not _is_pos_int(uid):
        return False

    role = entry.get("role")
    if role not in VALID_ROLES:
        return False

    display_name = entry.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        return False

    targets = entry.get("allowed_target_user_ids")

    if role == "admin":
        # allowed_target_user_ids is mandatory, must be a list of unique
        # positive ints (bool rejected). Empty list is allowed (=> no
        # cross-target), and self-target is handled separately in the policy.
        if not isinstance(targets, list):
            return False
        seen = set()
        for t in targets:
            if not _is_pos_int(t):
                return False
            if t in seen:
                return False
            seen.add(t)
        return True

    # role == "oyijon": cross-target list must be absent or empty.
    if targets is not None:
        if not isinstance(targets, list) or len(targets) != 0:
            return False
    return True


def validate_mapping_schema(id_map) -> bool:
    """Validate the entire identity mapping.

    Root must be ``dict[str(telegram_id), actor_entry]`` where every key is a
    non-empty digit-only string (raw Telegram IDs are encoded as keys, never
    logged). Any malformed entry invalidates the whole mapping.
    """
    if not isinstance(id_map, dict) or not id_map:
        return False
    for key, entry in id_map.items():
        if not isinstance(key, str) or not key or not key.isdigit():
            return False
        if not _validate_actor_entry(entry):
            return False
    return True


def validate_mapping_file(path: str | os.PathLike, enforce_posix_permissions: bool = False) -> None:
    """Raise if the mapping file mode is not 0600 (when enforced).

    Used for strict POSIX deployment. Does not read or log file contents.
    """
    if not enforce_posix_permissions:
        return
    p = Path(path)
    if not p.exists():
        raise PermissionError("identity mapping file missing")
    mode = stat.S_IMODE(p.stat().st_mode)
    if mode != 0o600:
        raise PermissionError("identity mapping must be mode 0600")


# ---------------------------------------------------------------------------
# Resolver (lazy Hermes import; swallows all errors -> fail-closed)
# ---------------------------------------------------------------------------
def resolve_telegram_user_id(session_id):
    """Resolve the Telegram id of the sender for a session.

    Source of truth: the persisted Hermes session origin (telegram platform),
    never the LLM-supplied display_name. Returns the str telegram id, or None
    on any failure (caller then blocks the tool).
    """
    if not session_id:
        return None
    try:
        import sqlite3

        db_path = _state_db_path()
        if not db_path or not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT origin_json FROM sessions WHERE id = ?", (session_id,)
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            return None
        origin = json.loads(row[0])
        if origin.get("platform") != "telegram":
            return None
        return origin.get("user_id")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Mapping load (fail-closed)
# ---------------------------------------------------------------------------
def load_identity_map():
    """Load and fully validate the identity mapping.

    Returns ``(mapping, None)`` on success, or ``(None, <safe_error_code>)``
    on any failure. The whole mapping is rejected if any entry is malformed.
    """
    path = os.environ.get("MARIYAM_IDENTITY_MAP_FILE")
    if not path or not Path(path).exists():
        return None, "IDENTITY_UNRESOLVED"

    enforce = os.name == "posix"
    try:
        validate_mapping_file(path, enforce_posix_permissions=enforce)
    except PermissionError:
        return None, "IDENTITY_MAPPING_PERMISSIONS"

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None, "IDENTITY_MAPPING_INVALID"

    if not validate_mapping_schema(data):
        return None, "IDENTITY_MAPPING_INVALID"

    return data, None


# ---------------------------------------------------------------------------
# Safe error envelope
# ---------------------------------------------------------------------------
def _safe_error(session_id, tool_name, code):
    assert code in SAFE_ERROR_CODES, code
    if session_id:
        LOG.warning(
            "identity_guard BLOCKED session=%s tool=%s code=%s",
            _mask(session_id),
            tool_name,
            code,
        )
    return json.dumps(
        {
            "ok": False,
            "error_code": code,
            "message_ru": "Некорректная идентификация пользователя",
            "message_uz": "Фойдаланувчи идентификацияси нотўғри",
        },
        ensure_ascii=False,
    )


def _audit_log(tool_name, actor_role, actor_user_id, requested, effective, decision):
    LOG.info(
        "identity_guard tool=%s actor_role=%s actor_user_id=%s requested=%s effective=%s decision=%s",
        tool_name,
        actor_role,
        actor_user_id,
        requested,
        effective,
        decision,
    )


# ---------------------------------------------------------------------------
# Core policy
# ---------------------------------------------------------------------------
def _resolve_actor(session_id, id_map):
    """Resolve the sending actor from session origin -> mapping entry."""
    tg = resolve_telegram_user_id(session_id)
    if not tg:
        return None
    entry = id_map.get(str(tg))
    if not entry or "user_id" not in entry or "role" not in entry:
        return None
    return entry


def _compute_effective_args(tool_name, args, actor_entry, tg):
    """Compute the rewritten args + (error_code_or_None) under the policy.

    Returns ``(effective_args, None)`` or ``(None, <safe_error_code>)``.
    """
    actor_user_id = actor_entry["user_id"]
    actor_role = actor_entry["role"]
    allowed_targets = actor_entry.get("allowed_target_user_ids", [])

    if tool_name == ENSURE_USER:
        # Account creation: bind explicitly to the verified sender identity.
        out = copy.deepcopy(args)
        out["telegram_id"] = tg
        out["role"] = actor_role
        out["display_name"] = actor_entry.get("display_name")
        return out, None

    if actor_role == "oyijon":
        # Strictly self: force own user_id regardless of requested.
        out = copy.deepcopy(args)
        out["user_id"] = actor_user_id
        return out, None

    elif actor_role == "admin":
        requested = args.get("user_id")

        # No target requested -> operate on self (no guessing).
        if requested is None:
            out = copy.deepcopy(args)
            out["user_id"] = actor_user_id
            return out, None

        # Self-target always allowed.
        if requested == actor_user_id:
            return copy.deepcopy(args), None

        # Cross-target only via the allowlist AND allowed_target_user_ids.
        if (
            tool_name in ADMIN_CROSS_TARGET_TOOLS
            and _is_pos_int(requested)
            and requested in allowed_targets
        ):
            out = copy.deepcopy(args)
            out["user_id"] = requested
            return out, None

        return None, "IDENTITY_TARGET_FORBIDDEN"

    else:
        # Unknown role must never reach admin branch (explicit fail-closed).
        return None, "IDENTITY_MAPPING_INVALID"


# ---------------------------------------------------------------------------
# Middleware entry point
# ---------------------------------------------------------------------------
def on_tool_execution_middleware(**kwargs):
    """tool_execution middleware: enforce identity, fail closed.

    Guarantees:
      * No exception before next_call reaches downstream (all pre-call logic
        is wrapped; any failure returns a safe block). Terminal (downstream)
        errors are NOT masked -- next_call is invoked outside the try.
      * next_call is invoked at most once.
    """
    tool_name = kwargs.get("tool_name")
    args = kwargs.get("args") or {}
    next_call = kwargs.get("next_call")
    session_id = kwargs.get("session_id")

    # Global tools: not user-scoped, pass straight through untouched.
    if tool_name in GLOBAL_TOOLS or (
        tool_name not in USER_SCOPED_TOOLS and tool_name != ENSURE_USER
    ):
        if callable(next_call):
            return next_call(args)
        return args

    effective_args = None
    try:
        id_map, map_err = load_identity_map()
        if map_err == "IDENTITY_MAPPING_PERMISSIONS":
            return _safe_error(session_id, tool_name, "IDENTITY_MAPPING_PERMISSIONS")
        if map_err == "IDENTITY_MAPPING_INVALID":
            return _safe_error(session_id, tool_name, "IDENTITY_MAPPING_INVALID")
        if not isinstance(id_map, dict):
            return _safe_error(session_id, tool_name, "IDENTITY_UNRESOLVED")

        actor = _resolve_actor(session_id, id_map)
        if actor is None:
            return _safe_error(session_id, tool_name, "IDENTITY_UNRESOLVED")

        tg = resolve_telegram_user_id(session_id)
        effective_args, err = _compute_effective_args(tool_name, args, actor, tg)
        if err is not None:
            return _safe_error(session_id, tool_name, err)

        if tool_name == ENSURE_USER:
            _audit_log(
                tool_name, actor["role"], actor["user_id"], None, actor["user_id"], "ensure_user_bound"
            )
        else:
            _audit_log(
                tool_name,
                actor["role"],
                actor["user_id"],
                args.get("user_id"),
                effective_args.get("user_id"),
                "oyijon_self" if actor["role"] == "oyijon" else "admin_target",
            )
    except Exception:
        return _safe_error(session_id, tool_name, "IDENTITY_GUARD_ERROR")

    # Downstream call OUTSIDE try so its errors are not masked.
    if callable(next_call):
        return next_call(effective_args)
    return effective_args


def register(ctx) -> None:  # pragma: no cover - exercised at runtime on VPS
    """Register the middleware with the Hermes plugin context."""
    ctx.register_middleware("tool_execution", on_tool_execution_middleware)
