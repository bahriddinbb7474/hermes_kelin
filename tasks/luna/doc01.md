# doc01 — Формальное закрытие Stage 5.3 (только документация, кода не трогать)

## Контекст
Repo: Hermes/Mariyam, ветка `main` (последний commit `37dbba7`).
Stage 5.3 (продуктовый месячный план) прошёл controlled Telegram E2E успешно,
но в репозитории статус остался `OFFLINE PASS / LIVE PENDING` и evidence-файла нет.
Задача — зафиксировать закрытие. Никакого кода, только .md + commit + push.

## Факты E2E (источник для evidence, ничего не выдумывать сверх этого)
Controlled Telegram E2E, тестовый аккаунт (реальная Ойижон не подключена):
- Message 1–4: PASS;
- естественное подтверждение «ха» принято;
- товарный план сохранён полностью (items не потеряны);
- planned: 5 та / 60 000 сўм; actual: 4 та / 48 000 сўм; remaining: 12 000 сўм;
- reference price: 12 000 (immutable snapshot);
- duplicate downstream count: 1 (breaker сработал);
- technical traces в ответах: 0;
- identity = exact test-user, admin не изменён;
- runtime: identity plugin 1.0.4, `mariyam_stage53_guard` 1.0.0, tools 21/21/21,
  `agent.max_turns=6`, migration 003 active, `terminal`/`code_execution`/`skills`
  отключены в профиле Мариям.

## Что сделать
1. Создать `docs/EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md`:
   формат по образцу `docs/EVIDENCE_STAGE_5_2_LIVE_PASS_2026-07-16.md`;
   содержание — только факты из блока выше.
2. Найти по репо все вхождения статуса Stage 5.3
   (`grep -rn "OFFLINE PASS / LIVE PENDING" --include=*.md`) и заменить на
   `CLOSED / LIVE PASS`. Ожидаемые файлы: `README.md`, `docs/ROADMAP.md`,
   `docs/ARCHITECT_PROMPT.md`, `docs/PROJECT_CONTEXT.md`, `docs/HERMES_PROFILE.md`,
   файлы в `docs/TZ/`. Обновить только строки статуса и фразы
   «Telegram E2E pending» → ссылка на evidence-файл. Смысл соседнего текста не менять.
3. В `README.md` и `docs/ROADMAP.md` добавить ссылку на evidence-файл рядом со статусом 5.3.
4. Проверить, что нигде не осталось `LIVE PENDING` для 5.3 (повторный grep = 0).
5. Один commit в `main`: `docs: close Stage 5.3 live acceptance` + push.
   ВНИМАНИЕ: в staged diff должны попасть только .md-файлы этой задачи.
   Если в рабочем дереве видны чужие изменения (CRLF-шум в 35 файлах) — их НЕ коммитить,
   добавлять файлы поимённо через `git add <file>`.

## Запрещено
- Трогать код, конфиги, плагины, тесты, статусы Stage 5.3A–6 (остаются PLANNED).
- Менять версии плагинов, tool count, версию ТЗ-документа кроме строки статуса 5.3.

## Отчёт (обязательно)
- Файл `tasks/luna/doc01.report.md`: список изменённых файлов, вывод финального grep,
  hash коммита, подтверждение push.
- В чат заказчику: 2–3 предложения простым русским — что сделано.
