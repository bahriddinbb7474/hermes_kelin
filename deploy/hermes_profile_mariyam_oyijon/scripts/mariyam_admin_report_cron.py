"""No-agent replacement for the `mariyam_admin_report_1930` cron job (imp12-opus).

Thin, dependency-free wrapper — see `mariyam_obligation_reminders_cron.py`'s
docstring for why: Hermes runs no-agent `.py` scripts under its own venv,
which does not carry asyncpg/mcp, so the actual DB work happens in
`backend.cron_admin_report`, shelled out to under the backend's own venv
(the same one the MCP stdio server runs under) exactly like the already
deployed `mariyam_health_guard` -> `stage7_record_keyword_alert.py` handoff.

Unlike the Oyijon-facing obligation-reminder script, this job's only reader
is the admin (Бахриддин ака), who already tolerates Russian/technical text
today (SOUL §8's explicit admin exception). So on failure this prints one
honest short line instead of staying silent — a broken report is itself
report-worthy, and silence here would look identical to "nothing happened
today".
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

WORKER_MODULE = "backend.cron_admin_report"
SUBPROCESS_TIMEOUT_SECONDS = 25
TASHKENT = ZoneInfo("Asia/Tashkent")


def _load_env_file(path: Path, env: dict) -> None:
    try:
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if key and key not in env:
                env[key] = value.strip()
    except OSError:
        pass


def _backend_python(root: Path) -> Path:
    posix = root / ".venv" / "bin" / "python"
    if posix.is_file():
        return posix
    return root / ".venv" / "Scripts" / "python.exe"


def _run_worker() -> tuple[str | None, str]:
    """Returns (stdout_or_None, short_diagnostic_reason)."""
    env = dict(os.environ)
    home_raw = env.get("HERMES_HOME")
    if home_raw:
        _load_env_file(Path(home_raw) / ".env", env)
    root_raw = env.get("MARIYAM_BACKEND_ROOT")
    if not root_raw:
        return None, "MARIYAM_BACKEND_ROOT не задан"
    root = Path(root_raw).resolve()
    python = _backend_python(root)
    if not python.is_file():
        return None, "backend python не найден"
    if not (root / "backend").is_dir():
        return None, "backend пакет не найден"
    try:
        completed = subprocess.run(
            [str(python), "-m", WORKER_MODULE],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "таймаут воркера"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}"
    if completed.returncode != 0:
        stderr_lines = (completed.stderr or "").strip().splitlines()
        return None, (stderr_lines[-1] if stderr_lines else "worker exit != 0")
    return completed.stdout.strip(), ""


def main() -> None:
    today_iso = __import__("datetime").datetime.now(TASHKENT).date().isoformat()
    try:
        message, reason = _run_worker()
    except Exception as exc:  # noqa: BLE001 - admin tolerates a short diagnostic
        message, reason = None, type(exc).__name__
    if message:
        print(message)
    else:
        print(
            f"Отчёт за {today_iso} не собрался (Бахриддин ака): "
            f"{reason or 'неизвестная ошибка'}. См. agent.log."
        )


if __name__ == "__main__":
    main()
