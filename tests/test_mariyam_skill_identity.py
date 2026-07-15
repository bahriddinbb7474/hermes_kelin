"""Permanent regression: canonical SOUL.md identity/sentinel contract (Этап 5).

These tests pin the *instruction* surface that keeps the model from refusing
financial tools when Hermes v0.18.2 does not inject origin.user_id into the LLM
context. Runtime binding itself is covered by test_mariyam_identity_guard.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROMPT = REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "SOUL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert PROMPT.is_file(), f"missing {PROMPT}"
    return PROMPT.read_text(encoding="utf-8")


def test_skill_has_identity_section_1_1(skill_text):
    assert "## 1.1. Идентичность пользователя" in skill_text


def test_skill_missing_origin_does_not_forbid_tool_call(skill_text):
    assert "НЕ повод отказываться от tool" in skill_text
    # Old harmful rule (VPS FAIL path) must stay gone.
    assert "при неуверенности в" not in skill_text or "НЕ вызывать write-tools" not in skill_text
    assert "НЕ вызывать финансовые/health/tools" not in skill_text


def test_skill_requires_sentinel_user_id_zero(skill_text):
    assert "user_id: 0" in skill_text
    assert "sentinel" in skill_text.lower() or "Обязательный sentinel" in skill_text


def test_skill_forbids_identity_from_display_name(skill_text):
    assert "display_name" in skill_text
    assert "chat_name" in skill_text
    assert "никогда" in skill_text
    # Must not teach display_name → user_id binding.
    assert "определять пользователя по" in skill_text or "Запрещено" in skill_text


def test_skill_no_ensure_user_on_ordinary_messages(skill_text):
    assert "Не вызывай `ensure_user` в обычных сообщениях" in skill_text


def test_skill_financial_intent_requires_mcp_tool(skill_text):
    assert "Финансовое намерение" in skill_text
    assert "save_expense" in skill_text
    assert "идентификатор аниқланмади" in skill_text
    # Explicit: do not answer that phrase *instead of* a tool-call.
    assert "вместо tool-call" in skill_text


def test_skill_identity_errors_no_retry_with_other_user_id(skill_text):
    for code in (
        "IDENTITY_UNRESOLVED",
        "IDENTITY_GUARD_ERROR",
        "IDENTITY_TARGET_FORBIDDEN",
    ):
        assert code in skill_text
    assert "повторяй с другим `user_id`" in skill_text
    assert "подставляй admin" in skill_text