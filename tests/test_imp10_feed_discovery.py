"""imp10: finding a site's feed by its address, without weakening SSRF defence.

Oyijon says «I want to read Дарё» — she will never know that the feed lives at
some /rss path. The site address is now accepted, and the feed it advertises in
<head> is fetched through the same safety path as a hand-typed one: https only,
public addresses, pinned connection, bounded redirects, size cap, mandatory
RSS/Atom parse.
"""
from __future__ import annotations

import pytest

from backend import external_data, server

RSS = (
    "<rss><channel><item><title>Хабар</title>"
    "<link>https://news.example/item</link></item></channel></rss>"
).encode("utf-8")

PAGE = """<!doctype html><html><head>
<title>Дарё</title>
<link rel="alternate" type="application/rss+xml" title="RSS" href="{href}">
</head><body>...</body></html>"""


def _public_dns(monkeypatch, address="93.184.216.34"):
    monkeypatch.setattr(
        external_data.socket, "getaddrinfo",
        lambda host, port, type=0: [(2, 1, 6, "", (address, port))],
    )


def _serve(monkeypatch, routes: dict[str, bytes]):
    """Answer each URL with its own payload; unknown URLs 404."""
    seen: list[str] = []

    def fake_get(url, parsed, address):
        seen.append(url)
        if url in routes:
            return 200, {}, routes[url]
        return 404, {}, b""

    monkeypatch.setattr(external_data, "_https_get_pinned", fake_get)
    return seen


# --- unchanged behaviour for a direct feed ---------------------------------


def test_direct_feed_is_used_as_is(monkeypatch):
    _public_dns(monkeypatch)
    _serve(monkeypatch, {"https://example.com/rss": RSS})
    feed_url, payload = external_data.resolve_feed_url("https://example.com/rss")
    assert feed_url == "https://example.com/rss"
    assert payload == RSS


def test_validate_returns_the_feed_url_for_a_direct_feed(monkeypatch):
    _public_dns(monkeypatch)
    _serve(monkeypatch, {"https://example.com/rss": RSS})
    feed_url, _ = external_data.validate_user_news_feed(
        "https://example.com/rss", "Техника хабарлари", ["техника"]
    )
    assert feed_url == "https://example.com/rss"


# --- discovery from a site page --------------------------------------------


def test_absolute_feed_link_in_head_is_discovered(monkeypatch):
    _public_dns(monkeypatch)
    seen = _serve(monkeypatch, {
        "https://daryo.example": PAGE.format(href="https://daryo.example/feed/").encode("utf-8"),
        "https://daryo.example/feed/": RSS,
    })
    feed_url, payload = external_data.resolve_feed_url("https://daryo.example")
    assert feed_url == "https://daryo.example/feed/"
    assert payload == RSS
    assert seen == ["https://daryo.example", "https://daryo.example/feed/"]


def test_relative_feed_link_is_resolved_against_the_page(monkeypatch):
    _public_dns(monkeypatch)
    _serve(monkeypatch, {
        "https://daryo.example/news": PAGE.format(href="/rss.xml").encode("utf-8"),
        "https://daryo.example/rss.xml": RSS,
    })
    feed_url, _ = external_data.resolve_feed_url("https://daryo.example/news")
    assert feed_url == "https://daryo.example/rss.xml"


def test_atom_link_is_accepted(monkeypatch):
    _public_dns(monkeypatch)
    page = (
        '<html><head><link rel="alternate" type="application/atom+xml" '
        'href="https://blog.example/atom">'
    ).encode("utf-8")
    _serve(monkeypatch, {"https://blog.example": page, "https://blog.example/atom": RSS})
    feed_url, _ = external_data.resolve_feed_url("https://blog.example")
    assert feed_url == "https://blog.example/atom"


