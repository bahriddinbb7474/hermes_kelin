"""No-agent replacement for the `mariyam_admin_report_1930` cron job (imp12-opus).

Same read-only tool (`get_admin_report_data`), same five facts requested by
the retired `cron/07_admin_report.md` prompt (kept in the repo for reference
and instant rollback via `hermes cron edit <id> --agent`): day totals, month
totals by group, plan status, due/overdue obligations, today's alerts. All
numbers come straight from `backend.db.admin_report_data` — nothing is
computed or guessed here, matching "Ничего не вычисляй и не придумывай
самостоятельно" from the old prompt. Health-note text, diagnoses and
Telegram/internal IDs were never part of that dict's return shape, so there
is nothing to accidentally leak.

Unlike the Oyijon-facing obligation-reminder script, this job's only reader
is the admin (Бахриддин ака), who already tolerates Russian/technical text
today (SOUL §8's explicit admin exception). So on failure this prints one
honest short line instead of staying silent — a broken report is itself
report-worthy, and silence here would look identical to "nothing happened
today".
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
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


async def _fetch_report(today_iso: str) -> dict:
    from backend import db
    from backend.config import get_pool

    pool = await get_pool()
    try:
        return await db.admin_report_data(pool, OYIJON_USER_ID, today_iso)
    finally:
        await pool.close()


def main() -> None:
    import datetime

    today_iso = datetime.datetime.now(TASHKENT).date().isoformat()
    try:
        _bootstrap_backend_import()
        import asyncio

        data = asyncio.run(_fetch_report(today_iso))
        print(render_report(data))
    except Exception as exc:  # noqa: BLE001 - admin tolerates a short diagnostic
        print(
            f"Отчёт за {today_iso} не собрался (Бахриддин ака): "
            f"{type(exc).__name__}. См. agent.log."
        )


if __name__ == "__main__":
    main()
