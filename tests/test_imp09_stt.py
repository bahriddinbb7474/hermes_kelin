"""imp09 OpenAI STT fallback and recurring prompt contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
STT_PATH = REPO / "deploy" / "stt" / "mariyam_openai_stt.py"
PATCH_PATH = REPO / "deploy" / "imp09_patch_stt_config.py"
SOUL_PATH = REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "SOUL.md"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stt = _load(STT_PATH, "mariyam_openai_stt_test")
patch = _load(PATCH_PATH, "imp09_patch_stt_config_test")


def test_api_success_does_not_call_local(monkeypatch, tmp_path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"audio")
    monkeypatch.setattr(
        stt, "transcribe_openai", lambda *_args: "ўн икки минг"
    )
    monkeypatch.setattr(
        stt,
        "transcribe_local",
        lambda *_args: (_ for _ in ()).throw(AssertionError("local called")),
    )

    text, provider, reason = stt.transcribe_with_fallback(
        audio, "gpt-4o-transcribe", "uz"
    )

    assert text == "ўн икки минг"
    assert provider == "openai"
    assert reason is None


def test_api_failure_uses_local_without_leaking_error(monkeypatch, tmp_path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"audio")

    def fail(*_args):
        raise TimeoutError("secret-bearing provider detail")

    monkeypatch.setattr(stt, "transcribe_openai", fail)
    monkeypatch.setattr(
        stt, "transcribe_local", lambda *_args: "маҳаллий матн"
    )

    text, provider, reason = stt.transcribe_with_fallback(
        audio, "gpt-4o-mini-transcribe", "uz"
    )

    assert text == "маҳаллий матн"
    assert provider == "local"
    assert reason == "TimeoutError"
    assert "secret-bearing" not in reason


def test_unsupported_uz_code_is_guided_by_prompt_only():
    assert stt._language_kwargs("uz") == {}
    assert stt._language_kwargs("") == {}
    assert stt._language_kwargs("en") == {"language": "en"}


def test_api_timeout_budget_leaves_room_for_local_fallback():
    worst_case_api_budget = (
        stt.OPENAI_TIMEOUT_SECONDS * (stt.OPENAI_MAX_RETRIES + 1)
    )
    assert worst_case_api_budget <= 50
    assert worst_case_api_budget < 120


def test_config_patch_is_idempotent_and_keeps_unrelated_content():
    original = [
        "model:",
        "  default: existing",
        "stt:",
        "  provider: local",
        "  local:",
        "    model: base",
        "cron:",
        "  wrap_response: false",
    ]
    once = patch.replace_top_level_block(
        original, "stt", patch.stt_block("gpt-4o-transcribe")
    )
    twice = patch.replace_top_level_block(
        once, "stt", patch.stt_block("gpt-4o-transcribe")
    )

    assert once == twice
    assert "  default: existing" in once
    assert "  wrap_response: false" in once
    assert once.count("stt:") == 1
    assert "      model: gpt-4o-transcribe" in once
    assert not any("OPENAI_API_KEY" in line for line in once)


def test_recurring_prompt_requires_database_tool_not_cron():
    soul = SOUL_PATH.read_text(encoding="utf-8")
    assert "upsert_recurring_obligation" in soul
    assert "recurring_obligations" in soul
    assert "не создавай Hermes cron" in soul
