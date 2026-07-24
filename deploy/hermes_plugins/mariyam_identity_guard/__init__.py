"""Deterministic, role-aware, fail-closed Telegram and cron identity guard.

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
import hashlib
import json
import logging
import os
import re
import sqlite3
import stat
import threading
from contextlib import contextmanager
from contextvars import ContextVar
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
        "set_monthly_budget",
        "get_monthly_budget_status",
        "save_quran_progress",
        "get_quran_progress",
        "save_health_note",
        "save_alert_event",
        "save_plan_note",
        "get_admin_report_data",
        # Stage 5.3A monthly plan approval cycle tools (self-only oyijon; cron
        # via trusted mapping). Classifying them enforces identity binding on the
        # Telegram path and routes cron calls through resolve_cron_actor.
        "approve_monthly_plan",
        "open_monthly_plan_cycle",
        "get_monthly_plan_cycle",
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

# Live Hermes MCP tools are exposed as mcp__<server>__<tool>. Only this exact
# Mariyam backend server prefix is stripped for classification/policy.
MCP_SERVER_PREFIX = "mcp__mariyam_backend__"

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
        "CRON_IDENTITY_UNRESOLVED",
        "CRON_JOB_UNTRUSTED",
        "CRON_TOOL_FORBIDDEN",
    }
)

LOG = logging.getLogger("mariyam_identity_guard")

VALID_ROLES = ("admin", "oyijon")

CRON_MAPPING_VERSION = 1
CRON_MAPPING_MAX_BYTES = 64 * 1024
CRON_JOBS_MAX_BYTES = 2 * 1024 * 1024
CRON_SESSION_RE = re.compile(r"^cron_([0-9a-f]{12})_[0-9]{8}_[0-9]{6}$")
CRON_MAPPING_ROOT_KEYS = frozenset({"version", "jobs"})
CRON_MAPPING_ENTRY_KEYS = frozenset(
    {
        "user_id",
        "role",
        "purpose",
        "allowed_tools",
        "job_fingerprint_sha256",
        "prompt_sha256",
    }
)
CRON_JOB_FINGERPRINT_FIELDS = (
    "id",
    "name",
    "prompt",
    "schedule",
    "repeat",
    "deliver",
    "origin",
    "skills",
    "script",
    "no_agent",
    "context_from",
    "enabled_toolsets",
    "workdir",
    "model",
    "provider",
    "base_url",
)
_LOWER_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
_CRON_READ_LOCK = threading.RLock()

# Hermes isolates a middleware callback failure and continues the chain with
# the original payload. The primary guard sets this context-local capability
# only while it delegates; the following barrier blocks a fallback path that
# did not pass through a verified primary guard.
_VERIFIED_GUARD_CALL: ContextVar[bool] = ContextVar(
    "mariyam_identity_guard_verified", default=False
)
_GUARD_ERROR_ENVELOPE = json.dumps(
    {
        "ok": False,
        "error_code": "IDENTITY_GUARD_ERROR",
        "message_ru": "Некорректная идентификация пользователя",
        "message_uz": "Фойдаланувчи идентификацияси нотўғри",
    },
    ensure_ascii=False,
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _mask(value):
    """Mask a raw Telegram ID for logs (never expose the real value)."""
    s = str(value)
    if len(s) <= 2:
        return "**"
    return s[0] + "*" * (len(s) - 2) + s[-1]


def canonical_tool_name(tool_name):
    """Return the bare tool name used for identity policy classification.

    Hermes registers Mariyam MCP tools as ``mcp__mariyam_backend__<tool>``.
    Policy sets use bare names (``save_expense``, ``ensure_user``, …). Only the
    exact server prefix ``mcp__mariyam_backend__`` is stripped; other servers
    and bare names are left unchanged. The original live name must still be
    preserved by the caller for ``next_call``/logging context.
    """
    if not isinstance(tool_name, str) or not tool_name:
        return tool_name
    if tool_name.startswith(MCP_SERVER_PREFIX):
        bare = tool_name[len(MCP_SERVER_PREFIX) :]
        return bare if bare else tool_name
    return tool_name


def _is_pos_int(value):
    """True if value is a positive int (bool is explicitly rejected)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _to_pos_int(value):
    """Coerce a trusted id to a positive int, or None if unsafe.

    Accepts int or digit-only str (origin JSON often stores user_id as str).
    Rejects bool, float, empty, signed, and non-numeric forms.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            n = int(s)
            return n if n > 0 else None
    return None


def _state_db_path() -> Path | None:
    """Resolve the Hermes state.db path from HERMES_HOME (no fallback guessing)."""
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        return Path(hermes_home) / "state.db"
    return None


def _strict_posix_permissions() -> bool:
    return os.name == "posix"


def _effective_uid():
    getter = getattr(os, "geteuid", None)
    return getter() if callable(getter) else None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_repeat(value):
    """Keep only the operator-controlled repeat limit, not run counters."""
    if isinstance(value, dict):
        return {"times": value.get("times")}
    return value


def canonical_cron_job(job) -> dict:
    """Return the immutable job definition used for operator fingerprints."""
    if not isinstance(job, dict):
        raise ValueError("cron job must be an object")
    value = {
        field: copy.deepcopy(job.get(field))
        for field in CRON_JOB_FINGERPRINT_FIELDS
    }
    value["repeat"] = _canonical_repeat(value["repeat"])
    return value


def cron_job_fingerprint(job) -> str:
    """SHA-256 of the canonical immutable cron job definition."""
    encoded = json.dumps(
        canonical_cron_job(job),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return _sha256_text(encoded)


def _validate_private_file(path: Path) -> os.stat_result:
    """Validate the cron mapping path without following symlinks."""
    if not path.is_absolute():
        raise PermissionError("cron identity mapping path must be absolute")
    parent = path.parent
    parent_stat = os.lstat(parent)
    file_stat = os.lstat(path)
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise PermissionError("cron identity mapping parent is unsafe")
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise PermissionError("cron identity mapping file is unsafe")
    if _strict_posix_permissions():
        uid = _effective_uid()
        if uid is None or parent_stat.st_uid != uid or file_stat.st_uid != uid:
            raise PermissionError("cron identity mapping owner is unsafe")
        if stat.S_IMODE(parent_stat.st_mode) != 0o700:
            raise PermissionError("cron identity mapping parent must be mode 0700")
        if stat.S_IMODE(file_stat.st_mode) != 0o600:
            raise PermissionError("cron identity mapping file must be mode 0600")
    return file_stat


def _read_bounded_regular_file(path: Path, max_bytes: int, *, private: bool) -> bytes:
    """Read one regular non-symlink file with lstat/fstat race checks."""
    before = _validate_private_file(path) if private else os.lstat(path)
    if not private and (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)):
        raise PermissionError("unsafe file")
    if before.st_size > max_bytes:
        raise ValueError("file too large")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
        ):
            raise PermissionError("file changed during validation")
        data = b""
        while len(data) <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) > max_bytes:
            raise ValueError("file too large")
        return data
    finally:
        os.close(fd)


@contextmanager
def _shared_cron_jobs_lock(cron_dir: Path):
    """Take Hermes' cross-process jobs lock in shared mode on POSIX."""
    lock_path = cron_dir / ".jobs.lock"
    lock_stat = os.lstat(lock_path)
    if stat.S_ISLNK(lock_stat.st_mode) or not stat.S_ISREG(lock_stat.st_mode):
        raise PermissionError("unsafe cron jobs lock")
    with _CRON_READ_LOCK:
        handle = open(lock_path, "rb")
        try:
            if _strict_posix_permissions():
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            yield
        finally:
            if _strict_posix_permissions():
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def _load_exact_cron_job(job_id: str):
    home = os.environ.get("HERMES_HOME")
    if not home:
        return None
    cron_dir = Path(home) / "cron"
    jobs_path = cron_dir / "jobs.json"
    try:
        with _shared_cron_jobs_lock(cron_dir):
            raw = _read_bounded_regular_file(
                jobs_path, CRON_JOBS_MAX_BYTES, private=False
            )
            store = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(store, dict) or set(store) - {"jobs", "updated_at"}:
        return None
    jobs = store.get("jobs")
    if not isinstance(jobs, list):
        return None
    matches = [job for job in jobs if isinstance(job, dict) and job.get("id") == job_id]
    if len(matches) != 1:
        return None
    job = matches[0]
    if job.get("enabled") is not True:
        return None
    if job.get("state") not in {"scheduled", "running"}:
        return None
    if (
        job.get("script") is not None
        or job.get("context_from") is not None
        or job.get("workdir") is not None
        or job.get("no_agent") is not False
    ):
        return None
    return job


