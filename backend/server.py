"""Hermes/Mariyam backend — MCP server exposing storage tools (раздел 15).
Транспорт: stdio. Backend only validates/stores/returns facts — no intent logic.
Источник истины: TZ_Hermes_Mariyam_FINAL_v3_0.md.
"""
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
import os

from . import db
from .config import get_pool, DATABASE_URL

app = Server("hermes-mariyam-backend")


def ok(**data):
    return {"ok": True, **data}


def err(code, ru, uz):
    return {"ok": False, "error_code": code, "message_ru": ru, "message_uz": uz}


async def _pool():
    return await get_pool()


@app.list_tools()
async def list_tools():
    return [
        types.Tool(name=n, description=d, inputSchema=s)
        for n, d, s in TOOLS
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    pool = await _pool()
    try:
        result = await DISPATCH[name](pool, arguments)
    except KeyError:
        result = err("UNKNOWN_TOOL", f"Неизвестный tool: {name}", "Номаълум восита")
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
    r = await db.update_expense(pool, a["user_id"], a.get("expense_id"), a.get("fields", {}))
    if not r:
        return err("NOT_FOUND", "Запись не найдена", "Ёзув топилмади")
    return ok(**r)


async def t_update_last_expense(pool, a):
    r = await db.update_expense(pool, a["user_id"], None, a.get("fields", {}))
    if not r:
        return err("NOT_FOUND", "Запись не найдена", "Ёзув топилмади")
    return ok(**r)


async def t_delete_expense(pool, a):
    r = await db.delete_expense(pool, a["user_id"], a.get("expense_id"))
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
    )
    return ok(**r)


async def t_get_balance_summary(pool, a):
    r = await db.balance_summary(pool, a["user_id"], a.get("period", "month"))
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
    # Placeholder: real backup is documented in SECURITY_PRIVACY / раздел 18.
    # Reports status only; actual archive via rclone/gpg runs on VPS.
    return ok(archive="<configured-on-vps>", uploaded=False)


async def t_get_backup_status(pool, a):
    return ok(last_backup_at=None, last_ok=True)


async def t_get_bot_status(pool, a):
    r = await db.get_bot_status(pool)
    return ok(**r)


async def t_log_usage_cost(pool, a):
    await db.log_usage_cost(
        pool, a["provider"], a["service_type"], a["units"], a["estimated_cost_usd"])
    return ok()


DISPATCH = {
    "save_expense": t_save_expense,
    "save_income": t_save_income,
    "update_expense": t_update_expense,
    "update_last_expense": t_update_last_expense,
    "delete_expense": t_delete_expense,
    "delete_last_expense": t_delete_last_expense,
    "get_expense_report": t_get_expense_report,
    "get_balance_summary": t_get_balance_summary,
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


SCHEMA_OBJ = {
    "type": "object",
    "properties": {
        "user_id": {"type": "integer"},
        "items": {"type": "array", "items": {"type": "object"}},
        "occurred_at": {"type": "string"},
        "source_type": {"type": "string"},
        "source_text": {"type": "string"},
        "amount": {"type": "number"},
        "currency": {"type": "string"},
        "source_name": {"type": "string"},
        "expense_id": {"type": "integer"},
        "fields": {"type": "object"},
        "period": {"type": "string"},
        "from": {"type": "string"},
        "to": {"type": "string"},
        "category_code": {"type": "string"},
        "surah": {"type": "string"},
        "juz": {"type": "integer"},
        "page": {"type": "integer"},
        "note": {"type": "string"},
        "severity": {"type": "string"},
        "alert_type": {"type": "string"},
        "bot_response": {"type": "string"},
        "detected_by": {"type": "string"},
        "sent_to_admin": {"type": "boolean"},
        "kind": {"type": "string"},
        "text": {"type": "string"},
        "value_int": {"type": "integer"},
        "date": {"type": "string"},
        "provider": {"type": "string"},
        "service_type": {"type": "string"},
        "units": {"type": "number"},
        "estimated_cost_usd": {"type": "number"},
    },
}

TOOLS = [
    ("save_expense", "Сохранить расход(ы). items:[{item_name,amount_uzs,category_code}]", SCHEMA_OBJ),
    ("save_income", "Сохранить доход (пенсия и т.п.)", SCHEMA_OBJ),
    ("update_expense", "Исправить расход по id", SCHEMA_OBJ),
    ("update_last_expense", "Исправить последнюю расходную запись", SCHEMA_OBJ),
    ("delete_expense", "Удалить расход по id", SCHEMA_OBJ),
    ("delete_last_expense", "Удалить последний расход", SCHEMA_OBJ),
    ("get_expense_report", "Отчёт по расходам: today/week/month/custom", SCHEMA_OBJ),
    ("get_balance_summary", "Доход/расход/остаток за период", SCHEMA_OBJ),
    ("save_quran_progress", "Сохранить прогресс Корана", SCHEMA_OBJ),
    ("get_quran_progress", "Последний прогресс Корана", SCHEMA_OBJ),
    ("save_health_note", "Заметка о самочувствии (без диагноза)", SCHEMA_OBJ),
    ("save_alert_event", "Событие срочного уведомления", SCHEMA_OBJ),
    ("save_plan_note", "План/заметка/счётчик как факт", SCHEMA_OBJ),
    ("get_admin_report_data", "Факты для отчёта 19:30 (прозу пишет Hermes)", SCHEMA_OBJ),
    ("backup_data", "Запустить backup (на VPS через rclone/gpg)", SCHEMA_OBJ),
    ("get_backup_status", "Статус последнего backup", SCHEMA_OBJ),
    ("get_bot_status", "Heartbeat: gateway/db/time", SCHEMA_OBJ),
    ("log_usage_cost", "Записать оценку стоимости STT/TTS/LLM", SCHEMA_OBJ),
]


async def main():
    transport_mode = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport_mode == "http":
        from mcp.server.streamable_http import StreamableHTTPServerTransport
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.requests import Request

        host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
        init_options = app.create_initialization_options()

        from contextlib import asynccontextmanager
        import anyio

        http_transport = StreamableHTTPServerTransport(mcp_session_id=None)
        init_options = app.create_initialization_options()

        @asynccontextmanager
        async def lifespan(_app):
            async with http_transport.connect() as (read, write):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(app.run, read, write, init_options)
                    yield

        async def mcp_endpoint(request: Request):
            await http_transport.handle_request(
                request.scope, request.receive, request._send)

        app_http = Starlette(
            routes=[Route("/mcp", endpoint=mcp_endpoint,
                          methods=["GET", "POST", "DELETE"])],
            lifespan=lifespan,
        )
        cfg = uvicorn.Config(app_http, host=host, port=port)
        server = uvicorn.Server(cfg)
        await server.serve()
    else:
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
