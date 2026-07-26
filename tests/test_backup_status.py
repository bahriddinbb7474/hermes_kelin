import json

import pytest

from backend import backup_status, server


def test_missing_status_is_real_negative(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_STATUS_FILE", str(tmp_path / "missing.json"))
    assert backup_status.read_backup_status() == {
        "ok": True, "last_ok": False, "last_backup_at": None,
        "archive": None, "uploaded": False,
    }


@pytest.mark.asyncio
async def test_backup_tools_are_read_only_status(monkeypatch, tmp_path):
    status = {
        "ok": True,
        "archive": "mariyam_2026-07-26T07-20-40Z.tar.gz.gpg",
        "uploaded_at": "2026-07-26T07:20:45Z",
        "sha256": "a" * 64,
    }
    path = tmp_path / "last-backup.json"
    path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setenv("BACKUP_STATUS_FILE", str(path))
    got = await server.t_get_backup_status(None, {})
    assert got["last_ok"] is True and got["uploaded"] is True
    triggered = await server.t_backup_data(None, {})
    assert triggered["read_only"] is True