def validate_cron_mapping_schema(value) -> bool:
    """Strict schema v1; any unknown key invalidates the entire mapping."""
    if not isinstance(value, dict) or set(value) != CRON_MAPPING_ROOT_KEYS:
        return False
    if value.get("version") != CRON_MAPPING_VERSION:
        return False
    jobs = value.get("jobs")
    # An operator may deploy the guard before any production cron job is
    # approved, and cleanup intentionally leaves this valid empty baseline.
    if not isinstance(jobs, dict):
        return False
    for job_id, entry in jobs.items():
        if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{12}", job_id):
            return False
        if not isinstance(entry, dict) or set(entry) != CRON_MAPPING_ENTRY_KEYS:
            return False
        if not _is_pos_int(entry.get("user_id")) or entry.get("role") != "oyijon":
            return False
        purpose = entry.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            return False
        allowed = entry.get("allowed_tools")
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(not isinstance(tool, str) for tool in allowed)
            or len(allowed) != len(set(allowed))
            or any(
                tool not in USER_SCOPED_TOOLS or tool == ENSURE_USER
                for tool in allowed
            )
        ):
            return False
        if not _LOWER_HEX_64_RE.fullmatch(
            str(entry.get("job_fingerprint_sha256") or "")
        ):
            return False
        if not _LOWER_HEX_64_RE.fullmatch(str(entry.get("prompt_sha256") or "")):
            return False
    return True


