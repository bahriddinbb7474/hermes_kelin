#!/usr/bin/env python3
import argparse, json, os, subprocess, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

def user_active(unit):
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus")
    return subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", unit], env=env
    ).returncode == 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--failure-unit")
    args = parser.parse_args()
    token, admin = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["ADMIN_TELEGRAM_ID"]
    path = Path(os.environ.get("BACKUP_STATUS_FILE", "/opt/hermes-mariyam/var/backup/last-backup.json"))
    backup = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"ok": False}
    gateway = user_active("hermes-gateway-mariyam_oyijon.service")
    postgres = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", "hermes_mariyam_postgres"], capture_output=True, text=True).stdout.strip()
    if args.failure_unit:
        text = f"🚨 Mariyam: сбой {args.failure_unit}. Gateway={'OK' if gateway else 'DOWN'}, PostgreSQL={postgres or 'unknown'}."
    else:
        text = f"Mariyam heartbeat {datetime.now(timezone.utc):%Y-%m-%d}: Gateway={'OK' if gateway else 'DOWN'}, PostgreSQL={postgres or 'unknown'}, backup={backup.get('uploaded_at', 'нет')}."
    data = urllib.parse.urlencode({"chat_id": admin, "text": text}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise SystemExit("Telegram delivery failed")

if __name__ == "__main__": main()
