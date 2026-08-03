"""fix04: пересчёт cron-отпечатков — часть процедуры, а не памяти человека.

Дважды подряд задача ломалась одинаково: кто-то менял определение cron-задачи
(промпт в fix02, `deliver` при перепривязке на реальную Ойижон), отпечатки в
приватной cron-карте не пересчитывались, и guard молча отказывал инструментам.
Сообщение при этом доставлялось — пустое. Тест держит правило: любой скрипт в
`deploy/`, который пишет SOUL или cron-задачи, обязан вызвать пересчёт.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DEPLOY = REPO / "deploy"
REFRESH_TOOL = DEPLOY / "imp04_refresh_cron_fingerprints.py"
REFRESH_NAME = "imp04_refresh_cron_fingerprints.py"

# Скрипт «трогает профиль», если он пишет SOUL.md или cron/jobs.json.
_WRITES_SOUL = re.compile(r"(cp|install|mv|tee|>)\s[^\n]*SOUL\.md")
_WRITES_JOBS = re.compile(r"cron\s+(edit|add|create|remove)|jobs\.json[^\n]*<|>\s*[^\n]*jobs\.json")


def _profile_writing_scripts() -> list[Path]:
    found = []
    for path in sorted(DEPLOY.rglob("*.sh")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "--rollback" in text and path.name.startswith("rollback"):
            continue
        if _WRITES_SOUL.search(text) or _WRITES_JOBS.search(text):
            found.append(path)
    return found


def test_the_refresh_tool_exists_and_has_a_gate_mode():
    text = REFRESH_TOOL.read_text(encoding="utf-8")
    assert "--check" in text
    assert "--apply" in text
    # --check обязан уметь падать: без ненулевого кода это не гейт.
    assert "return 1" in text


def test_every_profile_writing_script_refreshes_fingerprints():
    scripts = _profile_writing_scripts()
    # Если этот список опустел — значит регулярки перестали ловить скрипты,
    # и тест молча проходит ни на чём.
    assert scripts, "no profile-writing deploy scripts found — check the patterns"
    missing = [
        str(path.relative_to(REPO))
        for path in scripts
        if REFRESH_NAME not in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert not missing, (
        "these deploy scripts change the profile but never refresh the cron "
        f"identity fingerprints: {missing}"
    )


@pytest.mark.parametrize(
    "script", [p.name for p in _profile_writing_scripts()]
)
def test_soul_deploy_script_gates_on_check(script):
    """Одного --apply мало: гейт — это ненулевой код --check до рестарта."""
    path = next(p for p in _profile_writing_scripts() if p.name == script)
    text = path.read_text(encoding="utf-8", errors="replace")
    if "SOUL.md" not in text:
        pytest.skip("script does not deploy SOUL")
    assert "--apply" in text
    assert "--check" in text
    restart = text.find("systemctl --user restart")
    check = text.find("--check")
    if restart != -1:
        assert check < restart, "fingerprints must be verified before the restart"


def test_deploy_doc_states_the_rule():
    doc = (DEPLOY / "DEPLOY.md").read_text(encoding="utf-8")
    assert "Cron identity — обязательный шаг любого deploy" in doc
    assert "--check" in doc
    assert "deliver" in doc, "правило обязано называть смену delivery, не только промпт"
