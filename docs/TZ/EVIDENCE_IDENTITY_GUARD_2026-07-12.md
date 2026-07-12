# Evidence — Deterministic Identity Guard

Дата: 2026-07-12
Связь: `TZ_Hermes_Mariyam_FINAL_v3_0.md` §0.6, §15, §19, §21 (v3.6).
Плагин: `deploy/hermes_plugins/mariyam_identity_guard/`.

## 1. Инцидент

- Telegram session test-user была корректной (allowlist пропустил sender).
- Hermes вызвал бухгалтерские tools с `user_id` администратора.
- Две тестовые записи попали владельцу admin (вместо test-user).
- Backend сохранил переданный `user_id` корректно — ошибка не в backend.
- Root cause: стабильный Telegram sender ID отсутствовал в model context, identity ошибочно зависела от LLM (модель подставила admin `user_id` в аргументы tool).

Реальные Telegram ID в этом документе не приводятся.

## 2. Решение

- Profile plugin (Hermes-first, не второй мозг):
  `deploy/hermes_plugins/mariyam_identity_guard/__init__.py` + `plugin.yaml`.
- Регистрируется через официальный `tool_execution` middleware (Hermes PluginManager).
- Поток: current session → persisted Telegram source (`sessions.origin_json`, platform=`telegram`) → private mapping → internal `users.id`.
- Mapping применяется ДО MCP tool call; `effective user_id` переписывается на sender-bound.
- Identity НЕ определяется по display name и НЕ доверяется LLM-аргументам.

## 3. Политика

- **Oyijon self-only:** `role=oyijon` всегда принудительно получает свой собственный `user_id`, независимо от запрошенного.
- **Admin self-target:** `role=admin` без указания target работает на себя; self-target всегда разрешён.
- **Admin cross-target:** разрешён ТОЛЬКО если tool входит в строгий allowlist
  (`get_expense_report`, `get_balance_summary`, `get_admin_report_data`, `save_plan_note`)
  И target входит в `allowed_target_user_ids` из mapping.
- **Cross-target write/delete запрещены:** любой user-scoped write/delete tool вне self-target блокируется (`IDENTITY_TARGET_FORBIDDEN`).
- **Unknown/corrupt identity fail-closed:** отсутствующий sender, malformed mapping, неизвестная роль, небезопасные права файла → блок до tool (`IDENTITY_UNRESOLVED` / `IDENTITY_MAPPING_INVALID` / `IDENTITY_MAPPING_PERMISSIONS` / `IDENTITY_GUARD_ERROR`).
- **Mapping вне git/profile:** файл `MARIYAM_IDENTITY_MAP_FILE` хранится вне репозитория и вне model-visible profile; права POSIX `0600` (plugin отказывает при более широких правах). Raw Telegram ID и содержимое mapping не логируются (маскируются функцией `_mask`).

Текущий allowlist tools (ровно по коду, `USER_SCOPED_TOOLS` + `ADMIN_CROSS_TARGET_TOOLS`):

- User-scoped (14): `save_expense`, `save_income`, `update_expense`, `update_last_expense`, `delete_expense`, `delete_last_expense`, `get_expense_report`, `get_balance_summary`, `save_quran_progress`, `get_quran_progress`, `save_health_note`, `save_alert_event`, `save_plan_note`, `get_admin_report_data`.
- Admin cross-target разрешён (4): `get_expense_report`, `get_balance_summary`, `get_admin_report_data`, `save_plan_note`.
- Global (не user-scoped, pass-through, 4): `backup_data`, `get_backup_status`, `get_bot_status`, `log_usage_cost`.
- `ensure_user`: `telegram_id`/`role`/`display_name` привязываются к sender mapping (LLM не может создать произвольного пользователя).

## 4. История исправлений

- `a1a42b6` — initial identity guard (role-unaware).
- Первый независимый аудит: **BLOCK** (identity зависела от недостоверного источника).
- `4e1c519` — role-aware и fail-closed (привязка к sender, блокировка unknown/corrupt).
- Второй аудит: **BLOCK** из-за отсутствия строгой схемы mapping и proof discovery плагина.
- `a0011e2` — strict mapping schema (`validate_mapping_schema`) и реальный plugin discovery через Hermes PluginManager.
- Финальный независимый аудит: **PASS_TO_VPS_PHASE_B**.
- `dd9261e` — merge всей feature-ветки в `main`

## 5. Проверки

- pre-merge: **43 passed**, ruff clean, `git diff --check` clean.
- post-merge: **43 passed**, ruff clean, `git diff --check` clean.
- Реальный Hermes v0.18.2 PluginManager discovery плагина: **PASS** (integration-тест на установленном `hermes_cli`).
- malformed mapping → `IDENTITY_MAPPING_INVALID` (fail-closed, downstream calls = 0).
- unknown sender → `IDENTITY_UNRESOLVED` (downstream calls = 0).
- Raw Telegram IDs отсутствуют в логах/отчётах (маскировка `_mask`).

## 6. Текущий статус

- Код merged в `main` (`dd9261e`).
- Plugin на VPS ещё **НЕ установлен** (Фаза B не выполнялась).
- Gateway не перезапускался для identity guard.
- Telegram runtime smoke (Этап 5 E2E) **НЕ выполнен**.
- Phase B требует отдельного разрешения заказчика.
- Платный smoke требует отдельного лимита (бюджетное правило ТЗ/DECISIONS).
- Stage 5 остаётся **открытым** (VPS runtime и Telegram E2E pending).
- Реальная Ойижон **НЕ подключена**.
