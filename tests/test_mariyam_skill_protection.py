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
  - display.busy_ack_enabled: false
  - display.long_running_notifications: false
  The canonical contract is profile/SOUL.md; there is no mutable Mariyam skill.
  `skills.enabled` is not a Hermes v0.18.2 loader key.

Second root cause (imp05-opus, live 2026-08-01 02:27): after a provider switch
  agent/chat_completion_helpers.py + run_agent.py::_emit_pending_fallback_notice
  push "🔄 Switched to fallback model: …" through the gateway status rail.
  gateway/run.py::_TELEGRAM_NOISY_STATUS_RE has no pattern for it and Hermes has
  no config key, so the English line reached Oyijon. Fix: profile plugin
  deploy/hermes_plugins/mariyam_outbound_filter wraps the rail in-process and
  drops Latin-script status lines on human chat surfaces.

Third root cause (imp05-opus, same run): Hermes reuses the stored system prompt
  for a session's whole life and memory enters it as a frozen snapshot, while
  SessionResetPolicy defaults to mode "none" — so memory written after the
  session started never reaches the model. Fix: `session_reset` in the profile
  snippet (daily rollover at 02:00 local, notify off).

Fourth root cause (fix07/fix08, live Telegram 2026-08-01): the DeepSeek fallback can
  misreport completed mutations and leak internal/provider text into chat.
  It stays excluded. The approved fallback is the same Luna model through
  independent OpenRouter infrastructure; non-Cyrillic provider failure replies
  are replaced on human chat surfaces while raw programmatic diagnostics stay.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
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
OUTBOUND_FILTER_INIT = (
    REPO / "deploy" / "hermes_plugins" / "mariyam_outbound_filter" / "__init__.py"
)
# Canonical Git/deploy bytes after CRLF -> LF normalization.
EXPECTED_SOUL_SHA256 = (
    "6e9fa920af283c53acd760d194077aad5066045cbe70094442f502daa373902d"
)
PROFILE_SCOPED_DIR = "hermes_profile_mariyam_oyijon"
SELF_IMPROVEMENT_MARKERS = (
    "Self-improvement review",
    "Patched SKILL.md",
    "💾 Self-improvement review",
)
FALLBACK_NOTICE = (
    "🔄 Switched to fallback model: gpt-5.6-luna via n1n "
    "→ deepseek/deepseek-chat via openrouter"
)
FALLBACK_SWITCH_LINE = (
    "🔄 Primary model failed — switching to fallback: "
    "deepseek/deepseek-chat via openrouter"
)
# Hermes' own status filter (gateway/run.py::_TELEGRAM_NOISY_STATUS_RE) covers
# these; the provider-switch lines above are NOT in it — that is the defect.
HERMES_FILTERED_STATUS = "Rate limited. Waiting 20s before retrying in 3"
UZBEK_STATUS = "Ойижон, бир дақиқа, маълумотларни кўриб чиқяпман."
RAW_TEXT_PLATFORMS = ("local", "api_server", "webhook", "msgraph_webhook")
BUSY_ACK_MARKERS = (
    "Interrupting current task",
    "Queued for the next turn",
    "Steered into current run",
    "Subagent working",
    "Compressing context",
    "Working —",
    "First-time tip",
    "/busy queue",
    "/busy steer",
    "/busy status",
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


def _busy_ack_messages(
    busy_ack_enabled: bool, acknowledgement: str, onboarding_hint: str
) -> list[str]:
    """Mirror gateway/run.py's early busy-ack gate in Hermes v0.18.2."""
    if not busy_ack_enabled:
        return []
    return [acknowledgement, onboarding_hint]


def _soul_sha256() -> str:
    normalized = SOUL.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_guard_module():
    return _load_module("mariyam_identity_guard_skill_protect_check", GUARD_INIT)


def _load_outbound_filter():
    return _load_module("mariyam_outbound_filter_check", OUTBOUND_FILTER_INIT)


def _installed_hermes_root() -> Path | None:
    configured = os.environ.get("MARIYAM_HERMES_PYTHON")
    roots = []
    if configured:
        candidate = Path(configured)
        if not candidate.is_file():
            return None
        roots.append(candidate.parents[2])
    else:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            roots.append(Path(local_appdata) / "hermes" / "hermes-agent")
        roots.append(Path.home() / ".hermes" / "hermes-agent")

    for root in roots:
        if (root / "gateway" / "run.py").is_file():
            return root
    return None


def _should_reset(mode: str, at_hour: int, updated_hour: int, now_hour: int) -> bool:
    """Mirror gateway/session.py::SessionStore._should_reset daily branch."""
    if mode not in {"daily", "both"}:
        return False
    # today_reset rolls back a day when the clock is still before at_hour.
    reset_hour_today = at_hour if now_hour >= at_hour else at_hour - 24
    return updated_hour < reset_hour_today


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


def test_snippet_busy_ack_disabled(protect_cfg):
    assert protect_cfg["display"]["busy_ack_enabled"] is False


def test_snippet_long_running_notifications_disabled(protect_cfg):
    assert protect_cfg["display"]["long_running_notifications"] is False


def test_snippet_disables_skills_toolset(protect_cfg):
    assert "skills" in protect_cfg["agent"]["disabled_toolsets"]


def test_snippet_disables_all_command_execution_toolsets(protect_cfg):
    disabled = protect_cfg["agent"]["disabled_toolsets"]
    assert "terminal" in disabled
    # Hermes v0.18.2 maps execute_code to code_execution, not terminal.
    assert "code_execution" in disabled


def test_tool_progress_contract_remains_off(protect_cfg):
    assert protect_cfg["display"]["tool_progress"] is False


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


def test_user_visible_busy_ack_text_suppressed(protect_cfg):
    enabled = protect_cfg["display"]["busy_ack_enabled"]
    acknowledgement = "⚡ Interrupting current task. I'll respond shortly."
    hint = (
        "💡 First-time tip — I interrupted my current task. "
        "Send /busy queue, /busy steer, or /busy status."
    )
    assert _busy_ack_messages(enabled, acknowledgement, hint) == []

    # Positive control: the Hermes default would surface both framework strings.
    visible_by_default = _busy_ack_messages(True, acknowledgement, hint)
    assert visible_by_default == [acknowledgement, hint]
    assert all(
        any(marker in message for message in visible_by_default)
        for marker in ("Interrupting current task", "First-time tip", "/busy queue")
    )


def test_busy_ack_contract_covers_adjacent_framework_strings():
    """Document all nearby English busy-layer strings covered by one gate."""
    corpus = "\n".join(BUSY_ACK_MARKERS)
    for marker in (
        "Interrupting",
        "Queued",
        "Steered",
        "Working —",
        "First-time tip",
        "/busy",
    ):
        assert marker in corpus


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


# --- outbound status hygiene: provider-fallback notice (imp05-opus) ---


def test_snippet_enables_outbound_filter_plugin(protect_cfg):
    assert "mariyam_outbound_filter" in protect_cfg["plugins"]["enabled"]


def test_profile_fallback_is_only_luna_via_openrouter(protect_cfg):
    assert protect_cfg["fallback_providers"] == [
        {"provider": "openrouter", "model": "openai/gpt-5.6-luna"}
    ]


def test_outbound_filter_lives_in_profile_plugins_not_hermes_core():
    assert OUTBOUND_FILTER_INIT.is_file()
    assert OUTBOUND_FILTER_INIT.parts[-3] == "hermes_plugins"
    text = OUTBOUND_FILTER_INIT.read_text(encoding="utf-8")
    # In-process wrapper only: no writes into the Hermes install tree.
    assert "hermes-agent" not in text
    assert "sys.modules" in text


def test_fallback_notice_suppressed_on_chat_surface():
    mod = _load_outbound_filter()
    assert mod.should_suppress(FALLBACK_NOTICE, raw_surface=False) is True
    assert mod.should_suppress(FALLBACK_SWITCH_LINE, raw_surface=False) is True


def test_provider_failure_final_reply_becomes_warm_uzbek():
    mod = _load_outbound_filter()
    english = (
        "⚠️ The model provider failed after retries. I kept raw provider "
        "details out of chat; check gateway logs for diagnostics."
    )
    assert mod.filter_final_reply(
        english, raw_surface=False, provider_failure=True
    ) == (
        "Ойижон, ҳозир жавоб бера олмадим. "
        "Илтимос, бироздан кейин яна ёзинг."
    )


def test_provider_failure_final_reply_stays_raw_on_programmatic_surface():
    mod = _load_outbound_filter()
    english = "Provider authentication failed: invalid API key"
    assert mod.filter_final_reply(
        english, raw_surface=True, provider_failure=True
    ) == english


def test_uzbek_final_reply_is_unchanged():
    mod = _load_outbound_filter()
    uzbek = "Ойижон, бу ойда жами 739 700 сўм сарфлабсиз."
    assert mod.filter_final_reply(uzbek, raw_surface=False) == uzbek


@pytest.mark.parametrize(
    "reply",
    (
        "Мен GPT-5.6-luna моделида ишлайман, Ойижон.",
        "Ойижон, OpenAI — сунъий интеллект яратадиган ташкилот.",
        "Ойижон, Wi-Fi ни ўчириб ёқинг.",
    ),
)
def test_ordinary_final_reply_with_latin_text_is_unchanged(reply):
    mod = _load_outbound_filter()
    assert mod.filter_final_reply(reply, raw_surface=False) == reply


def test_uzbek_status_still_delivered(protect_cfg):
    """Positive control: the filter is script-based, not blanket suppression."""
    mod = _load_outbound_filter()
    assert mod.should_suppress(UZBEK_STATUS, raw_surface=False) is False


def test_raw_surfaces_keep_english_diagnostics():
    mod = _load_outbound_filter()
    for surface in RAW_TEXT_PLATFORMS:
        assert surface in RAW_TEXT_PLATFORMS  # documents the Hermes allowlist
    assert mod.should_suppress(FALLBACK_NOTICE, raw_surface=True) is False
    assert mod.should_suppress(HERMES_FILTERED_STATUS, raw_surface=True) is False


def test_status_already_dropped_by_hermes_stays_dropped():
    mod = _load_outbound_filter()
    assert mod.should_suppress(None, raw_surface=False) is True
    assert mod.should_suppress(None, raw_surface=True) is True


def test_fallback_markers_documented_in_plugin():
    mod = _load_outbound_filter()
    corpus = "\n".join(mod.KNOWN_ENGLISH_STATUS_MARKERS)
    assert "Switched to fallback model" in corpus
    assert "Primary model failed" in corpus


def test_install_is_noop_without_gateway_module():
    """Plugin must not import the gateway (CLI/cron processes stay cheap)."""
    mod = _load_outbound_filter()
    assert mod.install_status_filter() is False


def test_installed_hermes_gateway_exposes_status_hook(tmp_path):
    """Catch a Hermes upgrade that silently disables the profile filter."""
    hermes_root = _installed_hermes_root()
    if hermes_root is None:
        pytest.skip("Hermes runtime is not installed locally")

    site_packages = hermes_root / "venv" / "Lib" / "site-packages"
    if not site_packages.is_dir():
        site_packages = (
            hermes_root
            / "venv"
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        str(path)
        for path in (hermes_root, site_packages)
        if path.is_dir()
    )
    env["HERMES_HOME"] = str(tmp_path / "hermes-home")
    probe = (
        "import importlib; "
        "module = importlib.import_module('gateway.run'); "
        "print(hasattr(module, '_prepare_gateway_status_message') and "
        "hasattr(module, '_sanitize_gateway_final_response') and "
        "hasattr(module, '_gateway_provider_error_reply'))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, (
        "Installed Hermes could not import gateway.run: "
        f"{completed.stderr.strip()}"
    )
    assert completed.stdout.strip().splitlines()[-1:] == ["True"], (
        "Installed Hermes gateway.run no longer exposes "
        "the status/final response hooks; update mariyam_outbound_filter "
        "to use the new status hook"
    )


def test_register_defers_install_when_gateway_not_imported():
    """Plugin discovery runs before gateway.run is imported (cli.py:965)."""
    mod = _load_outbound_filter()

    class _Ctx:
        def __init__(self):
            self.hooks = []

        def register_hook(self, name, callback):
            self.hooks.append((name, callback))

    ctx = _Ctx()
    mod.register(ctx)
    assert [name for name, _ in ctx.hooks] == ["pre_llm_call"]
    # The deferred hook installs the wrapper on the first agent turn and
    # injects nothing into the user message.
    assert mod.on_pre_llm_call(session_id="s", model="m") is None


def test_filter_wraps_status_rail_and_drops_fallback_notice():
    """End-to-end over both outbound rails in a stand-in gateway.run."""
    import types

    mod = _load_outbound_filter()
    fake = types.ModuleType("gateway.run")

    def _prepare_gateway_status_message(platform, event_type, message):
        return str(message).strip() or None

    def _gateway_surface_passes_raw_text(platform):
        return platform in RAW_TEXT_PLATFORMS

    def _sanitize_gateway_final_response(platform, text):
        body = str(text).strip()
        if platform in RAW_TEXT_PLATFORMS:
            return body
        if body.startswith("API call failed") or body.startswith("HTTP 599"):
            return fake._gateway_provider_error_reply(body)
        return body

    def _gateway_provider_error_reply(text):
        return f"The model provider failed after retries: {text}"

    fake._prepare_gateway_status_message = _prepare_gateway_status_message
    fake._gateway_surface_passes_raw_text = _gateway_surface_passes_raw_text
    fake._sanitize_gateway_final_response = _sanitize_gateway_final_response
    fake._gateway_provider_error_reply = _gateway_provider_error_reply

    sys.modules["gateway.run"] = fake
    try:
        assert mod.install_status_filter() is True
        wrapped = fake._prepare_gateway_status_message
        assert wrapped("telegram", "lifecycle", FALLBACK_NOTICE) is None
        assert wrapped("telegram", "lifecycle", UZBEK_STATUS) == UZBEK_STATUS
        # Programmatic surface keeps the diagnostic.
        assert wrapped("local", "lifecycle", FALLBACK_NOTICE) == FALLBACK_NOTICE
        # Positive control: without the wrapper Hermes would deliver it.
        assert _prepare_gateway_status_message(
            "telegram", "lifecycle", FALLBACK_NOTICE
        ) == FALLBACK_NOTICE

        wrapped_final = fake._sanitize_gateway_final_response
        english_failure = "API call failed: invalid API key"
        assert wrapped_final("telegram", english_failure) == mod.WARM_PROVIDER_REPLY
        # A future fifth category is caught by provenance, not an output list.
        assert wrapped_final("telegram", "HTTP 599 new provider category") == (
            mod.WARM_PROVIDER_REPLY
        )
        assert wrapped_final("telegram", UZBEK_STATUS) == UZBEK_STATUS
        assert wrapped_final("local", english_failure) == english_failure
        for normal_reply in (
            "Мен GPT-5.6-luna моделида ишлайман, Ойижон.",
            "Ойижон, OpenAI — сунъий интеллект яратадиган ташкилот.",
            "Ойижон, Wi-Fi ни ўчириб ёқинг.",
        ):
            assert wrapped_final("telegram", normal_reply) == normal_reply
        # Positive control: without the wrapper Hermes would deliver English.
        assert _sanitize_gateway_final_response(
            "telegram", english_failure
        ) == _gateway_provider_error_reply(english_failure)
    finally:
        sys.modules.pop("gateway.run", None)


# --- memory freshness: session rollover (imp05-opus) ---


def test_snippet_sets_daily_session_reset(protect_cfg):
    policy = protect_cfg["session_reset"]
    assert policy["mode"] == "daily"
    assert int(policy["at_hour"]) == 2


def test_session_reset_notice_is_silent(protect_cfg):
    """Hermes' auto-reset notice is English; Oyijon must never see it."""
    assert protect_cfg["session_reset"]["notify"] is False


def test_reset_hour_avoids_every_cron_slot(protect_cfg):
    at_hour = int(protect_cfg["session_reset"]["at_hour"])
    # Stage 6/7 cron slots (local time): morning 08, obligations 09,
    # evening 19:30, admin report 19:30, plan cycle 25/27/28 at 09.
    assert at_hour not in {8, 9, 19, 20}
    assert 0 <= at_hour <= 5


def test_hermes_default_policy_never_refreshes_memory():
    """Documents the pre-fix default: mode 'none' → frozen memory forever."""
    assert _should_reset("none", 4, updated_hour=2, now_hour=23) is False


def test_daily_policy_rolls_session_after_reset_hour(protect_cfg):
    policy = protect_cfg["session_reset"]
    mode, at_hour = policy["mode"], int(policy["at_hour"])
    # Live case: memory written 01:17, session last active 01:27, next
    # message after 02:00 → session rolls over and rebuilds the prompt.
    assert _should_reset(mode, at_hour, updated_hour=1, now_hour=2) is True
    # Same-day traffic after the rollover does not reset again.
    assert _should_reset(mode, at_hour, updated_hour=5, now_hour=6) is False


def test_identity_guard_version_file_unchanged_by_skill_protect():
    py = GUARD_INIT.read_text(encoding="utf-8")
    yaml_path = GUARD_INIT.parent / "plugin.yaml"
    y = yaml_path.read_text(encoding="utf-8")
    assert "1.0.3" in y or "version" in y
    # Skill protect must not rewrite guard package.
    assert "creation_nudge_interval" not in py
