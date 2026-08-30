"""Worker half of the no-agent `mariyam_obligation_reminders` cron job (imp12-opus).

Runs under the backend's own venv (`/opt/hermes-mariyam/.venv/bin/python`,
which has asyncpg/mcp installed), invoked as a subprocess by the thin
dependency-free wrapper `<profile>/scripts/mariyam_obligation_reminders_cron.py`
that Hermes actually executes under its own venv (which does not have
asyncpg — Hermes' `sys.executable` no-agent contract runs scripts under the
Hermes install's interpreter, not a project-specific one; see the wrapper's
docstring for the split rationale). Same read-only tool
(`get_recurring_obligations`) and the same three-state date window and
"one combined message, never invent a sum" rules that used to live in
`cron/06_obligation_reminders.md` (kept in the repo for reference / instant
rollback via `hermes cron edit <id> --agent`).

Prints the finished Uzbek Cyrillic message to stdout, or nothing at all when
no obligation matches today (the wrapper treats both empty stdout and any
non-zero exit as silence — see its docstring for why failures must never
surface as raw text in Oyijon's chat).
"""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

# Single-family profile: this is the same internal `users.id` the identity
# guard's private cron mapping already resolves for every Oyijon-facing
# trusted job (role='oyijon'). Verified against the live `users` table during
# imp12-opus; update alongside the cron identity mapping if it ever changes.
OYIJON_USER_ID = 20

TASHKENT = ZoneInfo("Asia/Tashkent")

# Rotate by day-of-year so the same phrasing never repeats two days running
# (SOUL §2.5), mirroring the rotation already used by
# scripts/day_rhythm/mariyam_day_rhythm.py.
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
    import asyncio

    obligations = asyncio.run(_fetch_obligations())
    today = __import__("datetime").datetime.now(TASHKENT).date()
    message = build_message(today, obligations)
    if message:
        print(message)


if __name__ == "__main__":
    main()
