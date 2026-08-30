"""Worker half of the no-agent `mariyam_admin_report_1930` cron job (imp12-opus).

Runs under the backend's own venv, invoked as a subprocess by the thin
dependency-free wrapper `<profile>/scripts/mariyam_admin_report_cron.py`
that Hermes actually executes under its own venv (no asyncpg there — see the
wrapper's docstring for the split rationale). Same read-only tool
(`get_admin_report_data`) and the same five facts requested by the retired
`cron/07_admin_report.md` prompt (kept in the repo for reference and instant
rollback via `hermes cron edit <id> --agent`): day totals, month totals by
group, plan status, due/overdue obligations, today's alerts. All numbers
come straight from `backend.db.admin_report_data` — nothing is computed or
guessed here, matching "Ничего не вычисляй и не придумывай самостоятельно"
from the old prompt. Health-note text, diagnoses and Telegram/internal IDs
were never part of that dict's return shape, so there is nothing to
accidentally leak.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

# Single-family profile: same internal `users.id` the identity guard's
# private cron mapping already resolves for this job today. Verified against
# the live `users` table during imp12-opus.
OYIJON_USER_ID = 20

TASHKENT = ZoneInfo("Asia/Tashkent")
TOP_CATEGORIES = 6


def _fmt_uzs(value: object) -> str:
    try:
        return f"{int(value):,}".replace(",", " ") + " сум"
    except (TypeError, ValueError):
        return "0 сум"


def _fmt_categories(rows: list[dict]) -> str:
    if not rows:
        return "нет расходов"
    top = rows[:TOP_CATEGORIES]
    parts = [f"{row['name_uz']}: {_fmt_uzs(row['sum_uzs'])}" for row in top]
    if len(rows) > TOP_CATEGORIES:
        parts.append("…")
    return "; ".join(parts)


def _fmt_obligations(rows: list[dict], through: str) -> str:
    if not rows:
        return "нет"
    parts = []
    for row in rows:
        tail = ", просрочено" if row.get("overdue") else ""
        parts.append(
            f"{row['name']} — {row['due_date']} "
            f"({_fmt_uzs(row['expected_amount_uzs'])}{tail})"
        )
    return f"{'; '.join(parts)} (до {through})"


def _fmt_alerts(rows: list[dict]) -> str:
    if not rows:
        return "нет"
    by_severity: dict[str, int] = {}
    delivered = 0
    for row in rows:
        by_severity[row["severity"]] = by_severity.get(row["severity"], 0) + 1
        if row.get("sent_to_admin"):
            delivered += 1
    severities = ", ".join(f"{k}×{v}" for k, v in sorted(by_severity.items()))
    return f"{len(rows)} ({severities}), админу доставлено: {delivered}"


def render_report(data: dict) -> str:
    plan = data.get("plan") or {}
    lines = [
        f"Отчёт за {data['date']} (Бахриддин ака).",
        f"День: расход {_fmt_uzs(data['expense_total_uzs'])}, "
        f"доход {_fmt_uzs(data['income_total_uzs'])}.",
        f"Месяц {data['month']}: расход {_fmt_uzs(data['month_expense_total_uzs'])}, "
        f"доход {_fmt_uzs(data['month_income_total_uzs'])}.",
        f"По группам: {_fmt_categories(data.get('month_expense_by_category') or [])}.",
        (
            f"План: статус {plan.get('status') or 'айтилмаган'}, "
            f"план {_fmt_uzs(plan.get('planned_total_uzs'))}, "
            f"факт {_fmt_uzs(plan.get('actual_total_uzs'))}, "
            f"остаток {_fmt_uzs(plan.get('remaining_uzs'))}."
        ),
        (
            "Обязательства: "
            + _fmt_obligations(
                data.get("due_obligations") or [],
                data.get("due_obligations_through", "?"),
            )
            + "."
        ),
        f"Alerts за день: {_fmt_alerts(data.get('alerts') or [])}.",
    ]
    return "\n".join(lines)


async def _fetch_report(today_iso: str) -> dict:
    from backend import db
    from backend.config import get_pool

    pool = await get_pool()
    try:
        return await db.admin_report_data(pool, OYIJON_USER_ID, today_iso)
    finally:
        await pool.close()


def main() -> None:
    import asyncio
    import datetime

    today_iso = datetime.datetime.now(TASHKENT).date().isoformat()
    data = asyncio.run(_fetch_report(today_iso))
    print(render_report(data))


if __name__ == "__main__":
    main()
