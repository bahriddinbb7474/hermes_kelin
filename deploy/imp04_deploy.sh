#!/usr/bin/env bash
# imp04 controlled deploy: SOUL v2 + toolset compaction + new cron prompts.
# Run on the VPS as the profile service user (timeagent). Idempotent.
#
#   bash imp04_deploy.sh            # dry-run: show what would change
#   bash imp04_deploy.sh --apply    # apply, then restart the gateway
#   bash imp04_deploy.sh --rollback <backup-dir>
#
# SRC is the uploaded bundle (repo files); APP is the deployed backend copy.

set -euo pipefail

PROFILE="${HERMES_HOME:-$HOME/.hermes/profiles/mariyam_oyijon}"
SRC="${IMP04_SRC:-/tmp/imp04}"
APP="${MARIYAM_APP:-/opt/hermes-mariyam}"
PY="$HOME/.hermes/hermes-agent/venv/bin/python"
UNIT="hermes-gateway-mariyam_oyijon.service"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$HOME/imp04-backup-$STAMP"

mode="${1:-}"

if [ "$mode" = "--rollback" ]; then
  src="${2:?rollback needs a backup dir}"
  chmod 644 "$PROFILE/SOUL.md"
  cp "$src/SOUL.md" "$PROFILE/SOUL.md"
  chmod 444 "$PROFILE/SOUL.md"
  cp "$src/config.yaml" "$PROFILE/config.yaml"
  cp "$src/jobs.json" "$PROFILE/cron/jobs.json"
  [ -f "$src/server.py" ] && cp "$src/server.py" "$APP/backend/server.py"
  [ -f "$src/external_data.py" ] && cp "$src/external_data.py" "$APP/backend/external_data.py"
  "$PY" "$SRC/imp04_refresh_cron_fingerprints.py" --apply
  systemctl --user restart "$UNIT"
  sleep 3
  systemctl --user is-active "$UNIT"
  echo "rolled back from $src"
  exit 0
fi

echo "profile: $PROFILE"
echo "bundle:  $SRC"
echo "app:     $APP"

if [ "$mode" != "--apply" ]; then
  echo
  echo "DRY RUN — would do:"
  echo "  1. back up SOUL.md, config.yaml, cron/jobs.json, backend/*.py -> $BACKUP"
  echo "  2. install $SRC/SOUL.md into the profile (mode 444)"
  echo "  3. add browser/file/delegation/session_search/image_gen/vision/tts/"
  echo "     todo/clarify to agent.disabled_toolsets in config.yaml"
  echo "  4. hermes cron edit --prompt for morning/evening/25/27"
  echo "  5. refresh trusted cron fingerprints (mapping stays 0600)"
  echo "  6. copy backend/server.py + backend/external_data.py into $APP"
  echo "  7. restart $UNIT"
  echo
  echo "current SOUL sha256:"
  sha256sum "$PROFILE/SOUL.md"
  echo "bundle SOUL sha256:"
  sha256sum "$SRC/SOUL.md"
  echo "fingerprint preview:"
  "$PY" "$SRC/imp04_refresh_cron_fingerprints.py" || true
  exit 0
fi

mkdir -p "$BACKUP"
cp "$PROFILE/SOUL.md" "$PROFILE/config.yaml" "$BACKUP/"
cp "$PROFILE/cron/jobs.json" "$BACKUP/"
cp "$APP/backend/server.py" "$APP/backend/external_data.py" "$BACKUP/"
echo "backed up to $BACKUP"

# 1. SOUL v2 (canonical LF bytes)
chmod 644 "$PROFILE/SOUL.md"
cp "$SRC/SOUL.md" "$PROFILE/SOUL.md"
chmod 444 "$PROFILE/SOUL.md"
sha256sum "$PROFILE/SOUL.md"

# 2. toolsets
"$PY" "$SRC/imp04_patch_config.py" "$PROFILE/config.yaml"

# 3. cron prompts (Oyijon-facing jobs only)
set_prompt() {  # $1 = job name, $2 = prompt file
  job_id="$("$PY" "$SRC/imp04_job_id.py" "$1")"
  echo "cron edit $1 -> $job_id"
  "$PY" -m hermes_cli.main --profile mariyam_oyijon cron edit "$job_id" \
    --prompt "$(cat "$SRC/cron/$2")"
}
set_prompt mariyam_daily_morning 06_morning.md
set_prompt mariyam_daily_evening 06_evening.md
set_prompt mariyam_plan_25_draft 25_draft.md
set_prompt mariyam_plan_27_reminder 27_reminder.md

# 4. trusted fingerprints must follow the prompt change
"$PY" "$SRC/imp04_refresh_cron_fingerprints.py" --apply

# 5. backend (news summary_ru + shorter tool descriptions)
cp "$SRC/backend/server.py" "$APP/backend/server.py"
cp "$SRC/backend/external_data.py" "$APP/backend/external_data.py"

# 6. restart gateway so config, SOUL and backend take effect
systemctl --user restart "$UNIT"
sleep 3
systemctl --user is-active "$UNIT"

echo "done. rollback: bash $SRC/imp04_deploy.sh --rollback $BACKUP"
