import json
import os
from pathlib import Path

DEFAULT_STATUS_FILE = "/opt/hermes-mariyam/var/backup/last-backup.json"


def read_backup_status() -> dict:
    path = Path(os.environ.get("BACKUP_STATUS_FILE", DEFAULT_STATUS_FILE))
    if not path.is_file():
        return {
            "ok": True, "last_ok": False, "last_backup_at": None,
            "archive": None, "uploaded": False,
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        archive = raw["archive"]
        uploaded_at = raw["uploaded_at"]
        sha256 = raw["sha256"]
        if not isinstance(archive, str) or not isinstance(uploaded_at, str) or len(sha256) != 64:
            raise ValueError("invalid backup status fields")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "ok": True, "last_ok": False, "last_backup_at": None,
            "archive": None, "uploaded": False,
        }
    return {
        "ok": True,
        "last_ok": bool(raw.get("ok")),
        "last_backup_at": uploaded_at,
        "archive": archive,
        "uploaded": bool(raw.get("ok")),
        "sha256": sha256,
    }
