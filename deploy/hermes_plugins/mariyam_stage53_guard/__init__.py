"""Deterministic profile guard for Stage 5.3 structured tool execution.

The plugin never classifies user text.  It binds a successful structured
reference-price lookup to the next structured product-plan mutation and atomically
claims a canonical mutating call before downstream execution. State is private,
profile-local by session semantics, and persisted outside the model-visible profile
through ``MARIYAM_STAGE53_STATE_FILE``.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

MCP_SERVER_PREFIX = "mcp__mariyam_backend__"
STATE_TTL_SECONDS = 30 * 60
STATE_VERSION = 1

MUTATING_TOOLS = frozenset(
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
LOOKUP_TOOL = "get_monthly_budget_status"
PRODUCT_SAVE_TOOL = "set_monthly_budget"

_STATE_LOCK = threading.RLock()
_MUTATION_LOCK = threading.RLock()


def _utc_timestamp() -> float:
    return time.time()


def canonical_tool_name(tool_name):
    if isinstance(tool_name, str) and tool_name.startswith(MCP_SERVER_PREFIX):
        bare = tool_name[len(MCP_SERVER_PREFIX) :]
        return bare or tool_name
    return tool_name


def _error(code: str, message_ru: str, message_uz: str) -> str:
    return json.dumps(
        {
            "ok": False,
            "error_code": code,
            "message_ru": message_ru,
            "message_uz": message_uz,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _guard_error() -> str:
    return _error(
        "STAGE53_GUARD_ERROR",
        "Защита товарного плана недоступна; изменение не выполнено",
        "Маҳсулот режаси ҳимояси ишламади; ўзгартиш бажарилмади",
    )


def _product_items_required() -> str:
    return _error(
        "PRODUCT_ITEMS_REQUIRED",
        "Активный товарный черновик требует непустой items; завершите один корректный save",
        "Фаол маҳсулот режаси учун бўш бўлмаган items керак; битта тўғри сақлашни бажаринг",
    )


def _product_lookup_mismatch() -> str:
    return _error(
        "PRODUCT_LOOKUP_MISMATCH",
        "Товар, единица или цена не совпадают с активным reference-price lookup",
        "Маҳсулот, ўлчов бирлиги ёки нарх фаол нарх текширувига мос эмас",
    )


def _duplicate_success_blocked() -> str:
    return _error(
        "DUPLICATE_SUCCESS_BLOCKED",
        "Этот успешный вызов уже выполнен; завершите turn и сразу ответьте пользователю",
        "Бу муваффақиятли чақирув бажарилган; жараённи тугатиб, дарҳол жавоб беринг",
    )


def _state_path() -> Path:
    raw = os.environ.get("MARIYAM_STAGE53_STATE_FILE")
    if not raw:
        raise RuntimeError("MARIYAM_STAGE53_STATE_FILE is required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise RuntimeError("MARIYAM_STAGE53_STATE_FILE must be absolute")
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        try:
            path.resolve().relative_to(Path(hermes_home).expanduser().resolve())
        except ValueError:
            pass
        else:
            raise RuntimeError("stage53 state must be outside HERMES_HOME")
    return path


def _require_private_parent(path: Path) -> None:
    if os.name != "posix":
        return
    parent = path.parent
    if parent.resolve() != parent:
        raise PermissionError("stage53 private parent must not contain symlinks")
    value = parent.lstat()
    if not stat.S_ISDIR(value.st_mode):
        raise PermissionError("stage53 private parent must be a directory")
    if value.st_uid != os.geteuid():
        raise PermissionError("stage53 private parent must be owned by the service user")
    if stat.S_IMODE(value.st_mode) != 0o700:
        raise PermissionError("stage53 private parent must be mode 0700")


def _require_private_mode(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        value = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise PermissionError("stage53 private state must be a regular non-linked file")
    if value.st_uid != os.geteuid():
        raise PermissionError("stage53 private state must be owned by the service user")
    if stat.S_IMODE(value.st_mode) != 0o600:
        raise PermissionError("stage53 private state must be mode 0600")


@contextmanager
def _exclusive_file_lock(state_path: Path):
    with _STATE_LOCK:
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _require_private_parent(state_path)
        lock_path = Path(str(state_path) + ".lock")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(lock_path, flags, 0o600)
        try:
            if os.name == "posix":
                lock_stat = os.fstat(fd)
                if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1:
                    raise PermissionError("stage53 lock must be a regular non-linked file")
                if lock_stat.st_uid != os.geteuid():
                    raise PermissionError("stage53 lock must be owned by the service user")
                os.fchmod(fd, 0o600)
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            if os.name == "posix":
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _empty_state() -> dict:
    return {"version": STATE_VERSION, "sessions": {}, "successes": {}}


def _load_state(path: Path) -> dict:
    _require_private_mode(path)
    if not path.exists():
        return _empty_state()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        raise ValueError("invalid stage53 state")
    if not isinstance(value.get("sessions"), dict) or not isinstance(
        value.get("successes"), dict
    ):
        raise ValueError("invalid stage53 state collections")
    return value


def _write_state(path: Path, state: dict) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=".stage53-", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _cleanup_expired(state: dict, now: float) -> None:
    for collection in ("sessions", "successes"):
        expired = [
            key
            for key, value in state[collection].items()
            if not isinstance(value, dict) or value.get("expires_at", 0) <= now
        ]
        for key in expired:
            state[collection].pop(key, None)


def _state_transaction(callback):
    path = _state_path()
    with _exclusive_file_lock(path):
        state = _load_state(path)
        now = _utc_timestamp()
        _cleanup_expired(state, now)
        result = callback(state, now)
        _write_state(path, state)
        return result


def _digest(*parts: str) -> str:
    joined = "\x00".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def _session_key(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id required")
    return _digest("session", session_id)


def _turn_key(session_id: str, turn_id: str) -> str:
    if not isinstance(turn_id, str) or not turn_id:
        raise ValueError("turn_id required")
    return _digest("turn", session_id, turn_id)


def _positive_user_id(args: dict) -> int:
    user_id = args.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("trusted positive user_id required")
    return user_id


def _canonical_signature(user_id: int, tool_name: str, args: dict) -> str:
    canonical_args = json.dumps(
        args, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return _digest(str(user_id), tool_name, canonical_args)


def _json_payload(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    if isinstance(value, (list, tuple)):
        for entry in value:
            text = getattr(entry, "text", None)
            if text is None and isinstance(entry, dict):
                text = entry.get("text")
            parsed = _json_payload(text)
            if parsed is not None:
                return parsed
    return None


def _is_success(value) -> bool:
    payload = _json_payload(value)
    return isinstance(payload, dict) and payload.get("ok") is True


def _decimal_equal(left, right) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _lookup_state(args: dict, downstream_result, now: float) -> dict:
    user_id = _positive_user_id(args)
    month = args.get("month")
    requested = args.get("price_lookup_items")
    payload = _json_payload(downstream_result)
    returned = payload.get("price_lookup") if isinstance(payload, dict) else None
    if not isinstance(month, str) or not isinstance(requested, list) or not requested:
        raise ValueError("structured lookup context required")
    if not isinstance(returned, list) or len(returned) != len(requested):
        raise ValueError("lookup result mismatch")

    facts = []
    for request in requested:
        if not isinstance(request, dict):
            raise ValueError("invalid lookup request")
        name = request.get("item_name_normalized")
        unit = request.get("unit")
        basis = request.get("price_basis")
        match = next(
            (
                item
                for item in returned
                if isinstance(item, dict)
                and str(item.get("item_name_normalized", "")).casefold()
                == str(name or "").casefold()
                and item.get("unit") == unit
                and item.get("price_basis") == basis
            ),
            None,
        )
        if match is None:
            raise ValueError("lookup result item mismatch")
        facts.append(
            {
                "item_name_normalized": str(name).casefold(),
                "unit": unit,
                "reference_unit_price_uzs": match.get("reference_unit_price_uzs"),
                "price_basis": basis,
                "price_as_of": match.get("price_as_of"),
            }
        )
    return {
        "user_id": user_id,
        "month": month,
        "items": facts,
        "armed_at": now,
        "expires_at": now + STATE_TTL_SECONDS,
    }


def _active_product_state(session_id: str):
    key = _session_key(session_id)
    return _state_transaction(lambda state, _now: state["sessions"].get(key))


def _payload_matches_active(args: dict, active: dict) -> bool:
    if _positive_user_id(args) != active.get("user_id"):
        return False
    if args.get("month") != active.get("month"):
        return False
    items = args.get("items")
    if not isinstance(items, list) or not items:
        return False

    expected_items = active.get("items")
    if not isinstance(expected_items, list) or len(items) != len(expected_items):
        return False

    for expected in expected_items:
        actual = next(
            (
                item
                for item in items
                if isinstance(item, dict)
                and str(item.get("item_name_normalized", "")).casefold()
                == expected["item_name_normalized"]
                and item.get("unit") == expected["unit"]
            ),
            None,
        )
        if actual is None:
            return False
        expected_price = expected.get("reference_unit_price_uzs")
        if expected_price is None:
            if actual.get("price_basis") != "manual":
                return False
            try:
                if Decimal(str(actual.get("reference_unit_price_uzs"))) < 0:
                    return False
            except (InvalidOperation, TypeError, ValueError):
                return False
        else:
            if actual.get("price_basis") != expected.get("price_basis"):
                return False
            if not _decimal_equal(
                actual.get("reference_unit_price_uzs"), expected_price
            ):
                return False
            if actual.get("price_as_of") != expected.get("price_as_of"):
                return False
    return True


def _claim_signature(session_id: str, turn_id: str, signature: str) -> bool:
    session_hash = _session_key(session_id)
    key = _turn_key(session_id, turn_id)

    def update(state, now):
        entry = state["successes"].setdefault(
            key,
            {
                "session_key": session_hash,
                "claims": {},
                "expires_at": now + STATE_TTL_SECONDS,
            },
        )
        claims = entry.get("claims")
        if not isinstance(claims, dict):
            raise ValueError("invalid stage53 mutation claims")
        if signature in claims:
            return False
        claims[signature] = {"status": "inflight", "claimed_at": now}
        entry["expires_at"] = now + STATE_TTL_SECONDS
        return True

    return _state_transaction(update)


def _record_success(session_id: str, turn_id: str, signature: str) -> None:
    key = _turn_key(session_id, turn_id)

    def update(state, now):
        entry = state["successes"].get(key)
        claims = entry.get("claims") if isinstance(entry, dict) else None
        claim = claims.get(signature) if isinstance(claims, dict) else None
        if not isinstance(claim, dict):
            raise ValueError("stage53 mutation claim missing")
        claim["status"] = "success"
        claim["succeeded_at"] = now
        entry["expires_at"] = now + STATE_TTL_SECONDS

    _state_transaction(update)


def _release_claim(session_id: str, turn_id: str, signature: str) -> None:
    key = _turn_key(session_id, turn_id)

    def update(state, _now):
        entry = state["successes"].get(key)
        claims = entry.get("claims") if isinstance(entry, dict) else None
        if not isinstance(claims, dict):
            return
        claims.pop(signature, None)
        if not claims:
            state["successes"].pop(key, None)

    _state_transaction(update)


def _arm_lookup(session_id: str, args: dict, downstream_result) -> None:
    session_hash = _session_key(session_id)

    def update(state, now):
        state["sessions"][session_hash] = _lookup_state(args, downstream_result, now)

    _state_transaction(update)


def _clear_active(session_id: str) -> None:
    session_hash = _session_key(session_id)
    _state_transaction(lambda state, _now: state["sessions"].pop(session_hash, None))


def _handle_lookup(args: dict, session_id: str, next_call):
    result = next_call(args)
    if not args.get("price_lookup_items") or not _is_success(result):
        return result
    try:
        _arm_lookup(session_id, args, result)
    except Exception:
        return _guard_error()
    return result


def _handle_mutation(tool_name: str, args: dict, session_id: str, turn_id: str, next_call):
    with _MUTATION_LOCK:
        try:
            user_id = _positive_user_id(args)
            signature = _canonical_signature(user_id, tool_name, args)
            active = _active_product_state(session_id)
        except Exception:
            return _guard_error()

        if tool_name == PRODUCT_SAVE_TOOL and active is not None:
            items = args.get("items")
            if not isinstance(items, list) or not items:
                return _product_items_required()
            try:
                if not _payload_matches_active(args, active):
                    return _product_lookup_mismatch()
            except Exception:
                return _product_lookup_mismatch()

        try:
            if not _claim_signature(session_id, turn_id, signature):
                return _duplicate_success_blocked()
        except Exception:
            return _guard_error()

        try:
            result = next_call(args)
        except BaseException:
            # Outcome is unknown: downstream may have mutated before raising.
            # Keep the durable claim so a retry cannot execute twice.
            raise
        if not _is_success(result):
            try:
                _release_claim(session_id, turn_id, signature)
            except Exception:
                return _guard_error()
            return result
        try:
            _record_success(session_id, turn_id, signature)
        except Exception:
            # The durable pre-call claim remains. The mutation already succeeded,
            # so never misreport it as not executed or permit a retry downstream.
            return result
        if tool_name == PRODUCT_SAVE_TOOL and active is not None:
            try:
                _clear_active(session_id)
            except Exception:
                # The product save already succeeded. A stale draft is fail-closed
                # and expires automatically; it must not turn success into failure.
                pass
        return result


def on_tool_execution_middleware(**kwargs):
    """Apply structured product-draft binding and duplicate-success suppression."""
    tool_name = canonical_tool_name(kwargs.get("tool_name"))
    args = kwargs.get("args")
    session_id = kwargs.get("session_id")
    turn_id = kwargs.get("turn_id")
    next_call = kwargs.get("next_call")
    if not isinstance(args, dict) or not callable(next_call):
        return _guard_error()

    if tool_name == LOOKUP_TOOL and args.get("price_lookup_items"):
        try:
            return _handle_lookup(args, session_id, next_call)
        except Exception:
            return _guard_error()
    if tool_name in MUTATING_TOOLS:
        return _handle_mutation(tool_name, args, session_id, turn_id, next_call)
    return next_call(args)


def on_session_reset(**kwargs) -> None:
    """Remove private state belonging to the reset session."""
    old_session_id = kwargs.get("old_session_id") or kwargs.get("session_id")
    if not old_session_id:
        return
    try:
        old_key = _session_key(old_session_id)

        def update(state, _now):
            state["sessions"].pop(old_key, None)
            for key, value in list(state["successes"].items()):
                if value.get("session_key") == old_key:
                    state["successes"].pop(key, None)

        _state_transaction(update)
    except Exception:
        return


def register(ctx) -> None:
    """Register independently from ``mariyam_identity_guard``.

    Deployment keeps the identity plugin first in the profile-scoped middleware
    chain so this guard receives its trusted, rewritten ``user_id``.
    """
    ctx.register_middleware("tool_execution", on_tool_execution_middleware)
    ctx.register_hook("on_session_reset", on_session_reset)
