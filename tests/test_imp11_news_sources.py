"""imp11: user-owned news sources, SSRF boundary and inventory contracts."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from backend import db, external_data, server
from tests.db_guard import validate_destructive_test_target

REPO = Path(__file__).resolve().parents[1]
SQL_001 = REPO / "backend" / "sql" / "001_init.sql"
SQL_006 = REPO / "backend" / "sql" / "006_user_news_sources.sql"

_spec = importlib.util.spec_from_file_location(
    "imp11_identity_guard",
    REPO / "deploy" / "hermes_plugins" / "mariyam_identity_guard" / "__init__.py",
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

RSS = "<rss><channel><item><title>Хабар</title><link>https://news.example/item</link></item></channel></rss>".encode("utf-8")


def _public_dns(monkeypatch):
    monkeypatch.setattr(
        external_data.socket, "getaddrinfo",
        lambda host, port, type=0: [(2, 1, 6, "", ("93.184.216.34", port))],
    )


def test_https_and_private_targets_are_rejected_before_request(monkeypatch):
    called = []
    monkeypatch.setattr(external_data, "_https_get_pinned", lambda *args: called.append(args))
    with pytest.raises(external_data.ExternalDataError, match="https"):
        external_data._safe_feed_get("http://example.com/feed")
    monkeypatch.setattr(
        external_data.socket, "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(external_data.ExternalDataError, match="non-public"):
        external_data._safe_feed_get("https://localhost/feed")
    assert called == []


def test_redirect_destination_is_revalidated_and_private_is_blocked(monkeypatch):
    def dns(host, port, type=0):
        address = "93.184.216.34" if host == "public.example" else "169.254.169.254"
        return [(2, 1, 6, "", (address, port))]

    monkeypatch.setattr(external_data.socket, "getaddrinfo", dns)
    monkeypatch.setattr(
        external_data, "_https_get_pinned",
        lambda *args: (302, {"location": "https://metadata.example/feed"}, b""),
    )
    with pytest.raises(external_data.ExternalDataError, match="non-public"):
        external_data._safe_feed_get("https://public.example/feed")


def test_non_feed_and_oversize_response_are_rejected(monkeypatch):
    _public_dns(monkeypatch)
    monkeypatch.setattr(external_data, "_https_get_pinned", lambda *args: (200, {}, b"<html/>"))
    with pytest.raises(external_data.ExternalDataError, match="RSS"):
        external_data.validate_user_news_feed("https://example.com/feed", "Техника хабарлари", [])
    monkeypatch.setattr(
        external_data, "_https_get_pinned",
        lambda *args: (200, {}, b"x" * (external_data.MAX_RESPONSE_BYTES + 1)),
    )
    with pytest.raises(external_data.ExternalDataError, match="too large"):
        external_data._safe_feed_get("https://example.com/feed")


def test_valid_feed_name_generated_key_and_limits(monkeypatch):
    _public_dns(monkeypatch)
    monkeypatch.setattr(external_data, "_https_get_pinned", lambda *args: (200, {}, RSS))
    external_data.validate_user_news_feed("https://example.com/feed", "Техника хабарлари", ["Техника"])
    key = external_data.generated_news_source_key(20, "https://example.com/feed")
    assert 2 <= len(key) <= 40 and key.startswith("custom_")
    assert db.MAX_ACTIVE_NEWS_SOURCES == 15
    with pytest.raises(external_data.ExternalDataError, match="Cyrillic"):
        external_data.validate_user_news_feed("https://example.com/feed", "Tech news", [])


@pytest.mark.asyncio
async def test_inventory_and_tool_contract_are_30():
    tools = await server.list_tools()
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 30
    schema = {tool.name: tool.inputSchema for tool in tools}["manage_news_sources"]
    assert schema["required"] == ["user_id", "action"]
    # imp09 widened the contract: `enable` returns a feed the owner switched
    # off, and `source_key` addresses a shipped feed (custom ones keep using
    # source_id). The tool count stays 30 — no new tool was introduced.
    assert schema["properties"]["action"]["enum"] == ["add", "disable", "enable", "list"]
    assert schema["properties"]["source_key"]["pattern"] == "^[a-z0-9_]{2,40}$"


def test_identity_guard_binds_owner_and_trusted_added_by():
    assert {"manage_news_sources", "get_daily_news"} <= guard.USER_SCOPED_TOOLS
    actor = {"user_id": 20, "role": "oyijon"}
    args, error = guard._compute_effective_args(
        "manage_news_sources", {"user_id": 1, "action": "list", "added_by": "admin"}, actor, 222
    )
    assert error is None and args["user_id"] == 20 and args["added_by"] == "oyijon"
    admin = {"user_id": 1, "role": "admin", "allowed_target_user_ids": [20]}
    args, error = guard._compute_effective_args(
        "manage_news_sources", {"user_id": 20, "action": "list"}, admin, 111
    )
    assert error is None and args["user_id"] == 20 and args["added_by"] == "admin"
    _, error = guard._compute_effective_args(
        "manage_news_sources", {"user_id": 21, "action": "list"}, admin, 111
    )
    assert error == "IDENTITY_TARGET_FORBIDDEN"


def _db_available() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    if os.environ.get("APP_ENV") != "test" or not url:
        return False
    validate_destructive_test_target(
        database_url=url, app_env="test",
        allow_remote=os.environ.get("ALLOW_DESTRUCTIVE_TESTS") == "1",
    )
    return True


@pytest.mark.skipif(not _db_available(), reason="validated disposable PostgreSQL required")
@pytest.mark.asyncio
async def test_migration_006_applies_idempotently_and_rolls_back_cleanly():
    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await conn.execute(SQL_001.read_text(encoding="utf-8"))
        await conn.execute("DROP TABLE IF EXISTS user_news_sources")
        sql = SQL_006.read_text(encoding="utf-8")
        await conn.execute(sql)
        await conn.execute(sql)
        assert await conn.fetchval("SELECT to_regclass('public.user_news_sources')")
        await conn.execute("DROP TABLE user_news_sources")
        assert await conn.fetchval("SELECT to_regclass('public.user_news_sources')") is None
    finally:
        await conn.close()
