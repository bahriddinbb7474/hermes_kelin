"""Permanent offline contract for the assembled Mariyam Telegram prompt."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import yaml


REPO = Path(__file__).resolve().parents[1]
PROFILE_SOURCE = REPO / "deploy" / "hermes_profile_mariyam_oyijon"
SOUL = PROFILE_SOURCE / "SOUL.md"
LEGACY_SKILL = REPO / "skills" / "mariyam" / "SKILL.md"
CONFIG_SNIPPET = PROFILE_SOURCE / "config.skill-protect.snippet.yaml"
INSPECTOR = Path(__file__).with_name("inspect_effective_prompt.py")
DEPLOY_DOC = REPO / "deploy" / "DEPLOY.md"


def _hermes_python() -> Path:
    configured = os.environ.get("MARIYAM_HERMES_PYTHON")
    if configured:
        return Path(configured)

    roots = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        roots.append(Path(local_appdata) / "hermes" / "hermes-agent")
    roots.append(Path.home() / ".hermes" / "hermes-agent")

    for root in roots:
        for relative in (
            Path("venv") / "Scripts" / "python.exe",
            Path("venv") / "Scripts" / "python",
            Path("venv") / "bin" / "python",
        ):
            candidate = root / relative
            if candidate.is_file():
                return candidate
    raise AssertionError(
        "Hermes Python not found; set MARIYAM_HERMES_PYTHON for offline prompt inspection"
    )


def _inspect_effective_prompt(tmp_path: Path) -> dict:
    profile = tmp_path / "mariyam_oyijon"
    profile.mkdir()
    shutil.copy2(SOUL, profile / "SOUL.md")
    shutil.copy2(CONFIG_SNIPPET, profile / "config.yaml")

    env = os.environ.copy()
    env.update(
        {
            "HERMES_HOME": str(profile),
            "HERMES_PROFILE": "mariyam_oyijon",
            "HERMES_PLATFORM": "telegram",
            "HERMES_EPHEMERAL_SYSTEM_PROMPT": "",
        }
    )
    completed = subprocess.run(
        [str(_hermes_python()), str(INSPECTOR)],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_profile_uses_one_canonical_prompt_source():
    assert SOUL.is_file(), f"missing canonical profile prompt: {SOUL}"
    assert not LEGACY_SKILL.exists(), "Mariyam contract must not be duplicated in SKILL.md"


def test_no_second_mariyam_soul_or_skill_exists():
    completed = subprocess.run(
        ["git", "ls-files", "--", "*SOUL.md", "*SKILL.md"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    prompt_files = sorted(
        path for path in completed.stdout.splitlines() if "mariyam" in path.lower()
    )
    assert prompt_files == ["deploy/hermes_profile_mariyam_oyijon/SOUL.md"]


def test_profile_config_uses_supported_prompt_path_not_noop_enabled_key():
    config = yaml.safe_load(CONFIG_SNIPPET.read_text(encoding="utf-8"))
    assert "enabled" not in config["skills"]
    assert config["agent"]["disabled_toolsets"] == ["skills"]


def test_effective_telegram_prompt_contains_full_untruncated_contract(tmp_path):
    result = _inspect_effective_prompt(tmp_path)
    assert result["full_soul_present"] is True
    assert result["soul_truncated"] is False
    assert result["skills_index_present"] is False

    markers = result["markers"]
    assert markers["identity_sentinel"] >= 1
    assert markers["language_contract"] == 1
    assert markers["medical_contract"] == 1
    assert markers["decision_table"] == 1
    assert markers["monthly_budget_tool"] >= 1
    assert markers["final_phrase"] == 1
    assert markers["pcs_to_ta"] == 1
    assert markers["auto_detail_ban"] == 1
    assert markers["stage53_ban"] == 1
    assert not any(result["forbidden"].values())


def test_deploy_requires_new_session_and_cached_prompt_verification():
    text = DEPLOY_DOC.read_text(encoding="utf-8")
    section = text.split("## Deterministic profile prompt", 1)[1]
    offline = section.index("Offline preflight deployed-профиля")
    reset = section.index("/new")
    first_turn = section.index("Первый controlled E2E turn")
    stored = section.index("Stored prompt check после первого turn")
    assert offline < reset < first_turn < stored
    assert "sessions.system_prompt" in section
    assert "effective prompt" in section.lower()
