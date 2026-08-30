"""No-agent replacement for the `mariyam_obligation_reminders` cron job (imp12-opus).

Converts a daily LLM turn into a plain script: same read-only tool
(`get_recurring_obligations`), same three-state date window and same
"one combined message, never invent a sum" rules that used to live in
`cron/06_obligation_reminders.md` (kept in the repo for reference / instant
rollback via `hermes cron edit <id> --agent`), now executed deterministically.
No model call, no MCP round-trip: this process talks to Postgres directly
through the same `backend.db` functions the tool used.

Hermes cron contract for a `no_agent=true` script (see `--no-agent` docs):
non-empty stdout on exit 0 is delivered verbatim, empty stdout is a silent
tick, a non-zero exit delivers a raw error alert. Because this job's audience
is Oyijon (Cyrillic-only, no technical text ever), the last case is
unacceptable here, so every failure path below is swallowed and turned into
silence instead of a crash — a missed reminder is a much smaller harm than an
English string landing in her chat, and the same due/overdue obligations are
independently visible to the admin in the 19:30 admin report the same day.

Quiet hours / prayer-window suppression is not automatic for no-agent jobs
the way `transform_llm_output` gates a normal LLM cron turn, so this script
calls the same `emit_noncritical` used by dynamically created one-shot
reminders to stay consistent with that contract.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Single-family profile: this is the same internal `users.id` the identity
# guard's private cron mapping already resolves for every Oyijon-facing
# trusted job (role='oyijon'). Verified against the live `users` table during
# imp12-opus; update alongside the cron identity mapping if it ever changes.
OYIJON_USER_ID = 20

TASHKENT = ZoneInfo("Asia/Tashkent")

# Rotate by day-of-year so the same day never repeats itself two days
# running (SOUL §2.5: "не повторяй фразу два дня подряд"), mirroring the
# rotation already used by scripts/day_rhythm/mariyam_day_rhythm.py.
_OPENERS = (
    "Ойижон, бир нарсани эслатиб қўяй",
    "Ойижон, мулойим эслатма",
    "Ойижон, ёдингизга солай",
)
_ADVANCE = "{name} тўлови {lead} кундан кейин{amount}"
_DUE_TODAY = "{name} тўлови бугун{amount}"
_OVERDUE = "{name} тўлови кеча ўтиб кетди{amount}"


def _amount_clause(expected_amount_uzs: object) -> str:
    if not isinstance(expected_amount_uzs, (int, float)) or expected_amount_uzs <= 0:
        return ""
    return f", {expected_amount_uzs:,.0f} сўм".replace(",", " ")


def classify(today: date, obligation: dict) -> str | None:
    """Mirror the retired prompt's three mutually exclusive date windows."""
    due = date.fromisoformat(obligation["due_date"])
    lead = obligation["reminder_lead_days"]
    if today == due - timedelta(days=lead):
        return "advance"
    if today == due:
        return "due_today"
    if today == due + timedelta(days=1):
        return "overdue"
    return None


def render_clause(state: str, obligation: dict) -> str:
    amount = _amount_clause(obligation.get("expected_amount_uzs"))
    name = obligation["name"]
    if state == "advance":
        return _ADVANCE.format(name=name, lead=obligation["reminder_lead_days"], amount=amount)
    if state == "due_today":
        return _DUE_TODAY.format(name=name, amount=amount)
    return _OVERDUE.format(name=name, amount=amount)


def build_message(today: date, obligations: list[dict]) -> str | None:
    """Combine every matching obligation into one message; None means silence.

    Safety net kept from the original prompt: never mention an obligation
    that is inactive or already marked paid, even though `active_only=true`
    should already exclude it.
    """
    clauses = []
    for obligation in obligations:
        if not obligation.get("active") or obligation.get("paid"):
            continue
        state = classify(today, obligation)
        if state is not None:
            clauses.append(render_clause(state, obligation))
    if not clauses:
        return None
    opener = _OPENERS[today.toordinal() % len(_OPENERS)]
    return f"{opener}: {'; '.join(clauses)}."


def _load_env_file(path: Path) -> None:
    try:
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()
    except OSError:
        pass


def _bootstrap_backend_import() -> None:
    home_raw = os.environ.get("HERMES_HOME")
    if home_raw:
        _load_env_file(Path(home_raw) / ".env")
    root = os.environ.get("MARIYAM_BACKEND_ROOT")
    if not root:
        raise RuntimeError("MARIYAM_BACKEND_ROOT is not set")
    root_path = Path(root).resolve()
    if not (root_path / "backend").is_dir():
        raise RuntimeError(f"backend package not found under {root_path}")
    sys.path.insert(0, str(root_path))


def _emit(message: str) -> None:
    try:
        scripts_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(scripts_dir))
        from day_rhythm.mariyam_day_rhythm import emit_noncritical
    except Exception:
        print(message, flush=True)
        return
    emit_noncritical(message)


async def _fetch_obligations() -> list[dict]:
    from backend import db
    from backend.config import get_pool

    pool = await get_pool()
    try:
        result = await db.get_recurring_obligations(
            pool, OYIJON_USER_ID, active_only=True
        )
    finally:
        await pool.close()
    return result["obligations"]


def main() -> None:
    try:
        _bootstrap_backend_import()
        import asyncio

        obligations = asyncio.run(_fetch_obligations())
        today = __import__("datetime").datetime.now(TASHKENT).date()
        message = build_message(today, obligations)
    except Exception:
        # Never let a DB hiccup or import error surface as an English/raw
        # error alert in Oyijon's chat (see module docstring). Silent tick.
        return
    if message:
        _emit(message)


if __name__ == "__main__":
    main()
