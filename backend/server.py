"""Hermes/Mariyam backend — MCP server exposing storage tools (раздел 15).
Транспорт: stdio по умолчанию. Backend only validates/stores/returns facts — no intent logic.
Источник истины: TZ_Hermes_Mariyam_FINAL_v3_0.md.
"""
import json
import os
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from . import db
from .config import get_pool

app = Server("hermes-mariyam-backend")


def ok(**data):
    return {"ok": True, **data}


def err(code, ru, uz):
    return {"ok": False, "error_code": code, "message_ru": ru, "message_uz": uz}


@app.list_tools()
async def list_tools():
    return [types.Tool(name=n, description=d, inputSchema=s) for n, d, s in TOOLS]


@app.call_tool()
async def call_tool(name: str, arguments: dict | None):
    arguments = arguments or {}
    try:
        required = REQUIRED_BY_TOOL[name]
    except KeyError:
        result = err("UNKNOWN_TOOL", f"Неизвестный tool: {name}", "Номаълум восита")
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    missing = [field for field in required if field not in arguments]
    if missing:
        result = err(
            "INVALID_INPUT",
            "Отсутствуют обязательные поля: " + ", ".join(missing),
            "Мажбурий майдонлар етишмайди",
        )
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    if (
        name == "set_monthly_budget"
        and "items" in arguments
        and (
            not isinstance(arguments["items"], list)
            or not arguments["items"]
        )
    ):
        result = err(
            "INVALID_INPUT",
            "items должен отсутствовать или быть непустым массивом",
            "items майдони бўлмаслиги ёки бўш бўлмаган рўйхат бўлиши керак",
        )
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    pool = await get_pool()
    try:
        result = await DISPATCH[name](pool, arguments)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("BAD_CATEGORY"):
            result = err("BAD_CATEGORY", "Неизвестная категория", "Номаълум категория")
        elif msg.startswith("BAD_AMOUNT"):
            result = err("BAD_AMOUNT", "Сумма должна быть >= 0", "Сумма 0 дан катта бўлиши керак")
        else:
            result = err("INVALID_INPUT", f"Некорректные данные: {msg}", "Нотўғри маълумот")
    except Exception as e:  # pragma: no cover
        result = err("INTERNAL", f"Внутренняя ошибка: {e}", "Ички хато")
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------
async def t_ensure_user(pool, a):
    user_id, created = await db.ensure_user(pool, a["telegram_id"], a["role"], a["display_name"])
    return ok(user_id=user_id, created=created)


async def t_save_expense(pool, a):
    r = await db.save_expense(
        pool, a["user_id"], a["items"],
        a.get("occurred_at"), a.get("source_type", "text"),
        a.get("source_text"),
    )
    return ok(saved_ids=r["saved_ids"], total_uzs=r["total_uzs"])


async def t_save_income(pool, a):
    r = await db.save_income(
        pool, a["user_id"], a["amount"], a.get("currency", "UZS"),
        a.get("source_name"), a.get("occurred_at"), a.get("source_type", "text"),
    )
    return ok(**r)


async def t_update_expense(pool, a):
    r = await db.update_expense(pool, a["user_id"], a["expense_id"], a["fields"])
    if not r:
        return err("NOT_FOUND", "Запись не найдена", "Ёзув топилмади")
    return ok(**r)


async def t_update_last_expense(pool, a):
    r = await db.update_expense(pool, a["user_id"], None, a["fields"])
    if not r:
        return err("NOT_FOUND", "Запись не найдена", "Ёзув топилмади")
    return ok(**r)


async def t_delete_expense(pool, a):
    r = await db.delete_expense(pool, a["user_id"], a["expense_id"])
    if not r:
        return err("NOT_FOUND", "Запись не найдена", "Ёзув топилмади")
    return ok(**r)


