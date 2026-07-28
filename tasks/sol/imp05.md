# imp05 (Sol) — Stage 6, шаг 1: migration 005 + tools регулярных обязательств

## Контекст
Repo `main`. Runtime: backend 24 tools deployed (24/24/24), identity guard
1.2.0 (Telegram + cron trusted mapping), Stage 8 backup active. Требования —
ТЗ «Этап 6» (~стр. 1520): регулярные обязательства (internet, loan, tax,
utility, other). Это backend-шаг; cron-напоминания и утро/вечер/новости —
следующая задача.

## Что сделать
1. Migration 005: `recurring_obligations` (user-scoped; тип, название, сумма,
   due date, repeat rule, active/paid state, timestamps). Существующие миграции
   не редактировать.
2. Контракт в TOOLS_CONTRACTS.md (до кода), затем tools:
   - `upsert_recurring_obligation` — создать/изменить сумму или дату, отметить
     paid, disable. Отметка paid НЕ создаёт expense/transaction автоматически.
     Следующая due date вычисляется backend'ом детерминированно и только по
     утверждённому repeat rule;
   - `get_recurring_obligations` — active/due обязательства пользователя.
   Identity: Ойижон self-only; admin cross-target только target из
   `allowed_target_user_ids` через отдельный narrow allowlist; прав на
   transactions не даёт. Error codes в стиле существующих, отказы без мутации.
3. Guard: оба tool добавить в `USER_SCOPED_TOOLS` В ЭТОЙ ЖЕ задаче
   (урок imp03-opus), версия guard → 1.3.0, Telegram/cron ветки не менять,
   regression suites без правок тестов.
4. Inventory/dispatch/discovery 24 → 26 синхронно; count-тесты обновить.
5. Тесты: repeat rule (месячный/произвольный из ТЗ), paid → stop + следующая
   дата, edge даты (29–31 число, конец года), self-only/чужой target, admin
   allowlist, идемпотентность upsert. Существующие suites зелёные.
6. Controlled deploy: backup, migration 005 на VPS, backend 26, guard 1.3.0,
   restart; проверка 26/26/26, health, Telegram smoke-регрессия с тест-аккаунта.
   Rollback описать. Evidence `docs/EVIDENCE_STAGE_6_OBLIGATIONS_<дата>.md`.
7. Доки минимально: DATABASE.md, README/ROADMAP (Stage 6 = PARTIAL, шаг 1).

## Запрещено
Hermes core; SOUL (напоминания — следующая задача); cron jobs; scheduler в
backend/storage (расписания только Hermes cron, позже); transactions.

## Отчёт
`tasks/sol/imp05.report.md`: schema, контракты кратко, полный прогон тестов,
deploy-лог, hash коммитов. Commit поимённо + push:
`feat: Stage 6 recurring obligations (migration 005, tools 26, guard 1.3.0)`.
В чат заказчику: 2–3 предложения простым русским.
