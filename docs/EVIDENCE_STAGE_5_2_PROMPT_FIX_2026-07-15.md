# Evidence — Stage 5.2 deterministic effective prompt fix

Дата: 2026-07-15
Статус: **OFFLINE PASS / LIVE PENDING**

## Scope и baseline

- Repo baseline: `f3d150d4054a9cd07c25c4e220c419896522ecd8`.
- VPS runtime до и после аудита: Hermes `v0.18.2`, upstream `3b2ef789`,
  Stage 5.1 SKILL SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`.
- Проваленный run: **3 requests / $0.058928**.
- Аудит VPS был read-only. Новых Telegram/API calls, VPS deploy или mutations не было.
- Telegram ID, secrets и полный prompt в evidence не включены.

## Что реально собирает Hermes

Проверено по `agent/system_prompt.py`, `agent/prompt_builder.py`,
`agent/skill_utils.py`, `hermes prompt-size --platform telegram` и безопасной
`build_system_prompt_parts()` introspection.

1. `SOUL.md` загружается полностью в primary identity slot через `load_soul_md()`.
2. `SKILL.md` body в system prompt не попадает. `build_skills_system_prompt()`
   формирует только index из frontmatter name/description; body читается лишь
   отдельным `skill_view`.
3. `agent.disabled_toolsets: [skills]` удаляет `skills_list`, `skill_view` и
   `skill_manage`. `system_prompt.py` при отсутствии этих tools вообще не добавляет
   skills index. VPS prompt-size: skills index = `0` chars.
4. `skills.enabled` не читается loader-ом Hermes v0.18.2. Поддерживаемые filter keys
   в этом пути — `skills.disabled` и `skills.platform_disabled`.
5. VPS assembled prompt до fix: SOUL = `741` chars; Stage 5.2 markers,
   обязательная финальная фраза и unit contract отсутствовали; полный SKILL
   отсутствовал. Prompt-size: system prompt `11285` chars, tool schemas `43224`
   chars, `25` core tool schemas.
6. Локальный установленный Hermes имеет другую ревизию (`v0.18.0`, local
   `7426c09b`), но подтверждает ту же loader-семантику: полный SOUL присутствует,
   полный SKILL отсутствует. Target-вывод основан на VPS v0.18.2/`3b2ef789`.

## Проверенные prompt sources

- `profile/SOUL.md`: загружался, но содержал только короткую persona и ошибочное
  утверждение, что полный skill уже loaded.
- `profile/config.yaml`: `skills.enabled: [mariyam]` был no-op;
  `agent.disabled_toolsets: [skills]` реально отключал весь skill path.
- `platform_hints.telegram`: profile override отсутствовал; применялся встроенный
  Hermes Telegram hint без Stage 5.2 contract.
- `agent.system_prompt` / `HERMES_EPHEMERAL_SYSTEM_PROMPT`: отсутствовали.
- `MEMORY.md` и `USER.md`: загружались, Stage 5.2 markers не содержали.
- `TERMINAL_CWD`: `/`; `.hermes.md`, `HERMES.md`, `AGENTS.md`, `CLAUDE.md`,
  `.cursorrules` в effective context отсутствовали.
- `pre_llm_call`: active profile plugins не добавляли prompt instructions.
- Tool schemas передавались отдельно. `get_expense_report` был описан как общий
  отчёт и возвращал `by_item`; description не требовал automatic details, но и не
  запрещал их. Backend/tool descriptions менять не потребовалось.

## Failed session и реальные tool calls

- Session создана `2026-07-12T07:54:48Z`, то есть до Stage 5.2 deploy
  `2026-07-15T15:14:59Z`.
- Очистка message rows и restart Gateway не создали новую session. Сохранённый
  `sessions.system_prompt` был восстановлен из DB и не содержал Stage 5.2 markers.
- Реальные вызовы: сначала `session_search`, затем `get_expense_report` с
  sanitized args `user_id: 0`, `period: month`, `compare_previous: false`,
  `trend_months: 3`.
- `get_monthly_budget_status` не вызывался. `ensure_user` не вызывался.
- В результате модель получила `by_item` без запрета automatic details, не получила
  plan/remaining и сама выбрала слово `дона`. Никакая загруженная инструкция не
  требовала такого ответа: причиной была **потеря критического contract**, а не
  конфликт реально прочитанных Stage 5.2 правил.

## Root cause

1. Критический contract находился в `SKILL.md`, body которого Hermes автоматически
   не добавляет в prompt.
2. Skill tools были отключены, поэтому модель не видела даже index и не могла
   вызвать `skill_view`; `skills.enabled` это не исправлял.
3. Deploy переиспользовал старую session с persisted `sessions.system_prompt`;
   restart Gateway не является session rebuild.
4. В effective prompt не было tool-choice/format/unit правил Stage 5.2, поэтому
   generic report schema и `by_item` привели к automatic products, `дона` и
   отсутствию plan/remaining.

## Fix

- Единственный canonical repo-source перенесён в
  `deploy/hermes_profile_mariyam_oyijon/SOUL.md`; legacy
  `skills/mariyam/SKILL.md` удалён.
- Report contract сведён к одной decision-table:
  `GENERAL_FAMILY_REPORT`, `CATEGORY_DETAIL`, `COMPARE_OR_TREND`,
  `SET_MONTHLY_BUDGET`.
- Закреплены `get_monthly_budget_status` для общего отчёта, запрет automatic
  products, детали только по конкретной группе, summary перед actual items,
  `pcs → та`, дословная финальная фраза и запрет Stage 5.3 product plan.
- No-op `skills.enabled` удалён; `disabled_toolsets: [skills]` сохранён как security
  guard, поскольку SOUL не зависит от skill tools.
- Deploy runbook требует: offline prompt preflight на deployed profile без API,
  `/new`, первый controlled turn и только затем read-only проверку новой
  `sessions.system_prompt` перед остальными acceptance-сообщениями.
- Hermes core, backend, tool descriptions, SQL, identity plugin и runtime не менялись.

## Effective prompt verification

Offline inspector собрал Telegram prompt через реальный
`build_system_prompt_parts()` без network call. Contract отдельно выполнен на
точном source commit Hermes `3b2ef789` / v0.18.2, извлечённом read-only через
`git archive`: **5 passed**. Локальный installed v0.18.0 дал те же markers:

- full SOUL present: PASS;
- SOUL chars: `17073`; assembled SOUL content SHA:
  `87612d4d2a0eb80816f62ba3c2a9dbacf23113a96b4d888d079bead6a570b944`;
- canonical Git/deploy LF-byte SHA-256 (`.gitattributes: eol=lf`):
  `713021c2cfd6c3abff206b6a79ec7423c06c6920645ce4a6c2d31158a108c98a`;
- truncation: false; skills index: absent;
- decision-table/final phrase/`pcs → та`/auto-detail ban/Stage 5.3 ban: present;
- `дона`, old automatic-item instruction и old category/item example: absent;
- identity, language и medical contracts: present.

## Checks

- RED before fix: `tests/test_mariyam_effective_prompt.py` — `4 failed`.
- Targeted identity/Stage 5.1/Stage 5.2/effective prompt/protection:
  **117 passed**.
- Exact Hermes v0.18.2 effective-prompt contract: **5 passed**.
- Full `pytest -q`: **159 passed, 2 skipped**.
- `ruff check .`: PASS.
- `python -m compileall -q backend tests`: PASS.
- `git diff --check`: PASS.

## Verdict

**OFFLINE PASS / LIVE PENDING.** ТЗ повышено до v3.14. Будущий deploy и live
acceptance требуют отдельного разрешения. До первого платного сообщения выполняются
offline preflight deployed-профиля и `/new`; после первого controlled turn —
stored-prompt check, затем остальные E2E. Stage 5.3 не реализован.
