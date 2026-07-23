# imp02 (Opus) — отчёт: STOP на шаге 0 (конфликт «draft-создание» vs «25/27/28 read-only»)

## Итог: ОСТАНОВЛЕНО на шаге 0. Deploy, cron jobs, mapping, E2E, Telegram — НЕ выполнялись.

## Шаг 0 — факт по коду (не по докам)
Проверено фактически, `backend/`:
- `monthly_plan_cycles` пишется **только** в `approve_monthly_plan`:
  `backend/db.py:1187` (INSERT) и `:1198` (UPDATE).
- Оба пишут **только terminal-статус** (`target_status` ∈
  `approved_by_oyijon | approved_by_admin | auto_approved`).
- **Ни один** путь (MCP tool, trigger, rule, другая функция) не создаёт строку в
  статусе `draft` / `waiting_oyijon` / `waiting_admin` и не делает переход
  `waiting_oyijon → waiting_admin`. Триггеров/функций в `backend/sql/` нет.
- `set_monthly_budget` пишет только `monthly_budget_plans` / `monthly_budget_items`
  (контент плана), но **не** строку-статус цикла.
- В тестах строки цикла в non-terminal статусах создавались прямым SQL
  (`_cycle(...)`), что для production запрещено.

Вывод: **безопасного существующего пути создания draft-строки цикла нет.**

## Почему это STOP (конфликт с решением заказчика)
ТЗ «Этап 5.3A»:
- п.1: job **25** создаёт draft и ставит status `waiting_oyijon`;
- п.3: job **28** переводит в `waiting_admin`;
- п.5: `waiting_oyijon` / `waiting_admin` — реально хранимые статусы.

Решение заказчика (DECISIONS 2026-07-23): «**25/27/28 строго read-only**; их
mapping entries не содержат mutating tools». Но:
1. Job 25 обязан **записать** draft-строку (`waiting_oyijon`) — это mutation,
   которой нет ни одного tool, и она запрещена решением read-only.
2. Job 28 обязан **записать** переход в `waiting_admin` — тоже mutation без tool
   и против read-only.
3. E2E-шаг «ха»-approve Ойижон (`waiting_oyijon → approved_by_oyijon`) требует
   заранее существующую `waiting_oyijon`-строку — а её создать нечем; ручной
   `approve_monthly_plan` при отсутствии строки возвращает `NO_DRAFT`.
4. Даже job **1** (`source=auto`) при отсутствии cycle-строки идёт по ветке
   copy-last-approved и **игнорирует** уже существующий budget-draft целевого
   месяца (распознавание «valid draft» опирается на наличие cycle-строки).
   Для первого цикла без прошлого approved → `NO_PLAN_SOURCE`.

Итог: заявленный человеко-в-цикле flow 25/27/28/1 в текущем backend + решении
«read-only» **нереализуем без нового mutating-механизма**. Это ровно
STOP-условие из шага 0 и открытый вопрос в
`docs/TZ/CRON_IDENTITY_GATE_5_3A.md` (стр. 341: «какой из шагов вообще имеет
право на mutation»). Код и deploy до решения заказчика не делаю.

## Варианты (нужно решение заказчика)
- **A (рекомендую).** Добавить узкий mutating profile/backend tool цикла
  (напр. `open_monthly_plan_cycle`): job 25 создаёт `waiting_oyijon`-draft,
  job 28 делает `waiting_oyijon → waiting_admin`; никаких прав на transactions.
  Изменить решение «25/27/28 read-only» на «25/28 — только своя узкая
  cycle-мутация; никаких expense/transaction-мутаций; 27 остаётся read-only».
  Единственный вариант, полностью удовлетворяющий ТЗ п.1/п.3/п.5. Требует нового
  ТЗ-подтверждения и отдельной задачи на tool (не входит в imp02).
- **B.** Оставить 25/27/28 чисто как read-only напоминания, **не хранить**
  non-terminal статусы; строку цикла создаёт только approval. Тогда нужно
  изменить контракт `approve_monthly_plan` (создавать строку при первом ручном
  approve валидного budget-draft) и авто-ветку (approve существующего budget-draft,
  а не только copy prev). Теряются статусы `waiting_*` из ТЗ п.5. Требует
  изменения backend (scope imp01) + решения.
- **C.** Draft создаёт не cron, а обычный Telegram-turn Ойижон через новый
  self-only tool; cron 25/27/28 — только напоминания. Не выполняет «25 число
  автоматически создаёт draft», но не требует cron-мутаций.

## Что НЕ сделано (сознательно)
Controlled deploy 22 tools, prompts 4 jobs, создание jobs/mapping/fingerprints,
E2E `cron run`, Telegram-доставка, cleanup, evidence — не начинались, т.к.
блокируются шагом 0. VPS/секреты/production jobs/БД/Telegram не затрагивались.

## Коммит
Только этот отчёт (docs). Feature-коммит `feat: Stage 5.3A production approval
cycle live` не создавался — работа заблокирована.
