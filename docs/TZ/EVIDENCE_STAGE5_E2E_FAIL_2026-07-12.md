# EVIDENCE — Этап 5 E2E-тест ПРОВАЛЕН (root cause зафиксирован 2026-07-12)

**Статус:** **HISTORICAL FAIL** (не удалять). Позднейший финальный PASS: `EVIDENCE_STAGE_5_E2E_2026-07-12.md` (Stage 5 закрыт 2026-07-13).
**Действие агента на момент FAIL:** остановлено по команде пользователя («стоп. зафиксируй»).

## 1. Что проверялось (сообщение 1, аккаунт «Тест Ойижон»)

Фразы: `1. Бугун нон 12 минг, гўшт 180 минг олдим.`
Ответ бота: «Ёзиб қўйдим: нон — 12 000 сўм, гўшт — 180 000 сўм. Жами — 192 000 сўм.»
В Telegram до ответа всплыли служебные traces:
`mcp__mariyam_backend__ensure_user...`, `terminal/shell/date -Iseconds`, `mcp__mariyam_backend__save_expense...`

## 2. Состояние БД после сообщения 1 (VPS, read-only)

```
SELECT user_id, count(*), COALESCE(sum(amount),0)
FROM transactions GROUP BY user_id ORDER BY user_id;

user_id | count | sum
--------+-------+----------
1       | 4     | 384000.00   <- admin
20      | 0     | 0           <- test-user «Тест Ойижон»
```

Было до теста: admin (id=1) = 2 записи (те самые ошибочные из инцидента), test-user (id=20) = 0.
После сообщения 1: admin = 4 (+2 записи от test-user), test-user = 0.

**Две новые записи** (нон 12 000 + гўшт 180 000 = 192 000) ушли в **admin (id=1)** вместо test-user (id=20). Дефект инцидента воспроизвёлся в runtime.

## 3. ROOT CAUSE — identity guard НЕ вызывается в runtime

Исследован пакет `hermes_cli` на VPS (`/home/timeagent/.hermes/hermes-agent/hermes_cli`):

- Плагин `mariyam_identity_guard` загружается и `register(ctx)` вызывается loader-ом
  (`plugins.py:1747` «Import a plugin module and call its `register(ctx)` function»).
- `register()` → `ctx.register_middleware("tool_execution", on_tool_execution_middleware)`
  (`plugins.py:1175` `register_middleware`) корректно кладёт callback в
  `self._manager._middleware["tool_execution"]`.
- **НО `run_tool_execution_middleware` / `invoke_middleware` НЕ ВЫЗЫВАЮТСЯ ни из одного
  runtime-пути выполнения MCP-инструментов.** Глобальный grep по всему пакету
  `hermes_cli` нашёл вызовы `invoke_middleware(` / `run_tool_execution_middleware(` только
  внутри самих определений (`middleware.py`), НЕ в agent-loop / tool-dispatcher.
- Следовательно, механизм `tool_execution` middleware в сборке Hermes v0.18.2 физически
  не подключён к выполнению MCP backend-tools. Плагин «зарегистрирован, но мёртв».

**Почему аудит ранее дал `PASS_TO_VPS_PHASE_B`:**
Тесты `tests/test_mariyam_identity_guard.py` вызывают `run_tool_execution_middleware`
**напрямую** (харнесс имитирует Hermes). Они проходят (43 passed), НО реальный Hermes
эту функцию при tool-call не дёргает. Тест-харнесс не соответствует реальности —
ляпуница между «mock Hermes» и production-runtime.

## 4. Вторичный дефект — утечка tool-traces в Telegram

Причина: в `config.yaml` профиля `mariyam_oyijon` стоит `display: tool_progress: all`
→ служебные сообщения о вызовах tools видны пользователю.
Фикс (правка config, не кода): `display.tool_progress: minimal` (или `off`).

## 5. Ошибочные записи

2 новые записи под admin (id=1) от сообщения 1 — НЕ удалять (условие задачи:
«запрещено удаление ошибочных записей»). Они — симптом дефекта, не трогать.

## 6. Почему Гейтвей не остановлен агентом

`systemctl --user stop` / `hermes gateway restart` из-под агента блокируются
hardline-правилом Hermes («cannot restart or stop the gateway from inside the gateway
process»). **Остановка — руками, вне агента:**
```
ssh timeagent@46.224.239.76
systemctl --user stop hermes-gateway-mariyam_oyijon.service
```

## 7. Варианты починки (требуют согласования — меняют код плагина)

- **Вариант A (plugin-side, без изменения core/backend):** плагин регистрирует
  wrapper-инструменты через `ctx.register_tool(..., override=True)` + в `config.yaml`
  `plugins.entries.mariyam_identity_guard.allow_tool_override: true`. Wrapper резолвит
  identity из session и инжектит корректный `user_id` до вызова backend-tools. Backend
  и Hermes core не меняются. ЭТО единственный viable-путь в рамках запретов.
- **Вариант B (forbidden):** включить middleware-chain в tool-dispatcher Hermes core —
  меняет core, запрещено.
- **Вариант C (forbidden):** перенести identity-enforcement в backend (`server.py`) —
  меняет backend, запрещено.

## 8. Итог по проверкам задачи

1. БД test-user: ожидалось 2 записи / 192 000 → **ФАКТ: 0 записей** (FAIL).
2. Admin: ожидалось +0 → **ФАКТ: +2 ошибочные** (FAIL).
3. Identity guard / tool-call корректно: **FAIL** (middleware не вызывается в runtime).
4. Утечка tool-traces в Telegram: **подтверждено** (config `tool_progress: all`).
5. Лимит 6 вызовов: не превышен (1 сообщение = 1 LLM-вызов; usage_costs пуста до теста).
6. `/opt/time-agent`: не тронут. Paid calls: 1 (gpt-5.6-luna, в рамках лимита 6).

**Вывод:** Этап 5 НЕ закрыт. Требуется починка плагина (Вариант A) + правка config
(`tool_progress`) + повторный E2E. Текущий identity guard в runtime не работает.
