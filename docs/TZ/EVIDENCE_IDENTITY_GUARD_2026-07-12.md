# Evidence — Deterministic Identity Guard

Дата: 2026-07-12 → runtime close 2026-07-13
Связь: `TZ_Hermes_Mariyam_FINAL_v3_0.md` §0.6, §15, §19, §21 (v3.6).
Плагин: `deploy/hermes_plugins/mariyam_identity_guard/` (**1.0.3**).

## 1. Инцидент (исторический)

- Telegram session test-user была корректной (allowlist пропустил sender).
- Hermes вызвал бухгалтерские tools с `user_id` администратора.
- Тестовые записи попадали владельцу admin (вместо test-user).
- Backend сохранил переданный `user_id` корректно — ошибка не в backend.
- Root cause (эволюция):
  1. identity зависела от LLM / display_name;
  2. live tools приходят как `mcp__mariyam_backend__*` — bare-only guard = passthrough;
  3. primary callback exception раньше fail-open (Hermes fallback);
  4. `ensure_user` получал `telegram_id` string, backend schema integer;
  5. SKILL запрещал tool без `origin.user_id` в LLM-контексте (business FAIL, admin safe).

Реальные Telegram ID в этом документе не приводятся.

## 2. Решение (финальная реализация 1.0.3)

- Profile plugin (Hermes-first, не второй мозг):
  `deploy/hermes_plugins/mariyam_identity_guard/__init__.py` + `plugin.yaml` **1.0.3**.
- `tool_execution` middleware + **fail-closed barrier** (ContextVar).
- `canonical_tool_name()`: только prefix `mcp__mariyam_backend__` → bare policy name; original name для log/next.
- Поток: session → `sessions.origin_json` (telegram) → private mapping (`MARIYAM_IDENTITY_MAP_FILE`) → internal `users.id`.
- `effective user_id` переписывается **до** MCP; LLM args / display_name не authorization.
- `ensure_user`: `telegram_id` через `_to_pos_int` (str origin OK → int; unsafe → `IDENTITY_UNRESOLVED`).
- SKILL §1.1: sentinel `user_id: 0`; отсутствие origin в LLM **не** запрещает tool; ensure_user не в обычных msg.

## 3. Политика

- **Oyijon self-only:** всегда свой `user_id`.
- **Admin self-target / cross-target allowlist:** как в коде (`USER_SCOPED_TOOLS`, `ADMIN_CROSS_TARGET_TOOLS`).
- **Cross-target write/delete:** `IDENTITY_TARGET_FORBIDDEN`.
- **Fail-closed codes:** `IDENTITY_UNRESOLVED` / `IDENTITY_TARGET_FORBIDDEN` / `IDENTITY_MAPPING_INVALID` / `IDENTITY_MAPPING_PERMISSIONS` / `IDENTITY_GUARD_ERROR`.
- Mapping вне git; POSIX **0600**; raw TG id не логируются (`_mask`).

## 4. История исправлений

- `a1a42b6` — initial identity guard (role-unaware).
- Аудит BLOCK → `4e1c519` role-aware fail-closed.
- Аудит BLOCK → `a0011e2` strict schema + PluginManager discovery.
- Аудит **PASS_TO_VPS_PHASE_B** → merge `dd9261e` в `main`.
- Runtime FAIL (MCP bare-only / barrier) → **1.0.1** barrier + **1.0.2** MCP prefix + MAP unit.
- ensure_user int + SKILL sentinel → **1.0.3**.
- Stage 5 Telegram E2E 4/4 PASS — см. `EVIDENCE_STAGE_5_E2E_2026-07-12.md`.

## 5. Проверки (локально, post-1.0.3)

- full pytest: **83 passed** (identity suite + skill contract + project).
- ruff clean; `py_compile` OK; `git diff --check` clean.
- Offline VPS Hermes 0.18.2: callbacks=2; MCP save `0→20`; ensure_user int tg + oyijon; primary exception → `IDENTITY_GUARD_ERROR` downstream=0.
- Live E2E: all four tools `requested=0 effective=20` on test session; admin +0.

## 6. Текущий статус

- Plugin **1.0.3** установлен в profile runtime VPS.
- Stage 5 (бухгалтерия identity + CRUD) — **ЗАКРЫТ (PASS)**.
- Admin ошибочные historical rows (**8 / 768000**) **не удалялись**.
- Final test-user: **1 / 12000** (нон) после E2E msg4.
- Реальная Ойижон **НЕ подключена**.
- **ОТКРЫТО (критично, не identity AC):** self-improvement drift SKILL.md после msg4 — runtime изменил security-critical skill + служебное сообщение в Telegram; файл восстановлен на `dfc7e327…`; root-cause не закрыт → **live follow-up / handover запрещены** до минимального фикса (см. Stage 5 evidence §5).
