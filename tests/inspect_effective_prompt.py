"""Offline Hermes effective-prompt inspection; emits metadata, never prompt text."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from agent.system_prompt import build_system_prompt_parts
from hermes_cli.config import load_config
from hermes_cli.prompt_size import _build_inspection_agent
from toolsets import resolve_toolset


FINAL_PHRASE = (
    "Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб "
    "чиқамиз. Маълумотлар тайёр."
)
DECISION_TABLE_MARKER = "GENERAL_FAMILY_REPORT"
AUTO_DETAIL_BAN = "Товарные строки автоматически не показывай"
CATEGORY_SUMMARY_HEADER = "Харажат гуруҳи | Режа | Сарфлангани | Қолгани"
PRODUCT_TABLE_HEADER = "Маҳсулот | Миқдор | Сарфлангани"
CATEGORY_TABLE_ONLY = "summary категории выводи только отдельной Markdown-таблицей"
BULLET_SUMMARY_BAN = "Маркированный список вместо summary-таблицы запрещён"
SUMMARY_BEFORE_PRODUCTS = (
    "Сразу после summary-таблицы выведи таблицу фактических товаров"
)
COMPLETION_NOT_TOTAL_DRIVEN = "Наличие `Жами` никогда не определяет"
CATEGORY_COMPLETION = "После таблиц завершить ответ"
CATEGORY_NO_GENERAL_PHRASE = "Финальную фразу общего отчёта не писать"
STAGE53_HEADING = "Stage 5.3 — продуктовый месячный план"
STAGE53_PRODUCT_HEADER = (
    "Маҳсулот | Режа: миқдор / сумма | Амалда: миқдор / сумма"
)
ONE_QUESTION = "бир хабарда фақат битта савол"
DRAFT_CONFIRMATION = "не вызывай `set_monthly_budget`"
NUTRITION_LIMIT = "максимум один web search на plan cycle"
OLD_FIVE_COLUMN = (
    "Маҳсулот | Режа миқдор | Режа сўм | "
    "Сарфланган миқдор | Сарфланган сўм | Қолди сўм"
)


def main() -> None:
    profile = Path(os.environ["HERMES_HOME"])
    soul = (profile / "SOUL.md").read_text(encoding="utf-8").strip()
    agent = _build_inspection_agent("telegram")
    config = load_config()
    disabled_toolsets = (config.get("agent") or {}).get("disabled_toolsets") or []
    removed_tool_names = sorted(
        {
            tool_name
            for toolset_name in disabled_toolsets
            for tool_name in resolve_toolset(toolset_name)
        }
    )
    available_tool_names = sorted(
        tool["function"]["name"] for tool in (getattr(agent, "tools", None) or [])
    )
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
        "disabled_toolsets": sorted(disabled_toolsets),
        "removed_tool_names": removed_tool_names,
        "available_tool_names": available_tool_names,
        "markers": {
            "identity_sentinel": full.count("user_id: 0"),
            "language_contract": full.count("только узбекский, кириллица"),
            "medical_contract": full.count("## 9. Медицинская безопасность"),
            "decision_table": full.count(DECISION_TABLE_MARKER),
            "monthly_budget_tool": full.count("get_monthly_budget_status"),
            "final_phrase": full.count(FINAL_PHRASE),
            "pcs_to_ta": full.count("pcs → та"),
            "auto_detail_ban": full.count(AUTO_DETAIL_BAN),
            "stage52_product_plan_ban": full.count("Product plan не показывай"),
            "category_summary_header": full.count(CATEGORY_SUMMARY_HEADER),
            "product_table_header": full.count(PRODUCT_TABLE_HEADER),
            "category_table_only": full.count(CATEGORY_TABLE_ONLY),
            "bullet_summary_ban": full.count(BULLET_SUMMARY_BAN),
            "summary_before_products": full.count(SUMMARY_BEFORE_PRODUCTS),
            "completion_not_total_driven": full.count(COMPLETION_NOT_TOTAL_DRIVEN),
            "category_completion": full.count(CATEGORY_COMPLETION),
            "category_no_general_phrase": full.count(CATEGORY_NO_GENERAL_PHRASE),
            "stage53_heading": full.count(STAGE53_HEADING),
            "stage53_product_header": full.count(STAGE53_PRODUCT_HEADER),
            "stage53_one_question": full.count(ONE_QUESTION),
            "stage53_draft_confirmation": full.count(DRAFT_CONFIRMATION),
            "stage53_nutrition_limit": full.count(NUTRITION_LIMIT),
            "stage53_price_lookup": full.count("price_lookup_items"),
            "stage53_execute_code_ban": full.count("execute_code"),
        },
        "forbidden": {
            "dona": "дона" in full,
            "old_auto_items": "внутри питания — товары" in full,
            "old_category_item_example": "разбивку category/item" in full,
            "old_stage53_five_column": OLD_FIVE_COLUMN in full,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
