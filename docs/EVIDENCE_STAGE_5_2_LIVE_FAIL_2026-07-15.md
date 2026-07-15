# Evidence: Stage 5.2 LIVE FAIL / FIX REQUIRED

Дата: 2026-07-15

Область: controlled Telegram E2E на временном test-user после offline-реализации Stage 5.2. Реальная Ойижон не подключалась.

## 1. Общий отчёт

PASS:

- суммы трёх групп совпали с БД;
- показан общий итог;
- товарные детали автоматически не показаны;
- ответ — узбекская кириллица;
- технические поля и tool traces отсутствовали;
- вызван `get_monthly_budget_status`;
- requested `user_id = 0`, effective identity = test-user, admin не использован;
- запрос не изменил БД.

Единственный принятый FAIL общего ответа: отсутствовала обязательная финальная фраза:

`Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб чиқамиз. Маълумотлар тайёр.`

Заказчиком приняты и не считаются ошибкой: короткое вступление, заголовки `Сарфлангани / Қолгани`, строка `Жами`, отрицательный остаток с понятным пояснением.

## 2. Подробный ответ по питанию

Наблюдения, подтверждённые по фактическому ответу:

- показаны только товары питания;
- суммы и количества совпали с fixtures;
- количество сахара не выдумано;
- технических traces и латиницы нет.

Недостатки относительно нового решения заказчика:

- summary категории показан списком, а должен быть отдельной таблицей;
- `pcs` показан как `дона`, стандартное user-facing отображение должно быть `та`.

Этот ответ не является формальным E2E PASS: runbook был остановлен после FAIL общего ответа.

## 3. Cleanup и rollback

После точечного cleanup и rollback:

```text
marker transactions: 0
marker budget plans: 0
admin: 8 transactions / 768000 — без изменений
test-user: 1 transaction / 12000
test-user budget plans: 0

Gateway: active
Gateway processes: 1
PostgreSQL: healthy
Time-Agent: running
runtime SKILL SHA: b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4

tools: 21
plugin: 1.0.4
migration: 002
tool_progress: off
skill-protect: 4/4
```

## 4. Provider cost

```text
balance BEFORE: $155.04
historical spend BEFORE: $15.16
balance AFTER: $154.93
historical spend AFTER: $15.27

provider requests: 4
retry: 0
exact cost: $0.109182
dashboard delta: $0.11
model: gpt-5.6-luna
limit ≤6: PASS
```

Ключи, Telegram ID, usernames и token values в evidence не сохранялись.

## 5. Вердикт

```text
Stage 5.2 = LIVE FAIL / FIX REQUIRED
```

Перед повторным E2E необходимо отдельно исправить canonical SKILL и permanent tests. В рамках этой docs-only фиксации SKILL, tests, backend, SQL, deploy и runtime не менялись.
