# Evidence — Stage 5.2 narrow CATEGORY_DETAIL table fix

Дата: 2026-07-16
Статус: **OFFLINE PASS / LIVE PENDING**

## Scope и baseline

- Repo baseline: `27d3c7a` (`main`), clean worktree до начала.
- Предыдущий controlled Telegram E2E на временном test-user:
  - Message 1 — PASS;
  - Message 2 — FAIL только по формату category summary: вместо обязательной
    Markdown-таблицы модель вывела маркированный список;
  - суммы, фактические товары, missing quantity=`—`, `pcs → та`, identity,
    отсутствие technical traces и read-only DB behavior — PASS;
  - provider requests: Message 1 = 3, Message 2 = 3, всего 6/6; retry=0;
  - cleanup и rollback — PASS.
- VPS после rollback: Stage 5.1 baseline, tools `21/21/21`, plugin `1.0.4`,
  migration `002`, Gateway active/one process, PostgreSQL healthy; marker rows `0/0`,
  admin `8/768000`, test-user `1/12000`, budget plans `0`.
- Реальная Ойижон не подключалась.

## Root cause

`CATEGORY_DETAIL` требовал сначала summary группы, но не закреплял, что summary
допустим **только** как отдельная Markdown-таблица. Permanent test проверял порядок
заголовков во всей decision-section и мог ошибочно использовать заголовок из
`GENERAL_FAMILY_REPORT`, поэтому маркированный summary не блокировался offline.

Это узкий prompt-format defect. Backend, tools, descriptions, SQL, identity plugin и
Hermes core не требуют изменений.

## Narrow fix

В единственной decision-table `CATEGORY_DETAIL` теперь явно закреплено:

1. Summary категории выводится только отдельной Markdown-таблицей с точным заголовком
   `Харажат гуруҳи | Режа | Сарфлангани | Қолгани`.
2. Обязательна минимум одна строка выбранной категории.
3. Маркированный список вместо summary-таблицы запрещён.
4. Сразу после summary идёт таблица фактических товаров
   `Маҳсулот | Миқдор | Сарфлангани`.
5. Добавлен один короткий правильный пример двух таблиц.

`GENERAL_FAMILY_REPORT`, tools/descriptions, backend, SQL, identity plugin, Hermes
core и остальные правила SOUL не менялись.

## Permanent regression

- `tests/test_mariyam_skill_stage52.py` проверяет правила непосредственно в строке
  `CATEGORY_DETAIL`, точный порядок двух таблиц и короткий правильный пример.
- `tests/inspect_effective_prompt.py` экспортирует отдельные markers для двух
  заголовков, table-only, запрета списка и порядка summary → products.
- `tests/test_mariyam_effective_prompt.py` проверяет markers в реально собранном
  Telegram effective prompt.
- Сохранены contracts Message 1, `pcs → та`, missing quantity=`—`, запрет product
  plan, единственный tracked prompt-source `SOUL.md` и отсутствие truncation.
- SHA-protection обновлена на canonical LF SHA-256:
  `a9b584e14d704f08b4778b7928ca71a0cf095394583f769c5e9571097884b4e4`.

## TDD и проверки

- RED: focused Stage 5.2/effective-prompt suite — `3 failed, 9 passed`; failures
  воспроизвели отсутствие table-only rules и короткого примера.
- GREEN: focused suite — `12 passed`.
- Full `pytest -q`: `160 passed, 2 skipped`.
- `ruff check .`: PASS.
- `python -m compileall -q backend tests`: PASS.
- `git diff --check`: PASS.

## Verdict

**Stage 5.2 = OFFLINE PASS / LIVE PENDING.**
**VPS runtime = Stage 5.1 rollback baseline.**

В этой задаче commit, VPS deploy, Telegram/API retest и push не выполнялись. Для
закрытия Stage 5.2 требуется отдельно разрешённый deploy и controlled live retest.
