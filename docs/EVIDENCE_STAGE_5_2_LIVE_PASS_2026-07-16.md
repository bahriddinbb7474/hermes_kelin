# Stage 5.2 — LIVE PASS closure evidence

Date: 2026-07-16  
Status: **CLOSED / LIVE PASS**

## Scope

Stage 5.2 closes the simple family-report contract. The last correction makes
response completion depend only on report type, never on whether a `Жами` row
is present. This is a correction of the existing contract; `DECISIONS.md` was
not changed.

Stage 5.3–6 remain **PLANNED / NOT IMPLEMENTED**. The real Oyijon is not
connected.

## Live acceptance already obtained

- Message 1 (`GENERAL_FAMILY_REPORT`) was previously confirmed live and was not
  repeated.
- Message 2 (`CATEGORY_DETAIL`) was confirmed live: category summary table,
  product table, exact plan/spent/remaining values and tool-backed product
  quantities/amounts were visible in Telegram.
- The final report-type completion correction was verified offline. By explicit
  instruction, no new Telegram message, LLM call or provider request was made.
- Special stored-prompt wrapper strings are not acceptance criteria. Telegram
  profile names are not identity. Identity is verified only through the exact
  Telegram session, private mapping, `requested=0`, and effective test-user.

## Local contract proof

Permanent tests cover both decision-table rows:

- `GENERAL_FAMILY_REPORT`: `Жами` is allowed and the exact general-report final
  phrase is mandatory.
- `CATEGORY_DETAIL`: category summary table first, product table second; `Жами`
  is allowed; the response ends after the tables without the general-report
  final phrase and without a question.
- `Жами` never selects the completion behavior.

Canonical LF SOUL SHA-256:

`3135a12e07529222b9db350ccca07f52d79b76b0ca2b8597bec50a4a0f9a176e`

## VPS deployment and rollback safety

- A private rollback backup of the previous VPS `SOUL.md`, active legacy
  Mariyam skill, `config.yaml`, routed test-user session and SQLite state was
  created before mutation.
- An initial offline session-invalidation implementation was rejected by the
  post-deploy route check and fully rolled back before the final deployment.
- The final deployment installed the canonical LF SOUL and removed the active
  Mariyam `SKILL.md`.
- The exact private-mapped test-user route was rotated through Hermes'
  `SessionStore.reset_session()` path. Other routes were unchanged; the new
  routed session is empty and has zero API calls.
- Only `hermes-gateway-mariyam_oyijon.service` was cycled.
- Skill protection remained enabled: skills toolset disabled, creation nudge
  `0`, write approval enabled, memory notifications off and
  `tool_progress=off`.

## Deployed effective-prompt proof

Offline assembly with the installed Hermes runtime proved:

- runtime SOUL SHA equals the canonical LF SHA above;
- the full SOUL occurs exactly once in the assembled prompt;
- no SOUL truncation and no skills index;
- one report decision table;
- `GENERAL_FAMILY_REPORT` has the mandatory exact final phrase;
- `CATEGORY_DETAIL` has the category summary and product tables and explicitly
  forbids the general-report final phrase and follow-up questions;
- both rows allow `Жами`, while the global contract states that `Жами` never
  determines completion;
- `pcs → та`, category-summary table-only, summary-before-products and Stage 5.3
  product-plan bans are present;
- obsolete automatic-detail instructions and `дона` are absent.

## Runtime verification

- Gateway: active, enabled, one service MainPID.
- PostgreSQL: healthy.
- Tools: inventory / dispatch / MCP discovery = `21 / 21 / 21`.
- Identity plugin: `1.0.4`.
- Applied project migration: `002`; migrations `003/004/005` are absent.
- Provider/API call delta during backup, deployment, reset and offline checks:
  `0`.
- Backend, SQL, Hermes core, identity plugin and migrations were not modified.
- No command targeted `/opt/time-agent`, its unit, container, volumes, logs or
  backups.

## Closure

`Stage 5.2 = CLOSED / LIVE PASS`  
`Stage 5.3–6 = PLANNED / NOT IMPLEMENTED`  
`real Oyijon = not connected`

No commit or push was created.