async def t_delete_last_expense(pool, a):
    r = await db.delete_expense(pool, a["user_id"], None)
    if not r:
        return err("NOT_FOUND", "Запись не найдена", "Ёзув топилмади")
    return ok(**r)


async def t_get_expense_report(pool, a):
    r = await db.expense_report(
        pool, a["user_id"], a.get("period", "month"),
        a.get("from"), a.get("to"), a.get("category_code"),
        compare_previous=a.get("compare_previous", False),
        trend_months=a.get("trend_months", 3),
    )
    return ok(**r)


async def t_get_balance_summary(pool, a):
    r = await db.balance_summary(pool, a["user_id"], a.get("period", "month"))
    return ok(**r)


async def t_set_monthly_budget(pool, a):
    positional = (
        pool,
        a["user_id"],
        a["month"],
        a["category_code"],
        a["planned_amount_uzs"],
        a.get("note"),
    )
    if "items" in a:
        r = await db.set_monthly_budget(*positional, items=a["items"])
    else:
        r = await db.set_monthly_budget(*positional)
    return ok(**r)


async def t_get_monthly_budget_status(pool, a):
    r = await db.get_monthly_budget_status(
        pool,
        a["user_id"],
        a["month"],
        a.get("include_items", False),
        a.get("price_lookup_items"),
    )
    return ok(**r)


# Stage 5.3A — deterministic domain refusals from approve_monthly_plan.
CYCLE_ERRORS = {
    "MONTH_ALREADY_STARTED": ("Плановый месяц уже начался", "Режалаштирилган ой аллақачон бошланган"),
    "MONTH_NOT_STARTED": ("Плановый месяц ещё не начался", "Режалаштирилган ой ҳали бошланмаган"),
    "NO_DRAFT": ("Черновик плана не найден", "План лойиҳаси топилмади"),
    "EMPTY_DRAFT": ("План пустой, подтверждать нечего", "План бўш, тасдиқлаш учун маълумот йўқ"),
    "NO_PLAN_SOURCE": ("Нет ни черновика, ни прошлого плана", "На лойиҳа, на олдинги план мавжуд"),
    "INVALID_STATUS_TRANSITION": ("Недопустимый переход статуса плана", "Режа ҳолатининг нотўғри ўзгариши"),
    "SELF_ONLY_VIOLATION": ("Ойижон может подтверждать только свой план", "Ойижон фақат ўз режасини тасдиқлай олади"),
    "ADMIN_TARGET_REQUIRED": ("Админ должен указать целевого пользователя", "Админ мақсадли фойдаланувчини кўрсатиши керак"),
    "INVALID_APPROVER": ("Авто-утверждение не принимает approved_by_user_id", "Авто-тасдиқ approved_by_user_id ни қабул қилмайди"),
}


async def t_approve_monthly_plan(pool, a):
    r = await db.approve_monthly_plan(
        pool, a["user_id"], a["month"], a["source"],
        a.get("approved_by_user_id"), a.get("household_size"),
    )
    code = r.get("_cycle_error")
    if code:
        ru, uz = CYCLE_ERRORS[code]
        return err(code, ru, uz)
    return ok(**r)


async def t_save_quran_progress(pool, a):
    rid = await db.save_quran_progress(
        pool, a["user_id"], a.get("surah"), a.get("juz"), a.get("page"), a.get("note"))
    return ok(id=rid)


async def t_get_quran_progress(pool, a):
    row = await db.get_quran_progress(pool, a["user_id"])
    if not row:
        return err("NOT_FOUND", "Прогресс не найден", "Ривож топилмади")
    return ok(
        surah=row["surah"], juz=row["juz"], page=row["page"],
        note=row["note"], updated_at=row["updated_at"].isoformat().replace("+00:00", "Z"),
    )


async def t_save_health_note(pool, a):
    rid = await db.save_health_note(
        pool, a["user_id"], a["note"], a.get("severity", "info"), a.get("source_text"))
    return ok(id=rid)


