# EVIDENCE — Этап 5 E2E (бухгалтерия) — PASS

Дата runtime: 2026-07-12 / 2026-07-13 Asia/Tashkent
Аккаунт: временный test-user «Тест Ойижон» (internal `user_id=20`, role=oyijon)
Реальная Ойижон: **не подключена**
Plugin runtime: `mariyam_identity_guard` **1.0.3**
SKILL runtime (восстановлен): sha256 `dfc7e327605cbf293737f6b1b8395e22c551bc53dabc4d35249cc4e7c562f8ea`
Hermes: v0.18.2, profile `mariyam_oyijon`

## 0. Предшествующие FAIL (не удалять)

| Evidence | Суть |
|---|---|
| `EVIDENCE_STAGE5_E2E_FAIL_2026-07-12.md` | Live save писал admin (identity fail-open / MCP bare-only) |
| Ранние FAIL turns | admin rows id 9–14 (ошибочные bread/meat); **не удалялись** |
| Business FAIL после SKILL old rule | model отказал tool без `origin.user_id` (security +0 admin) |
| ensure_user type FAIL | bound `telegram_id` str → backend «not integer» |

Эти FAIL сохранены как forensic. Финальный PASS ниже **не** стирает историю.

## 1. Что вошло в PASS-реализацию

1. **MCP-prefixed canonicalize** (`mcp__mariyam_backend__*` → bare policy name).
2. **Fail-closed barrier** (ContextVar): primary exception → `IDENTITY_GUARD_ERROR`, downstream=0.
3. **ensure_user `telegram_id` → int** (`_to_pos_int`; unsafe → `IDENTITY_UNRESOLVED`).
4. **SKILL §1.1 sentinel** `user_id: 0`; отсутствие origin в LLM ≠ отказ от tool.
5. **MAP** durable: unit `Environment=` + profile `.env` (Hermes может перезаписать unit; agent loads `.env`).
6. Permanent tests: guard MCP/sentinel + `tests/test_mariyam_skill_identity.py`.

## 2. Preflight (перед финальным E2E)

- Gateway: active
- Plugin: 1.0.3
- Offline probe: ensure_user → int tg + role oyijon; save `user_id=0` → effective **20**
- Oyijon session history cleared after backup (old ensure_user/admin pattern removed)
- Baseline DB: admin **8 / 768000**, test **0 / 0**

## 3. E2E 4/4 (строго по одному сообщению)

| # | Вход | Bot (кратко) | test id=20 | admin id=1 | Guard log |
|---|---|---|---|---|---|
| 1 | Бугун нон 12 минг, гўшт 180 минг олдим. | ёзиб қўйдим, жами 192 000 | 2 / **192000** (bread 12k + meat 180k) | 8 / 768000 (+0) | `save_expense` requested=0 effective=20 |
| 2 | Шу ойдаги харажатларимни айтинг. | жами 192 000 | 2 / 192000 (без изменений) | +0 | `get_balance_summary` 0→20 |
| 3 | Гўштни 150 минг қилинг. | тузатдим 150 000 | 2 / **162000** (meat 150k) | +0 | `update_last_expense` 0→20 |
| 4 | Охирги харажатни ўчиринг. | ўчирилди 150 000 | **1 / 12000** (нон) | +0 | `delete_last_expense` 0→20 |

Финальная БД (после msg4):

```
user_id | n | sum
1       | 8 | 768000.00   -- admin, ошибочные rows сохранены
20      | 1 |  12000.00   -- test-user, bread only
```

Tool-traces в UI: **нет** (tool_progress off).
MCP tools: live `mcp__mariyam_backend__*`.
effective user_id: **всегда 20** на test-user session.

## 4. Вердикт

| AC | Результат |
|---|---|
| create 2×192k @ test-user | PASS |
| monthly report = DB | PASS |
| update meat → 150k / total 162k | PASS |
| delete last → bread 12k remains | PASS |
| admin +0 за весь E2E | PASS |
| identity deterministic (not LLM) | PASS |
| Stage 5 | **ЗАКРЫТ (PASS)** |

## 5. ОТКРЫТЫЙ КРИТИЧЕСКИЙ БЛОКЕР (не Stage 5 AC)

**Self-improvement / curator drift SKILL.md (2026-07-13 ~00:24 +05)**

- После msg4 runtime показал служебное:
  `Self-improvement review: Patched SKILL.md in skill 'mariyam' (1 replacement).`
- Active profile SKILL sha сменился: `dfc7e327…` → `6df02380…`
- Log: `skill_manage` curator patch **refused** (content not approved), но файл на диске уже отличался.
- **Действие:** SKILL восстановлен из `SKILL.md.bak.20260712T191339Z` → sha **`dfc7e327…` OK**.
- **Причина drift root-cause не устранена.**
- **Запрет:** следующие live-этапы и handover **запрещены** до отдельного минимального фикса, блокирующего самопереписывание security-critical SKILL (и показ служебных сообщений end-user).

## 6. Не делалось

- push в origin
- удаление admin ошибочных rows
- подключение реальной Ойижон
- изменение Hermes core / backend / `/opt/time-agent`
- bump ТЗ (требования не менялись; исправлена реализация)
