"""Stage 7 deterministic health-alert guard and dataset contracts."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[1]
PLUGIN = (
    REPO / "deploy" / "hermes_plugins" / "mariyam_health_guard" / "__init__.py"
)
DATASET = REPO / "tests" / "data" / "stage7_health_alert_phrases.json"
SOUL = REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "SOUL.md"
CONFIG = (
    REPO
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "config.skill-protect.snippet.yaml"
)

spec = importlib.util.spec_from_file_location("mariyam_health_guard_test", PLUGIN)
guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(guard)


def _dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def test_keyword_dataset_recall_100_percent_and_trigger_identity():
    data = _dataset()
    assert len(data["positive"]) == 35
    detected = [
        (item, guard.detect_health_keyword(item["text"]))
        for item in data["positive"]
    ]
    misses = [item["text"] for item, trigger in detected if trigger is None]
    wrong = [
        (item["text"], trigger, item["trigger"])
        for item, trigger in detected
        if trigger is not None and trigger != item["trigger"]
    ]
    assert misses == []
    assert wrong == []


def test_keyword_dataset_precision_has_no_negative_false_alerts():
    data = _dataset()
    assert len(data["negative"]) >= 20
    false_positives = [
        text for text in data["negative"]
        if guard.detect_health_keyword(text) is not None
    ]
    assert false_positives == []


def test_keyword_layer_accepts_narrow_openai_stt_chest_variants():
    assert guard.detect_health_keyword("Какрагим оғрияпт.") == "chest_pain"
    assert guard.detect_health_keyword("Какрагим оғряпт.") == "chest_pain"
    assert guard.detect_health_keyword("Кокрагим қаттиқ оғрияпти.") == "chest_pain"
    assert guard.detect_health_keyword("Какрагим яхши.") is None


def test_keyword_layer_accepts_narrow_openai_stt_breathing_variant():
    assert (
        guard.detect_health_keyword("Нафас олишим қийн.")
        == "breathing_difficulty"
    )
    assert guard.detect_health_keyword("Нафас олишим яхши.") is None


def test_keyword_layer_handles_negated_russian_davlenie_variants():
    assert guard.detect_health_keyword("Давлениям баланд") == "high_blood_pressure"
    assert guard.detect_health_keyword("Давлениям юқори эмас") is None
    assert guard.detect_health_keyword("Давлениям яхши, юқори эмас") is None
    assert guard.detect_health_keyword("Қон босимим баланд эмас") is None
    assert guard.detect_health_keyword("Босимим кўтарилди") == "high_blood_pressure"
    assert (
        guard.detect_health_keyword("Давлениям бугун жуда баланд")
        == "high_blood_pressure"
    )
    assert guard.detect_health_keyword("Давлениям 108/67") is None


def test_guard_rejects_untrusted_sender_before_dispatch(tmp_path, monkeypatch):
    mapping = tmp_path / "identity.json"
    mapping.write_text(
        json.dumps(
            {
                "10001": {
                    "user_id": 1,
                    "role": "oyijon",
                    "display_name": "Test Oyijon",
                },
                "20002": {
                    "user_id": 2,
                    "role": "admin",
                    "display_name": "Admin",
                    "allowed_target_user_ids": [1],
                },
            }
        ),
        encoding="utf-8",
    )
    mapping.chmod(stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(mapping))
    event = SimpleNamespace(
        text="Юрагим оғрияпти.",
        message_id="m1",
        source=SimpleNamespace(
            platform=SimpleNamespace(value="telegram"),
            user_id="99999",
        ),
    )
    assert guard.on_pre_gateway_dispatch(event=event, gateway=object()) is None


def test_trusted_keyword_is_rewritten_and_dispatch_claimed(tmp_path, monkeypatch):
    mapping = tmp_path / "identity.json"
    mapping.write_text(
        json.dumps(
            {
                "10001": {
                    "user_id": 1,
                    "role": "oyijon",
                    "display_name": "Test Oyijon",
                },
                "20002": {
                    "user_id": 2,
                    "role": "admin",
                    "display_name": "Admin",
                    "allowed_target_user_ids": [1],
                },
            }
        ),
        encoding="utf-8",
    )
    mapping.chmod(stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.setenv("MARIYAM_IDENTITY_MAP_FILE", str(mapping))
    monkeypatch.setattr(guard, "_claim_event", lambda _key, _trigger: True)
    scheduled = []

    def capture(coro):
        scheduled.append(coro)
        coro.close()

    monkeypatch.setattr(guard, "_schedule", capture)
    event = SimpleNamespace(
        text="Юрагим оғрияпти.",
        message_id="m1",
        source=SimpleNamespace(
            platform=SimpleNamespace(value="telegram"),
            user_id="10001",
        ),
    )
    result = guard.on_pre_gateway_dispatch(event=event, gateway=object())
    assert result["action"] == "rewrite"
    assert result["text"].startswith("[MARIYAM_HEALTH_GUARD_RECORDED:")
    assert result["text"].endswith(event.text)
    assert len(scheduled) == 1


def test_durable_event_claim_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert guard._claim_event("a" * 64, "heart_pain") is True
    assert guard._claim_event("a" * 64, "heart_pain") is False
    if os.name == "posix":
        mode = (tmp_path / guard.STATE_FILE).stat().st_mode
        assert stat.S_IMODE(mode) & (stat.S_IWGRP | stat.S_IWOTH) == 0


def test_llm_alert_tool_success_schedules_independent_delivery(monkeypatch):
    scheduled = []

    def capture(coro):
        scheduled.append(coro)
        coro.close()

    monkeypatch.setattr(guard, "_schedule", capture)
    result = guard.on_tool_execution_middleware(
        tool_name="mcp__mariyam_backend__save_alert_event",
        args={
            "source_text": "semantic alert",
            "sent_to_admin": True,
        },
        next_call=lambda args: json.dumps({"ok": True, "id": 7}),
    )
    assert json.loads(result)["ok"] is True
    assert len(scheduled) == 1


def test_profile_enables_guard_in_safe_order_and_soul_hides_marker():
    text = CONFIG.read_text(encoding="utf-8")
    identity = text.index("- mariyam_identity_guard")
    health = text.index("- mariyam_health_guard")
    reliability = text.index("- mariyam_cron_reliability")
    stage53 = text.index("- mariyam_stage53_guard")
    assert identity < health < reliability < stage53
    soul = SOUL.read_text(encoding="utf-8")
    assert "MARIYAM_HEALTH_GUARD_RECORDED" in soul
    assert "НЕ вызывай `save_alert_event` повторно" in soul
    assert "Не показывай исходные" in soul
    assert "health-фразы, тексты health_notes" in soul


def test_plugin_manifest_and_writer_contract_are_present():
    manifest = PLUGIN.with_name("plugin.yaml").read_text(encoding="utf-8")
    assert 'version: "1.0.0"' in manifest
    assert "pre_gateway_dispatch" in PLUGIN.read_text(encoding="utf-8")
    writer = (
        REPO
        / "deploy"
        / "hermes_profile_mariyam_oyijon"
        / "scripts"
        / "stage7_record_keyword_alert.py"
    ).read_text(encoding="utf-8")
    assert "db.save_alert_event" in writer
    assert "source_text" in writer