async def t_save_alert_event(pool, a):
    rid = await db.save_alert_event(
        pool, a["user_id"], a["alert_type"], a["severity"],
        a["source_text"], a.get("bot_response"), a.get("detected_by"),
        a.get("sent_to_admin", False),
    )
    return ok(id=rid)


async def t_save_plan_note(pool, a):
    rid = await db.save_plan_note(
        pool, a["user_id"], a.get("kind"), a["text"], a.get("value_int"))
    return ok(id=rid)


async def t_get_admin_report_data(pool, a):
    r = await db.admin_report_data(pool, a["user_id"], a.get("date"))
    return ok(**r)


async def t_backup_data(pool, a):
    return err(
        "NOT_CONFIGURED",
        "Backup ещё не настроен (Этап 8)",
        "Заҳира нусхаси ҳали созланмаган",
    )


async def t_get_backup_status(pool, a):
    return err(
        "NOT_CONFIGURED",
        "Backup ещё не настроен (Этап 8)",
        "Заҳира нусхаси ҳали созланмаган",
    )


async def t_get_bot_status(pool, a):
    r = await db.get_bot_status(pool)
    return ok(**r)


async def t_log_usage_cost(pool, a):
    await db.log_usage_cost(
        pool, a["provider"], a["service_type"], a["units"], a["estimated_cost_usd"])
    return ok()


DISPATCH = {
    "ensure_user": t_ensure_user,
    "save_expense": t_save_expense,
    "save_income": t_save_income,
    "update_expense": t_update_expense,
    "update_last_expense": t_update_last_expense,
    "delete_expense": t_delete_expense,
    "delete_last_expense": t_delete_last_expense,
    "get_expense_report": t_get_expense_report,
    "get_balance_summary": t_get_balance_summary,
    "set_monthly_budget": t_set_monthly_budget,
    "get_monthly_budget_status": t_get_monthly_budget_status,
    "approve_monthly_plan": t_approve_monthly_plan,
    "save_quran_progress": t_save_quran_progress,
    "get_quran_progress": t_get_quran_progress,
    "save_health_note": t_save_health_note,
    "save_alert_event": t_save_alert_event,
    "save_plan_note": t_save_plan_note,
    "get_admin_report_data": t_get_admin_report_data,
    "backup_data": t_backup_data,
    "get_backup_status": t_get_backup_status,
    "get_bot_status": t_get_bot_status,
    "log_usage_cost": t_log_usage_cost,
}


def schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


