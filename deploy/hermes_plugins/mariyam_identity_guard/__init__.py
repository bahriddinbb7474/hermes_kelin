"""Deterministic, role-aware, fail-closed Telegram identity guard.

Hermes ``tool_execution`` middleware. Runs BEFORE the MCP tool call and forces
the correct internal ``users.id`` into tool arguments based on the *current
Telegram session*, never on model guesses, memory, or display name.

Identity model
--------------
``user_id`` in the MCP tools denotes the OWNER of the data, not necessarily
the sender:

* ``oyijon`` (care receiver) is always bound to her OWN ``user_id``. Any
  ``user_id`` the model passes is overwritten with her own.
* ``admin`` (Bahriddin aka) may act on his own data, and may read a limited
  set of another user's data ONLY when BOTH hold:
    - the tool is in ``ADMIN_CROSS_TARGET_TOOLS`` (read/report/note only);
    - the requested ``user_id`` is in his ``allowed_target_user_ids``.
  Write/delete tools (save_expense, delete_last_expense, ...) are never
  cross-target.

Fail-closed (P0)
---------------
Exceptions thrown inside the guard BEFORE ``next_call`` are caught and turned
into a safe error result; ``next_call`` is then never invoked, so the
downstream MCP tool cannot run. Exceptions raised BY the downstream tool are
NOT masked (the call happens outside the try block).

Chain of trust (no model involvement in identity):

    Telegram session -> origin.user_id (Hermes session store)
                     -> private mapping (MARIYAM_IDENTITY_MAP_FILE)
                     -> actor entry (role, user_id, allowed_target_user_ids)
                     -> forced into tool arguments

No real Telegram IDs, no internal user_ids live in this file. The mapping
lives only in the private file referenced by ``MARIYAM_IDENTITY_MAP_FILE``
(set on the VPS, never in git).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sqlite3
import stat
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

# Admin may reach ANOTHER user's data only via these tools (read/report/note).
ADMIN_CROSS_TARGET_TOOLS = frozenset(
    {
        "get_expense_report",
        "get_balance_summary",
        "get_admin_report_data",
        "save_plan_note",
    }
)

ERROR_MESSAGES = {
    "IDENTITY_UNRESOLVED": (
        "Не удалось безопасно определить пользователя",
        "Фойдаланувчини хавфсиз аниқлаб бўлмади",
    ),
    "IDENTITY_TARGET_FORBIDDEN": (
        "Этот инструмент запрещён для чужих данных",
        "Бу восита бошқа фойдаланувчи маълумотлари учун ман этилган",
    ),
    "IDENTITY_MAPPING_INVALID": (
        "Файл привязки пользователей недействителен",
        "Фойдаланувчилар боғловчи файли яроқсиз",
    ),
    "IDENTITY_MAPPING_PERMISSIONS": (
        "Файл привязки недоступен по правам доступа",
        "Боғловчи файлга рухсат бўйича кириш маҳ бўлмади",
    ),
    "IDENTITY_GUARD_ERROR": (
        "Внутренняя ошибка защиты идентификации",
        "Идентификация ҳимоясида ички хатолик",
    ),
}


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
    session_id, field ``origin_json.user_id``. Requires ``platform ==
    telegram`` and a non-empty ``user_id``. Never uses display_name,
    user_name, chat_name, or session title.
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
        if origin.get("platform") != "telegram":
            return None
        uid = origin.get("user_id")
        return str(uid) if uid not in (None, "") else None
    except Exception as exc:  # pragma: no cover - defensive
        LOG.debug("resolve_telegram_user_id failed: %s", exc)
        return None


class MappingError(Exception):
    """Raised by validate_mapping_file / load_identity_map with an error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_mapping_file(path: str, enforce_posix_permissions: bool = True) -> None:
    """Validate the private mapping file.

    Raises ``MappingError`` with a specific code on any problem:
      * file missing / unreadable  -> IDENTITY_UNRESOLVED
      * corrupt JSON / not a dict  -> IDENTITY_MAPPING_INVALID
      * wrong POSIX mode (non-0600) -> IDENTITY_MAPPING_PERMISSIONS

    ``enforce_posix_permissions`` is True at runtime on POSIX systems
    (``os.name == "posix"``); tests may force it to exercise the 0600 check
    on any OS.
    """
    if not path or not os.path.exists(path):
        raise MappingError("IDENTITY_UNRESOLVED")
    if enforce_posix_permissions:
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError as exc:
            raise MappingError("IDENTITY_UNRESOLVED") from exc
        if mode != 0o600:
            raise MappingError("IDENTITY_MAPPING_PERMISSIONS")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise MappingError("IDENTITY_MAPPING_INVALID") from exc
    if not isinstance(data, dict):
        raise MappingError("IDENTITY_MAPPING_INVALID")


def load_identity_map() -> tuple[dict[str, Any] | None, str | None]:
    """Load the private mapping.

    Returns ``(mapping_dict, None)`` on success, or ``(None, error_code)`` on
    any failure (fail-closed trigger). The error code distinguishes a
    permissions problem from a missing/corrupt mapping.
    """
    path = os.environ.get("MARIYAM_IDENTITY_MAP_FILE")
    if not path:
        return None, "IDENTITY_UNRESOLVED"
    enforce = os.name == "posix"
    try:
        validate_mapping_file(path, enforce_posix_permissions=enforce)
    except MappingError as exc:
        return None, exc.code
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None, "IDENTITY_MAPPING_INVALID"
    if not isinstance(data, dict):
        return None, "IDENTITY_MAPPING_INVALID"
    return data, None


