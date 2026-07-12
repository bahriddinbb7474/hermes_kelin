# Security And Privacy

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Telegram allowlist

Начальное состояние allowlist (v3.4) — **только Telegram ID администратора (Бахриддин ака)**. Для одобренных end-to-end тестов разрешено **временно** добавить второй аккаунт заказчика как test-user «Тест Ойижон» (ТЗ §0.4); перед handover он удаляется. Реальный Telegram ID Ойижон добавляется в allowlist только при handover (ТЗ §19).

Все остальные блокируются: безопасный отказ — либо короткий текст `Кечирасиз, бу шахсий ёрдамчи.`, либо тихая блокировка (Hermes v0.18.2). В обоих случаях они не могут читать данные или вызывать tools.

> **Отказ unauthorized-пользователю (v3.5):** для установленного Hermes v0.18.2 допустимы два варианта (ТЗ §0.5): (а) короткий текст `Кечирасиз, бу шахсий ёрдамчи.`; (б) тихая блокировка без текста. В обоих случаях строго обязательно отсутствие agent session / LLM-вызова / tool-вызова / обращения к БД / чтения данных. Результат: `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL`. Короткий текст остаётся предпочтительным, но для v0.18.2 не обязателен. Решение заказчика (2026-07-12) закрывает прежний `FAIL_TEXT_AC`; не разрешает доступ и не ослабляет allowlist.

## Секреты

- Bot token, DB URL, API keys, rclone credentials — только `.env` или переменные окружения.
- Не хранить секреты в коде, git, логах или Markdown.
- **Запрещены fallback-креды** (значения по умолчанию для `DATABASE_URL`/паролей) в коде, Dockerfile и compose — при отсутствии переменной процесс падает сразу (ТЗ §17).
- **`.dockerignore` обязателен**: `.env`, `.env.*`, `.venv/`, `__pycache__/`, `.git/`, `logs/` не должны попадать в docker-образ. Содержимое образа проверяется перед деплоем.
- Для HTTP MCP tools на одном VPS слушать только localhost; по умолчанию использовать stdio (ТЗ §16).

## Тесты и данные

- Тесты содержат `TRUNCATE ... RESTART IDENTITY CASCADE` — они обязаны иметь предохранитель и отказываться работать с боевой БД (ТЗ §20, п.15). Никогда не запускать их против боевой БД `hermes`.
- Жёсткий guard (`tests/db_guard.py`, Блок 6Ж) срабатывает ДО подключения к БД и требует одновременно:
  - `APP_ENV=test` (строго);
  - имя базы данных обязательно оканчивается на `_test`;
  - точное имя `hermes` запрещено безусловно;
  - `localhost` / `127.0.0.1` сами по себе НЕ являются достаточным признаком тестовой БД;
  - удалённая тестовая БД `*_test` дополнительно требует `ALLOW_DESTRUCTIVE_TESTS=1`.
- `ALLOW_DESTRUCTIVE_TESTS=1` НЕ может обойти запрет `hermes`, отсутствие `APP_ENV=test` или отсутствие суффикса `_test`.

> **Статус (2026-07-12, после merge в `main` `dd9261e`):** жёсткий `tests/db_guard.py` (Блок 6Ж, 16 unit-тестов PASS) **уже merged в `main`** через `dd9261e`. Аналогично **identity guard** (`deploy/hermes_plugins/mariyam_identity_guard/`, 43 теста PASS, независимый аудит `PASS_TO_VPS_PHASE_B`) **также merged в `main`**. **VPS installation/runtime (Фаза B) обоих ещё НЕ выполнена** — требует отдельного разрешения. Destructive suite не запускался на production-БД. Обязательны `APP_ENV=test` и БД с окончанием `_test`; production БД `hermes` запрещена безусловно; `localhost`/`127.0.0.1` сами по себе НЕ являются достаточным признаком тестовой БД.

## Детерминированный identity guard (v3.6)

- Sender определяется по **exact Telegram session** (persisted `sessions.origin_json`, platform=`telegram`), а не по аргументам модели/display name.
- `role=oyijon` — **self-only** (всегда свой internal `user_id`).
- `role=admin` cross-target — только по allowlist tools (`get_expense_report`, `get_balance_summary`, `get_admin_report_data`, `save_plan_note`) И `allowed_target_user_ids`; cross-target write/delete запрещены.
- **Fail-closed:** unknown/corrupt identity, неизвестная роль, malformed mapping и небезопасные права mapping-файла блокируются **до MCP tool** (коды `IDENTITY_UNRESOLVED` / `IDENTITY_TARGET_FORBIDDEN` / `IDENTITY_MAPPING_INVALID` / `IDENTITY_MAPPING_PERMISSIONS` / `IDENTITY_GUARD_ERROR`).
- Mapping **вне git и вне model-visible profile**; файл `MARIYAM_IDENTITY_MAP_FILE` с правами **`chmod 600`** (plugin отказывает при более широких правах).
- **Raw Telegram ID и содержимое mapping не логируются** (маскируются функцией `_mask`).
- Плагин находится в репо, но на VPS ещё **НЕ установлен** — runtime (Фаза B) требует отдельного разрешения; до установки identity обеспечивается только allowlist-логикой.

## Приватность

- Не хранить сырые voice-файлы дольше необходимого.
- Логи ротировать и не писать туда токены/ключи.
- В админ-отчётах не раскрывать лишние интимные детали.
- Cloud STT/TTS/LLM допустимы как осознанный компромисс, но передавать минимум данных.

## Backup

Backup должен включать:

- PostgreSQL dump;
- Hermes profile `mariyam_oyijon` с memory/skills/cron/sessions;
- конфиги tools без секретов.

Шифрование обязательно: `rclone crypt` или gpg-архив. Хранение: VPS + Google Drive через rclone.

## Restore и alerts

Restore нужно реально проверить до go-live: поднять чистое окружение, восстановить известный расход и сверить число строк.

Safety alerts: медицинские/критические фразы ловятся LLM + keyword-предохранителем; при срабатывании Hermes мягко отвечает Ойижон, уведомляет Бахриддин ака и пишет `alert_event`.