P = {
    "user_id": {"type": "integer"},
    "telegram_id": {"type": "integer"},
    "role": {"type": "string", "enum": list(db.ROLES)},
    "display_name": {"type": "string"},
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "item_name": {"type": "string"},
        "item_name_normalized": {"type": "string"},
        "amount_uzs": {"type": "number"},
        "category_code": {"type": "string"},
        "quantity": {"type": "number"},
        "unit": {"type": "string", "enum": list(db.CANONICAL_UNITS)},
    }, "required": ["amount_uzs"]}},
    "occurred_at": {"type": "string", "description": "UTC ISO 8601 или дата (день по Ташкенту)"},
    "source_type": {"type": "string", "enum": list(db.SOURCE_TYPES)},
    "source_text": {"type": "string"},
    "amount": {"type": "number"},
    "currency": {"type": "string", "enum": list(db.CURRENCIES)},
    "source_name": {"type": "string"},
    "expense_id": {"type": "integer"},
    "fields": {"type": "object"},
    "period": {"type": "string", "enum": ["today", "week", "month", "custom"]},
    "from": {"type": "string"},
    "to": {"type": "string"},
    "category_code": {"type": "string"},
    "compare_previous": {"type": "boolean"},
    "trend_months": {"type": "integer", "minimum": 1, "maximum": 12},
    "month": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-01$"},
    "planned_amount_uzs": {"type": "number", "minimum": 0},
    "budget_items": {"type": "array", "minItems": 1, "items": {
        "type": "object",
        "properties": {
            "item_name_normalized": {"type": "string", "minLength": 1},
            "item_name_display": {"type": "string", "minLength": 1},
            "planned_quantity": {"type": "number", "exclusiveMinimum": 0},
            "unit": {"type": "string", "enum": list(db.CANONICAL_UNITS)},
            "planned_amount_uzs": {"type": "number", "minimum": 0},
            "reference_unit_price_uzs": {"type": "number", "minimum": 0},
            "price_basis": {"type": "string", "enum": list(db.PRICE_BASES)},
            "price_as_of": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["item_name_normalized", "item_name_display"],
        "anyOf": [
            {"required": ["planned_quantity"]},
            {"required": ["planned_amount_uzs"]},
        ],
        "additionalProperties": False,
    }},
    "include_items": {"type": "boolean", "default": False},
    "price_lookup_items": {
        "type": "array",
        "maxItems": 50,
        "items": {
            "type": "object",
            "properties": {
                "item_name_normalized": {"type": "string", "minLength": 1},
                "unit": {"type": "string", "enum": list(db.CANONICAL_UNITS)},
                "price_basis": {"type": "string", "enum": ["last", "average"]},
            },
            "required": ["item_name_normalized", "unit", "price_basis"],
            "additionalProperties": False,
        },
    },
    "source": {"type": "string", "enum": list(db.APPROVAL_SOURCES)},
    "approved_by_user_id": {"type": "integer"},
    "household_size": {"type": "integer", "minimum": 1},
    "surah": {"type": "string"},
    "juz": {"type": "integer"},
    "page": {"type": "integer"},
    "note": {"type": "string"},
    "severity": {"type": "string", "enum": list(db.HEALTH_SEVERITIES)},
    "alert_severity": {"type": "string", "enum": list(db.ALERT_SEVERITIES)},
    "alert_type": {"type": "string"},
    "bot_response": {"type": "string"},
    "detected_by": {"type": "string", "enum": list(db.DETECTED_BY)},
    "sent_to_admin": {"type": "boolean"},
    "kind": {"type": "string"},
    "text": {"type": "string"},
    "value_int": {"type": "integer"},
    "date": {"type": "string"},
    "provider": {"type": "string"},
    "service_type": {"type": "string", "enum": list(db.SERVICE_TYPES)},
    "units": {"type": "number"},
    "estimated_cost_usd": {"type": "number"},
}


def pick(*names: str) -> dict:
    return {name: P[name] for name in names}