def _safe_error(
    session_id: str | None,
    tool_name: str | None,
    code: str,
    actor_role: str | None = None,
    actor_uid: int | None = None,
    requested: Any = None,
    effective: Any = None,
    decision: str = "blocked",
) -> str:
    """Fail-closed result: no tool executed, model sees a safe error.

    The Telegram origin is NEVER included in the message or logs.
    """
    LOG.warning(
        "identity_guard BLOCKED session=%s tool=%s code=%s",
        _mask(session_id),
        tool_name,
        code,
    )
    ru, uz = ERROR_MESSAGES.get(
        code,
        ("Внутренняя ошибка защиты идентификации", "Идентификация ҳимоясида ички хатолик"),
    )
    payload = {
        "ok": False,
        "error_code": code,
        "message_ru": ru,
        "message_uz": uz,
    }
    return json.dumps(payload, ensure_ascii=False)


def _audit_log(
    tool_name: str,
    actor_role: str,
    actor_uid: int,
    requested: Any,
    effective: Any,
    rewritten: bool,
    decision: str,
) -> None:
    """Safe audit log: internal ids + decision only, never raw Telegram id."""
    LOG.info(
        "identity_guard tool=%s actor=%s actor_user_id=%s requested=%s effective=%s decision=%s",
        tool_name,
        actor_role,
        actor_uid,
        requested,
        effective,
        decision,
    )


def _resolve_actor(
    session_id: str | None, id_map: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the actor mapping entry, or None if unresolved."""
    tg_id = resolve_telegram_user_id(session_id)
    if not tg_id:
        return None
    entry = id_map.get(tg_id)
    if not isinstance(entry, dict) or "user_id" not in entry or "role" not in entry:
        return None
    return entry


def _compute_effective_args(
    tool_name: str,
    args: dict[str, Any],
    actor: dict[str, Any],
    tg_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Compute (effective_args, error_code). error_code None means allowed."""
    actor_uid = actor["user_id"]
    actor_role = actor["role"]
    allowed = actor.get("allowed_target_user_ids", []) or []
    requested = args.get("user_id")

    if tool_name == ENSURE_USER:
        # Setup/handover only: force every identity field from the sender.
        out = copy.deepcopy(args)
        out["telegram_id"] = int(tg_id) if str(tg_id).isdigit() else tg_id
        out["role"] = actor_role
        out["display_name"] = actor.get("display_name")
        return out, None

    if actor_role == "oyijon":
        # Always own data; any requested user_id is overwritten.
        out = copy.deepcopy(args)
        out["user_id"] = actor_uid
        return out, None

    # Admin.
    if requested is None:
        # Never guess a cross-target; default to self.
        out = copy.deepcopy(args)
        out["user_id"] = actor_uid
        return out, None
    if requested == actor_uid:
        return copy.deepcopy(args), None
    # Cross-target: allow only read/report/note tools to allowed ids.
    if tool_name in ADMIN_CROSS_TARGET_TOOLS and requested in allowed:
        out = copy.deepcopy(args)
        out["user_id"] = requested
        return out, None
    return None, "IDENTITY_TARGET_FORBIDDEN"


def on_tool_execution_middleware(**kwargs: Any) -> Any:
    """tool_execution middleware: force correct identity into tool args."""
    tool_name = kwargs.get("tool_name")
    args = kwargs.get("args") or {}
    next_call = kwargs.get("next_call")
    session_id = kwargs.get("session_id")

    # Global / system tools: pass through unchanged (no guard applied).
    if tool_name in GLOBAL_TOOLS:
        if callable(next_call):
            return next_call(args)
        return args
    # Only guard user-scoped tools and ensure_user; everything else passes.
    if tool_name not in USER_SCOPED_TOOLS and tool_name != ENSURE_USER:
        if callable(next_call):
            return next_call(args)
        return args

    # Everything that can fail is inside try; any exception -> safe block,
    # next_call is NEVER reached, so downstream MCP tool cannot execute.
    try:
        id_map, map_err = load_identity_map()
        if map_err is not None:
            return _safe_error(session_id, tool_name, map_err)
        tg_id = resolve_telegram_user_id(session_id)
        actor = _resolve_actor(session_id, id_map) if tg_id else None
        if actor is None:
            return _safe_error(session_id, tool_name, "IDENTITY_UNRESOLVED")
        effective_args, err = _compute_effective_args(
            tool_name, copy.deepcopy(args), actor, tg_id
        )
        if err is not None:
            return _safe_error(session_id, tool_name, err)
        requested = args.get("user_id")
        effective = effective_args.get("user_id")
        rewritten = requested != effective
        decision = (
            "oyijon_self_forced"
            if actor["role"] == "oyijon"
            else ("admin_self" if effective == actor["user_id"] else "allowed_cross_target")
        )
        _audit_log(
            tool_name,
            actor["role"],
            actor["user_id"],
            requested,
            effective,
            rewritten,
            decision,
        )
    except Exception as exc:  # P0: never let an exception reach downstream.
        LOG.debug("identity_guard internal error: %s", exc)
        return _safe_error(session_id, tool_name, "IDENTITY_GUARD_ERROR")

    # Downstream call is OUTSIDE the try block, so its own errors are not
    # masked. next_call is invoked at most once.
    if callable(next_call):
        return next_call(effective_args)
    return effective_args


def register(ctx) -> None:  # pragma: no cover - exercised at runtime on VPS
    """Register the middleware with the Hermes plugin context."""
    ctx.register_middleware("tool_execution", on_tool_execution_middleware)
