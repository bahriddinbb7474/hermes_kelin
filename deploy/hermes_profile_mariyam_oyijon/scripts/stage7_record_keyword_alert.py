"""Persist one already-detected keyword health alert through backend storage."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


backend_root = Path(os.environ.get("MARIYAM_BACKEND_ROOT", ""))
if not backend_root.is_absolute() or not (backend_root / "backend").is_dir():
    raise RuntimeError("MARIYAM_BACKEND_ROOT is invalid")
sys.path.insert(0, str(backend_root))

from backend import db  # noqa: E402
from backend.config import get_pool  # noqa: E402


async def _main() -> None:
    raw = sys.stdin.buffer.read(16 * 1024)
    payload = json.loads(raw.decode("utf-8"))
    if set(payload) != {
        "user_id", "source_text", "bot_response", "sent_to_admin"
    }:
        raise ValueError("invalid payload")
    user_id = payload["user_id"]
    source_text = payload["source_text"]
    bot_response = payload["bot_response"]
    sent_to_admin = payload["sent_to_admin"]
    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
        or not isinstance(source_text, str)
        or not source_text
        or len(source_text) > 1000
        or not isinstance(bot_response, str)
        or not bot_response
        or not isinstance(sent_to_admin, bool)
    ):
        raise ValueError("invalid payload")
    pool = await get_pool()
    try:
        await db.save_alert_event(
            pool,
            user_id,
            "medical",
            "critical",
            source_text,
            bot_response,
            "keyword",
            sent_to_admin,
        )
    finally:
        await pool.close()
    sys.stdout.write("ALERT_RECORDED\n")


if __name__ == "__main__":
    asyncio.run(_main())