TOOLS = [
    ("ensure_user", "Создать/найти пользователя по telegram_id", schema(pick("telegram_id", "role", "display_name"), ["telegram_id", "role", "display_name"])),
    ("save_expense", "Сохранить расход(ы). items:[{item_name,amount_uzs,category_code,quantity?,unit?}]", schema(pick("user_id", "items", "occurred_at", "source_type", "source_text"), ["user_id", "items"])),
    ("save_income", "Сохранить доход (пенсия и т.п.)", schema(pick("user_id", "amount", "currency", "source_name", "occurred_at", "source_type"), ["user_id", "amount"])),
    ("update_expense", "Исправить расход по id", schema(pick("user_id", "expense_id", "fields"), ["user_id", "expense_id", "fields"])),
    ("update_last_expense", "Исправить последнюю расходную запись", schema(pick("user_id", "fields"), ["user_id", "fields"])),
    ("delete_expense", "Удалить расход по id", schema(pick("user_id", "expense_id"), ["user_id", "expense_id"])),
    ("delete_last_expense", "Удалить последний расход", schema(pick("user_id"), ["user_id"])),
    ("get_expense_report", "Отчёт по расходам (+ by_item / compare_previous / monthly_series)", schema(pick("user_id", "period", "from", "to", "category_code", "compare_previous", "trend_months"), ["user_id"])),
    ("get_balance_summary", "Доход/расход/остаток за период", schema(pick("user_id", "period"), ["user_id"])),
    ("set_monthly_budget", "Создать/обновить план категории и атомарно заменить optional product items. Category-only допустим только когда items omitted; explicit items=[] всегда INVALID_INPUT. Для подтверждённого товара используй exact fields item_name_normalized, item_name_display, planned_quantity, unit, planned_amount_uzs, reference_unit_price_uzs, price_basis, price_as_of", schema({**pick("user_id", "month", "category_code", "planned_amount_uzs", "note"), "items": P["budget_items"]}, ["user_id", "month", "category_code", "planned_amount_uzs"])),
    ("get_monthly_budget_status", "Точные plan/fact за месяц; include_items=true добавляет product plan, actual и reference prices; price_lookup_items требует price_basis=last|average и возвращает read-only selected reference-price facts", schema(pick("user_id", "month", "include_items", "price_lookup_items"), ["user_id", "month"])),
    ("approve_monthly_plan", "Утвердить месячный план (draft→approved). source=oyijon|admin|auto. Работает только до начала планового месяца (Asia/Tashkent); auto — только в 1-й день. Не читает и не меняет transactions. Идемпотентен по user/month; недопустимый переход статуса отклоняется без мутации. source=auto копирует последний approved plan, если нет draft", schema(pick("user_id", "month", "source", "approved_by_user_id", "household_size"), ["user_id", "month", "source"])),
    ("save_quran_progress", "Сохранить прогресс Корана", schema(pick("user_id", "surah", "juz", "page", "note"), ["user_id"])),
    ("get_quran_progress", "Последний прогресс Корана", schema(pick("user_id"), ["user_id"])),
    ("save_health_note", "Заметка о самочувствии (без диагноза)", schema(pick("user_id", "note", "severity", "source_text"), ["user_id", "note"])),
    ("save_alert_event", "Событие срочного уведомления", schema({**pick("user_id", "alert_type"), "severity": P["alert_severity"], **pick("source_text", "bot_response", "detected_by", "sent_to_admin")}, ["user_id", "alert_type", "severity", "source_text"])),
    ("save_plan_note", "План/заметка/счётчик как факт", schema(pick("user_id", "kind", "text", "value_int"), ["user_id", "text"])),
    ("get_admin_report_data", "Факты для отчёта 19:30 (прозу пишет Hermes)", schema(pick("user_id", "date"), ["user_id"])),
    ("backup_data", "Backup: до Этапа 8 возвращает NOT_CONFIGURED", schema({})),
    ("get_backup_status", "Статус backup: до Этапа 8 возвращает NOT_CONFIGURED", schema({})),
    ("get_bot_status", "Heartbeat: gateway/db/time", schema({})),
    ("log_usage_cost", "Записать оценку стоимости STT/TTS/LLM", schema(pick("provider", "service_type", "units", "estimated_cost_usd"), ["provider", "service_type", "units", "estimated_cost_usd"])),
]
REQUIRED_BY_TOOL = {name: tool_schema.get("required", []) for name, _desc, tool_schema in TOOLS}


async def main():
    transport_mode = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport_mode == "http":
        import uvicorn
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.routing import Mount

        host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
        session_manager = StreamableHTTPSessionManager(app=app, json_response=True)

        class MCPASGIApp:
            def __init__(self, manager):
                self.manager = manager

            async def __call__(self, scope, receive, send):
                await self.manager.handle_request(scope, receive, send)

        @asynccontextmanager
        async def lifespan(_app):
            async with session_manager.run():
                yield

        app_http = Starlette(routes=[Mount("/mcp", app=MCPASGIApp(session_manager))], lifespan=lifespan)
        cfg = uvicorn.Config(app_http, host=host, port=port)
        server = uvicorn.Server(cfg)
        await server.serve()
    else:
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
