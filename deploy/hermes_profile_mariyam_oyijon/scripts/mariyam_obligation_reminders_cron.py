"""No-agent replacement for the `mariyam_obligation_reminders` cron job (imp12-opus).

Converts a daily LLM turn into a plain script: no model call, no MCP
round-trip. Hermes' no-agent contract runs a `.py` script under its own
`sys.executable` (the Hermes install's venv) — which does not, and should
not, carry backend-only dependencies like asyncpg/mcp (verified on the VPS
during imp12-opus: Hermes' venv has neither). So this file is a thin,
dependency-free wrapper: it shells out to `backend.cron_obligation_reminder`
under the backend's OWN venv (same one the MCP stdio server itself runs
under), exactly the way the already-deployed `mariyam_health_guard` plugin
delegates alert recording to `stage7_record_keyword_alert.py` via
`MARIYAM_HEALTH_ALERT_PYTHON`. All the actual logic (date-window rules,
message templates, the `get_recurring_obligations` query) lives in that
worker module, unit-tested independently.

Hermes cron contract for a `no_agent=true` script: non-empty stdout on exit
0 is delivered verbatim, empty stdout is a silent tick, a non-zero exit
delivers a raw error alert. Because this job's audience is Oyijon
(Cyrillic-only, no technical text ever), that last case is unacceptable
here, so every failure path below — worker crash, timeout, missing
interpreter — is swallowed into silence instead of a crash. A missed
reminder is a much smaller harm than an English string landing in her chat,
and the same due/overdue obligations are independently visible to the admin
in the 19:30 admin report the same day.

Quiet hours / prayer-window suppression is not automatic for no-agent jobs
the way `transform_llm_output` gates a normal LLM cron turn, so this script
calls the same `emit_noncritical` used by dynamically created one-shot
reminders to stay consistent with that contract.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WORKER_MODULE = "backend.cron_obligation_reminder"
SUBPROCESS_TIMEOUT_SECONDS = 25


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


def _run_worker() -> str | None:
    env = dict(os.environ)
    home_raw = env.get("HERMES_HOME")
    if home_raw:
        _load_env_file(Path(home_raw) / ".env", env)
    root_raw = env.get("MARIYAM_BACKEND_ROOT")
    if not root_raw:
        return None
    root = Path(root_raw).resolve()
    python = _backend_python(root)
    if not python.is_file() or not (root / "backend").is_dir():
        return None
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
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    message = completed.stdout.strip()
    return message or None


def _emit(message: str) -> None:
    try:
        scripts_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(scripts_dir))
        from day_rhythm.mariyam_day_rhythm import emit_noncritical
    except Exception:
        print(message, flush=True)
        return
    emit_noncritical(message)


def main() -> None:
    try:
        message = _run_worker()
    except Exception:
        # Never let a DB hiccup or environment error surface as an English/
        # raw error alert in Oyijon's chat (see module docstring). Silent tick.
        return
    if message:
        _emit(message)


if __name__ == "__main__":
    main()