def test_first_declared_feed_wins(monkeypatch):
    _public_dns(monkeypatch)
    page = (
        '<html><head>'
        '<link rel="alternate" type="application/rss+xml" href="https://s.example/one">'
        '<link rel="alternate" type="application/rss+xml" href="https://s.example/two">'
        '</head>'
    ).encode("utf-8")
    seen = _serve(monkeypatch, {"https://s.example": page, "https://s.example/one": RSS})
    feed_url, _ = external_data.resolve_feed_url("https://s.example")
    assert feed_url == "https://s.example/one"
    assert "https://s.example/two" not in seen


def test_site_without_a_feed_is_refused_honestly(monkeypatch):
    _public_dns(monkeypatch)
    _serve(monkeypatch, {"https://plain.example": b"<html><head><title>No feed</title></head>"})
    with pytest.raises(external_data.ExternalDataError, match="does not advertise"):
        external_data.resolve_feed_url("https://plain.example")


# --- the security boundary (case 5 of the task) -----------------------------


def test_feed_declared_on_a_private_address_is_rejected(monkeypatch):
    """A page may advertise anything; the discovered URL is still untrusted."""
    def dns(host, port, type=0):
        if host == "internal.example":
            return [(2, 1, 6, "", ("127.0.0.1", port))]
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(external_data.socket, "getaddrinfo", dns)
    seen = _serve(monkeypatch, {
        "https://evil.example": PAGE.format(href="https://internal.example/feed").encode("utf-8"),
        "https://internal.example/feed": RSS,
    })
    with pytest.raises(external_data.ExternalDataError, match="non-public"):
        external_data.resolve_feed_url("https://evil.example")
    assert "https://internal.example/feed" not in seen, "must fail before the request"


def test_plain_http_feed_link_is_ignored(monkeypatch):
    _public_dns(monkeypatch)
    _serve(monkeypatch, {
        "https://mixed.example": PAGE.format(href="http://mixed.example/rss").encode("utf-8"),
    })
    with pytest.raises(external_data.ExternalDataError, match="does not advertise"):
        external_data.resolve_feed_url("https://mixed.example")


def test_discovery_is_single_level(monkeypatch):
    """A discovered address that is itself a page is not scanned again."""
    _public_dns(monkeypatch)
    _serve(monkeypatch, {
        "https://loop.example": PAGE.format(href="https://loop.example/a").encode("utf-8"),
        "https://loop.example/a": PAGE.format(href="https://loop.example/b").encode("utf-8"),
        "https://loop.example/b": RSS,
    })
    with pytest.raises(external_data.ExternalDataError, match="invalid RSS"):
        external_data.validate_user_news_feed(
            "https://loop.example", "Техника хабарлари", []
        )


def test_only_the_head_is_scanned(monkeypatch):
    _public_dns(monkeypatch)
    body_link = (
        "<html><head><title>Дарё</title></head><body>"
        + "x" * 1000
        + '<link rel="alternate" type="application/rss+xml" href="https://late.example/rss">'
        + "</body></html>"
    ).encode("utf-8")
    _serve(monkeypatch, {"https://late.example": body_link})
    with pytest.raises(external_data.ExternalDataError, match="does not advertise"):
        external_data.resolve_feed_url("https://late.example")


def test_scan_window_is_bounded(monkeypatch):
    _public_dns(monkeypatch)
    padded = (
        "<html><head>" + "<!--" + "x" * (external_data.HTML_HEAD_SCAN_BYTES + 100) + "-->"
        + '<link rel="alternate" type="application/rss+xml" href="https://far.example/rss">'
        + "</head></html>"
    ).encode("utf-8")
    _serve(monkeypatch, {"https://far.example": padded})
    with pytest.raises(external_data.ExternalDataError, match="does not advertise"):
        external_data.resolve_feed_url("https://far.example")


# --- contract ---------------------------------------------------------------


def test_no_new_tool_was_introduced():
    assert len(server.TOOLS) == len(server.DISPATCH) == 30
    entry = next(item for item in server.TOOLS if item[0] == "manage_news_sources")
    assert "url" in entry[2]["properties"]


def test_head_scan_limit_is_modest():
    assert external_data.HTML_HEAD_SCAN_BYTES <= 128 * 1024
    assert external_data.MAX_RESPONSE_BYTES == 2_000_000