def load_cron_identity_map():
    path_text = os.environ.get("MARIYAM_CRON_IDENTITY_MAP_FILE")
    if not path_text:
        return None, "CRON_IDENTITY_UNRESOLVED"
    try:
        raw = _read_bounded_regular_file(
            Path(path_text), CRON_MAPPING_MAX_BYTES, private=True
        )
    except FileNotFoundError:
        return None, "CRON_IDENTITY_UNRESOLVED"
    except PermissionError:
        return None, "IDENTITY_MAPPING_PERMISSIONS"
    except Exception:
        return None, "IDENTITY_MAPPING_INVALID"
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, "IDENTITY_MAPPING_INVALID"
    if not validate_cron_mapping_schema(value):
        return None, "IDENTITY_MAPPING_INVALID"
    return value, None


def _load_cron_session(session_id: str):
    db_path = _state_db_path()
    if not db_path or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT source, user_id, origin_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row != ("cron", None, None):
                return None
            prompt_row = conn.execute(
                "SELECT content FROM messages "
                "WHERE session_id = ? AND role = 'user' "
                "ORDER BY id ASC LIMIT 1",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not prompt_row or not isinstance(prompt_row[0], str):
        return None
    return prompt_row[0]


def _cron_prompt_is_bound(session_prompt: str, base_prompt: str) -> bool:
    return (
        isinstance(base_prompt, str)
        and bool(base_prompt)
        and session_prompt.count(base_prompt) == 1
        and session_prompt.rstrip().endswith(base_prompt)
    )


def resolve_cron_actor(session_id: str, tool_name: str):
    """Resolve one trusted cron actor or return a safe error code."""
    match = CRON_SESSION_RE.fullmatch(session_id or "")
    if not match:
        return None, "CRON_IDENTITY_UNRESOLVED", None
    job_id = match.group(1)
    session_prompt = _load_cron_session(session_id)
    if session_prompt is None:
        return None, "CRON_IDENTITY_UNRESOLVED", job_id
    mapping, map_err = load_cron_identity_map()
    if map_err is not None:
        return None, map_err, job_id
    entry = mapping["jobs"].get(job_id)
    if entry is None:
        return None, "CRON_IDENTITY_UNRESOLVED", job_id
    if tool_name not in entry["allowed_tools"]:
        return None, "CRON_TOOL_FORBIDDEN", job_id
    job = _load_exact_cron_job(job_id)
    if job is None:
        return None, "CRON_JOB_UNTRUSTED", job_id
    prompt = job.get("prompt")
    try:
        trusted = (
            isinstance(prompt, str)
            and _sha256_text(prompt) == entry["prompt_sha256"]
            and cron_job_fingerprint(job) == entry["job_fingerprint_sha256"]
            and _cron_prompt_is_bound(session_prompt, prompt)
        )
    except Exception:
        trusted = False
    if not trusted:
        return None, "CRON_JOB_UNTRUSTED", job_id
    return entry, None, job_id


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
    try:
        if session_id:
            LOG.warning(
                "identity_guard BLOCKED session=%s tool=%s code=%s",
                _mask(session_id),
                tool_name,
                code,
            )
    except Exception:
        # A temporary/debug logging error must not escape to Hermes, whose
        # generic middleware handler would otherwise continue with raw args.
        pass
    if code == "IDENTITY_GUARD_ERROR":
        return _GUARD_ERROR_ENVELOPE
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


def _cron_audit_log(job_id, tool_name, decision):
    """Cron audit deliberately omits session and all user/target identifiers."""
    LOG.info(
        "identity_guard cron_job=%s tool=%s decision=%s",
        job_id,
        tool_name,
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
        # Backend schema requires telegram_id: integer; origin may store str.
        tg_int = _to_pos_int(tg)
        if tg_int is None:
            return None, "IDENTITY_UNRESOLVED"
        out = copy.deepcopy(args)
        out["telegram_id"] = tg_int
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
      * Any primary-callback error returns a safe block.
      * The registered barrier blocks Hermes' generic fallback when an error
        escapes this callback before delegation.
      * Terminal (downstream) errors are not masked.
      * MCP-prefixed Mariyam tool names are classified by their bare name;
        the original live name is kept only for logging context.
    """
    try:
        original_tool_name = kwargs.get("tool_name")
        tool_name = canonical_tool_name(original_tool_name)
        args = kwargs.get("args") or {}
        next_call = kwargs.get("next_call")
        session_id = kwargs.get("session_id")

        if tool_name in GLOBAL_TOOLS or (
            tool_name not in USER_SCOPED_TOOLS and tool_name != ENSURE_USER
        ):
            effective_args = args
        elif CRON_SESSION_RE.fullmatch(session_id or ""):
            actor, cron_err, job_id = resolve_cron_actor(session_id, tool_name)
            if cron_err is not None:
                return _safe_error(session_id, original_tool_name, cron_err)
            effective_args, err = _compute_effective_args(
                tool_name, args, actor, None
            )
            if err is not None:
                return _safe_error(session_id, original_tool_name, err)
            _cron_audit_log(job_id, original_tool_name, "oyijon_self")
        else:
            id_map, map_err = load_identity_map()
            if map_err == "IDENTITY_MAPPING_PERMISSIONS":
                return _safe_error(session_id, original_tool_name, "IDENTITY_MAPPING_PERMISSIONS")
            if map_err == "IDENTITY_MAPPING_INVALID":
                return _safe_error(session_id, original_tool_name, "IDENTITY_MAPPING_INVALID")
            if not isinstance(id_map, dict):
                return _safe_error(session_id, original_tool_name, "IDENTITY_UNRESOLVED")

            actor = _resolve_actor(session_id, id_map)
            if actor is None:
                return _safe_error(session_id, original_tool_name, "IDENTITY_UNRESOLVED")

            tg = resolve_telegram_user_id(session_id)
            # Policy/classification always use the bare canonical name.
            effective_args, err = _compute_effective_args(tool_name, args, actor, tg)
            if err is not None:
                return _safe_error(session_id, original_tool_name, err)

            if tool_name == ENSURE_USER:
                # _compute_effective_args already rebinds telegram_id/role/
                # display_name from trusted session + validated mapping; model
                # telegram_id/display_name are never authorization sources.
                _audit_log(
                    original_tool_name,
                    actor["role"],
                    actor["user_id"],
                    None,
                    actor["user_id"],
                    "ensure_user_bound",
                )
            else:
                _audit_log(
                    original_tool_name,
                    actor["role"],
                    actor["user_id"],
                    args.get("user_id"),
                    effective_args.get("user_id"),
                    "oyijon_self" if actor["role"] == "oyijon" else "admin_target",
                )

        if not callable(next_call):
            return _safe_error(session_id, original_tool_name, "IDENTITY_GUARD_ERROR")
    except Exception:
        return _safe_error(kwargs.get("session_id"), kwargs.get("tool_name"), "IDENTITY_GUARD_ERROR")

    verified_token = _VERIFIED_GUARD_CALL.set(True)
    try:
        return next_call(effective_args)
    finally:
        _VERIFIED_GUARD_CALL.reset(verified_token)


def _fail_closed_barrier_middleware(**kwargs):
    """Block Hermes fallback after an unexpected primary callback failure."""
    if not _VERIFIED_GUARD_CALL.get():
        return _GUARD_ERROR_ENVELOPE
    next_call = kwargs.get("next_call")
    if not callable(next_call):
        return _GUARD_ERROR_ENVELOPE
    return next_call(kwargs.get("args"))


def register(ctx) -> None:  # pragma: no cover - exercised at runtime on VPS
    """Register the primary guard followed by its fail-closed barrier."""
    ctx.register_middleware("tool_execution", on_tool_execution_middleware)
    ctx.register_middleware("tool_execution", _fail_closed_barrier_middleware)
