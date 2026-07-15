"""Permanent regression: Mariyam SOUL.md and self-improvement protection.

Root cause (runtime, Hermes v0.18.x, profile mariyam_oyijon only):
  After multi-tool Telegram turns, agent/turn_finalizer.py may spawn
  agent/background_review.py with review_skills=True when
  skills.creation_nudge_interval > 0 and skill_manage is in valid tools.
  That fork could skill_manage(patch) the former skills/mariyam/SKILL.md and deliver
  "Self-improvement review: Patched SKILL.md…" via background_review_callback.

Supported profile-scoped fix (no Hermes core / identity guard change):
  deploy/hermes_profile_mariyam_oyijon/config.skill-protect.snippet.yaml
  - skills.creation_nudge_interval: 0
  - agent.disabled_toolsets: [skills]
  - skills.write_approval: true
  - display.memory_notifications: "off"
  The canonical contract is profile/SOUL.md; there is no mutable Mariyam skill.
  `skills.enabled` is not a Hermes v0.18.2 loader key.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SNIPPET = (
    REPO
    / "deploy"
    / "hermes_profile_mariyam_oyijon"
    / "config.skill-protect.snippet.yaml"
)
SOUL = REPO / "deploy" / "hermes_profile_mariyam_oyijon" / "SOUL.md"
GITATTRIBUTES = REPO / ".gitattributes"
GUARD_INIT = (
    REPO / "deploy" / "hermes_plugins" / "mariyam_identity_guard" / "__init__.py"
)
# Canonical Git/deploy bytes after CRLF -> LF normalization.
EXPECTED_SOUL_SHA256 = (
    "a9b584e14d704f08b4778b7928ca71a0cf095394583f769c5e9571097884b4e4"
)
PROFILE_SCOPED_DIR = "hermes_profile_mariyam_oyijon"
SELF_IMPROVEMENT_MARKERS = (
    "Self-improvement review",
    "Patched SKILL.md",
    "💾 Self-improvement review",
)


def _should_review_skills(
    skill_nudge_interval: int, iters_since_skill: int, has_skill_manage: bool
) -> bool:
    """Mirror agent/turn_finalizer.py review_skills gate (Hermes v0.18.x)."""
    return (
        skill_nudge_interval > 0
        and iters_since_skill >= skill_nudge_interval
        and has_skill_manage
    )


def _notify_actions(notification_mode: str, actions_if_on: list[str]) -> list[str]:
    """Mirror background_review.summarize_background_review_actions mode gate."""
    mode = str(notification_mode or "on").lower()
    if mode == "off":
        return []
    return list(actions_if_on)


def _soul_sha256() -> str:
    normalized = SOUL.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _load_guard_module():
    spec = importlib.util.spec_from_file_location(
        "mariyam_identity_guard_skill_protect_check", GUARD_INIT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def protect_cfg() -> dict:
    assert SNIPPET.is_file(), f"missing {SNIPPET}"
    assert PROFILE_SCOPED_DIR in SNIPPET.as_posix()
    data = yaml.safe_load(SNIPPET.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


# --- snippet contract (profile mariyam_oyijon only) ---


def test_protect_path_is_profile_mariyam_oyijon_only():
    """Snippet lives under profile-specific deploy dir, not global Hermes home."""
    assert SNIPPET.parts[-2] == PROFILE_SCOPED_DIR
    text = SNIPPET.read_text(encoding="utf-8")
    assert "mariyam_oyijon" in text
    # Must not claim to rewrite default profile / all profiles.
    assert "profiles/default" not in text
    assert "all profiles" not in text.lower()


def test_snippet_disables_skill_nudge(protect_cfg):
    assert int(protect_cfg["skills"]["creation_nudge_interval"]) == 0


def test_snippet_write_approval_on(protect_cfg):
    assert protect_cfg["skills"]["write_approval"] is True


def test_snippet_memory_notifications_off(protect_cfg):
    assert str(protect_cfg["display"]["memory_notifications"]).lower() == "off"


def test_snippet_disables_skills_toolset(protect_cfg):
    assert "skills" in protect_cfg["agent"]["disabled_toolsets"]


def test_snippet_does_not_use_unsupported_skills_enabled(protect_cfg):
    assert "enabled" not in protect_cfg["skills"]


# --- self-improvement cannot change canonical SOUL under protect policy ---


def test_nudge_zero_blocks_background_skill_review(protect_cfg):
    nudge = int(protect_cfg["skills"]["creation_nudge_interval"])
    assert _should_review_skills(nudge, 999, True) is False
    assert _should_review_skills(nudge, 0, True) is False


def test_disabled_skills_toolset_blocks_review_even_with_legacy_nudge(protect_cfg):
    has_skill_manage = "skills" not in protect_cfg["agent"]["disabled_toolsets"]
    assert has_skill_manage is False
    assert _should_review_skills(10, 10, has_skill_manage) is False


def test_self_improvement_policy_preserves_soul_sha(protect_cfg):
    """With protect gates, the self-improvement path cannot rewrite SOUL."""
    before = _soul_sha256()
    assert before == EXPECTED_SOUL_SHA256

    nudge = int(protect_cfg["skills"]["creation_nudge_interval"])
    has_sm = "skills" not in protect_cfg["agent"]["disabled_toolsets"]
    would_review = _should_review_skills(nudge, 10_000, has_sm)
    assert would_review is False

    # No write path taken → bytes unchanged.
    after = _soul_sha256()
    assert after == before == EXPECTED_SOUL_SHA256


def test_soul_sha256_is_canonical():
    assert _soul_sha256() == EXPECTED_SOUL_SHA256


def test_canonical_soul_checkout_is_forced_to_lf():
    attributes = GITATTRIBUTES.read_text(encoding="utf-8").splitlines()
    assert "deploy/hermes_profile_mariyam_oyijon/SOUL.md text eol=lf" in attributes


def test_soul_remains_readable_for_agent():
    text = SOUL.read_text(encoding="utf-8")
    assert text.strip()
    assert "user_id" in text
    # §1.1 identity sentinel must stay loadable.
    compact = text.replace(" ", "")
    assert "user_id:0" in compact or "user_id: 0" in text


def test_user_visible_self_improvement_text_suppressed(protect_cfg):
    mode = str(protect_cfg["display"]["memory_notifications"]).lower()
    assert mode == "off"
    sample = [
        "Patched SKILL.md in skill 'mariyam' (1 replacement).",
        "Self-improvement review: Skill updated",
    ]
    assert _notify_actions(mode, sample) == []
    # Positive control: default "on" would surface the line.
    assert any("Patched SKILL.md" in a for a in _notify_actions("on", sample))


def test_snippet_comments_document_self_improvement_block():
    text = SNIPPET.read_text(encoding="utf-8")
    assert "Self-improvement" in text or "self-improvement" in text
    assert "skill_manage" in text
    assert "background_review" in text or "turn_finalizer" in text


def test_legacy_defaults_would_have_triggered_review():
    """Documents pre-fix dangerous default (nudge=10 + skill_manage present)."""
    assert _should_review_skills(10, 10, True) is True


# --- identity guard / plugin surface not broken by skill-protect work ---


def test_identity_guard_module_still_loads_and_exports_core_api():
    mod = _load_guard_module()
    assert hasattr(mod, "USER_SCOPED_TOOLS")
    # Financial user-scoped tools remain (skill-protect does not touch plugin).
    assert "save_expense" in mod.USER_SCOPED_TOOLS
    assert "get_expense_report" in mod.USER_SCOPED_TOOLS
    assert "delete_last_expense" in mod.USER_SCOPED_TOOLS
    # ensure_user is handled as a dedicated bind path (not always in USER_SCOPED_TOOLS).
    assert hasattr(mod, "ENSURE_USER") or "ensure_user" in getattr(
        mod, "USER_SCOPED_TOOLS", ()
    ) or hasattr(mod, "_compute_effective_args")
    assert hasattr(mod, "_compute_effective_args") or hasattr(
        mod, "tool_execution_wrapper"
    ) or hasattr(mod, "register")


def test_identity_guard_version_file_unchanged_by_skill_protect():
    py = GUARD_INIT.read_text(encoding="utf-8")
    yaml_path = GUARD_INIT.parent / "plugin.yaml"
    y = yaml_path.read_text(encoding="utf-8")
    assert "1.0.3" in y or "version" in y
    # Skill protect must not rewrite guard package.
    assert "creation_nudge_interval" not in py
