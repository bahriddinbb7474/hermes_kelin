"""Offline Hermes effective-prompt inspection; emits metadata, never prompt text."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from agent.system_prompt import build_system_prompt_parts
from hermes_cli.prompt_size import _build_inspection_agent


FINAL_PHRASE = (
    "Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб "
    "чиқамиз. Маълумотлар тайёр."
)
DECISION_TABLE_MARKER = "GENERAL_FAMILY_REPORT"
AUTO_DETAIL_BAN = "Товарные строки автоматически не показывай"


def main() -> None:
    profile = Path(os.environ["HERMES_HOME"])
    soul = (profile / "SOUL.md").read_text(encoding="utf-8").strip()
    agent = _build_inspection_agent("telegram")
    parts = build_system_prompt_parts(agent)
    full = "\n\n".join(
        parts[name] for name in ("stable", "context", "volatile") if parts[name]
    )
    payload = {
        "soul_chars": len(soul),
        "soul_sha256": hashlib.sha256(soul.encode("utf-8")).hexdigest(),
        "parts_chars": {name: len(text) for name, text in parts.items()},
        "full_soul_present": soul in full,
        "soul_truncated": "[...truncated SOUL.md:" in full,
        "skills_index_present": "<available_skills>" in full,
        "markers": {
            "identity_sentinel": full.count("user_id: 0"),
            "language_contract": full.count("только узбекский, кириллица"),
            "medical_contract": full.count("## 9. Медицинская безопасность"),
            "decision_table": full.count(DECISION_TABLE_MARKER),
            "monthly_budget_tool": full.count("get_monthly_budget_status"),
            "final_phrase": full.count(FINAL_PHRASE),
            "pcs_to_ta": full.count("pcs → та"),
            "auto_detail_ban": full.count(AUTO_DETAIL_BAN),
            "stage53_ban": full.count("Product plan не показывай"),
        },
        "forbidden": {
            "dona": "дона" in full,
            "old_auto_items": "внутри питания — товары" in full,
            "old_category_item_example": "разбивку category/item" in full,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
