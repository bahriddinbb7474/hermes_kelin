# Evidence: Stage 5.2 OFFLINE PASS / LIVE PENDING

Дата: 2026-07-14
Baseline HEAD: `43044c9df29d34d20d7f5250d7dfb63411061693`
Область: только offline-реализация простых семейных отчётов для Ойижон.

## Реализовано

- Canonical `skills/mariyam/SKILL.md`: общий отчёт первой таблицей, ровно один мягкий вопрос, детали только по просьбе, питание по товарам, unknown=`айтилмаган`, user-facing units, превышение плана простыми словами и запрет технического текста.
- Permanent contract: `tests/test_mariyam_skill_stage52.py`.
- SHA-protection обновлена в `tests/test_mariyam_skill_protection.py`.
- Новый repo SKILL SHA-256: `b3afd9ecfb16a4d4618be898573a84c00ae24a1c3b41e8ae57823912b9ac9d18`.

## Offline verification

- Targeted suite: **110 passed**.
- Full suite: **159 passed, 2 skipped**.
- `ruff check .`: PASS.
- `python -m compileall backend tests`: PASS.
- `git diff --check`: PASS.
- Backend inventory: **21 tools**.

Старые contracts сохранены: identity sentinel `user_id: 0`, `ensure_user` policy, quantity/unit policy, financial tools, medical safety и узбекская кириллица.

## Границы

- Backend, БД, identity plugin, Hermes core и deploy-код не менялись.
- Runtime остаётся **21 tools / plugin 1.0.4 / migration 002**.
- Migrations 003/004/005 отсутствуют и не применялись.
- VPS/profile не менялись; runtime SKILL остаётся Stage 5.1 SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`.
- Telegram E2E не выполнялся.
- Платные API не вызывались.
- Реальная Ойижон не подключалась.
- Commit/push/merge не выполнялись.

## Вердикт

**Stage 5.2 = OFFLINE PASS / LIVE PENDING.**

Stage 5.2 не CLOSED и не LIVE PASS до отдельно разрешённого Telegram E2E.