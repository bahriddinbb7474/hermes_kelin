# imp01 — Pre-code gate Stage 5.3A: исследование cron identity Hermes v0.18.2

## Контекст
Проект Hermes/Mariyam, VPS `/opt/time-agent`, Hermes v0.18.2, профиль
`mariyam_oyijon`. Runtime: 21 tools, identity plugin `mariyam_identity_guard`
1.0.4 (deploy/hermes_plugins/), guard `mariyam_stage53_guard` 1.0.0,
migration 003 активна (в ней уже есть таблица `monthly_plan_cycles`).

Stage 5.3A (ТЗ `docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md`, раздел «Этап 5.3A»,
~стр. 1484) — цикл утверждения месячного плана 25/27/28/1. Все cron-инициированные
user-scoped tool calls должны идти по цепочке:
`trusted cron job id → private mapping (file mode 0600) → internal users.id`.
`user_id`, сформированный LLM, не доверяется. Unknown/untrusted cron job →
fail closed, downstream tool calls = 0.

**Это исследовательская задача. Код Stage 5.3A НЕ писать.**
Архитектурные запреты: Hermes core и backend не менять; никаких
backend-router/orchestrator/отдельного scheduler; допустимо только узкое
расширение profile plugin.

## Что сделать
1. На VPS исследовать фактический cron-механизм Hermes v0.18.2:
   - как объявляются cron jobs (config/profile/API), где хранятся;
   - что происходит при срабатывании: новый agent turn? какая session,
     какой identity context, какие поля видит middleware/plugin chain;
   - отличим ли cron-инициированный turn от Telegram-инициированного
     на уровне plugin (наличие/отсутствие telegram user id, спец-поля, job id);
   - может ли cron turn вызывать MCP tools и проходит ли он через
     существующий `mariyam_identity_guard` (и что тот сделает сейчас:
     pass/fail? проверить фактическое поведение, не по докам).
2. Спроектировать минимальное расширение (нового или существующего profile
   plugin) для цепочки trusted job id → mapping 0600 → users.id, fail closed.
   Указать: где живёт mapping-файл, формат, кто его создаёт, поведение при
   unknown job / битом mapping / неверных правах файла.
3. Оценить риски: может ли LLM внутри cron turn «подделать» identity;
   что с `max_turns=6` и duplicate-breaker в cron-контексте.

## Отчёт (обязательно)
- `tasks/sol/imp01.report.md` + design-документ
  `docs/TZ/CRON_IDENTITY_GATE_5_3A.md`:
  факты о cron v0.18.2 (с доказательствами: пути конфигов, фрагменты кода
  Hermes, логи тестового прогона), схема identity-цепочки, план узкого
  расширения plugin, открытые вопросы/блокеры.
- Тестовые cron jobs после исследования удалить, production-профиль и БД
  не изменять; если что-то временно менялось — вернуть и указать в отчёте.
- Commit только новых .md (`git add` поимённо), message:
  `docs: Stage 5.3A cron identity gate research`, push в `main`.
- В чат заказчику: 2–3 предложения простым русским — можно ли безопасно
  делать 5.3A и что для этого нужно.
