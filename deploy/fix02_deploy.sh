#!/usr/bin/env bash
# Controlled fix02 deploy: day rhythm, prayer no-agent jobs, news and quiet gate.
set -euo pipefail

PROFILE="${HERMES_HOME:-$HOME/.hermes/profiles/mariyam_oyijon}"
SRC="${FIX02_SRC:-/tmp/fix02}"
APP="${MARIYAM_APP:-/opt/hermes-mariyam}"
PY="$HOME/.hermes/hermes-agent/venv/bin/python"
UNIT="hermes-gateway-mariyam_oyijon.service"
PRAYER_TIMER="mariyam-prayer-scheduler.timer"
PRAYER_SERVICE="mariyam-prayer-scheduler.service"
MAP_PATH="${MARIYAM_CRON_IDENTITY_MAP_FILE:-/opt/hermes-mariyam-secrets/cron-identity-map.json}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$HOME/fix02-backup-$STAMP"
MODE="${1:-}"

job_id() {
  "$PY" "$SRC/deploy/imp04_job_id.py" "$1"
}

if [ "$MODE" = "--rollback" ]; then
  backup="${2:?rollback needs a backup dir}"
  systemctl --user disable --now "$PRAYER_TIMER" >/dev/null 2>&1 || true
  systemctl --user stop "$UNIT"
  cp "$backup/jobs.json" "$PROFILE/cron/jobs.json"
  install -m 600 "$backup/cron-identity-map.json" "$MAP_PATH"
  chmod 644 "$PROFILE/SOUL.md"
  cp "$backup/SOUL.md" "$PROFILE/SOUL.md"
  chmod 444 "$PROFILE/SOUL.md"
  install -m 644 "$backup/mariyam_cron_reliability.py" \
    "$PROFILE/plugins/mariyam_cron_reliability/__init__.py"
  install -m 644 "$backup/plugin.yaml" \
    "$PROFILE/plugins/mariyam_cron_reliability/plugin.yaml"
  cp "$backup/server.py" "$APP/backend/server.py"
  cp "$backup/external_data.py" "$APP/backend/external_data.py"
  if [ -f "$backup/news_sources.json" ]; then
    cp "$backup/news_sources.json" "$APP/backend/news_sources.json"
  else
    rm -f "$APP/backend/news_sources.json"
  fi
  cp "$backup/cron_watchdog_jobs.json" \
    "$APP/deploy/watchdog/cron_watchdog_jobs.json"
  rm -rf "$PROFILE/scripts/day_rhythm"
  if [ -d "$backup/profile-day-rhythm" ]; then
    cp -a "$backup/profile-day-rhythm" "$PROFILE/scripts/day_rhythm"
  fi
  for unit in "$PRAYER_SERVICE" "$PRAYER_TIMER"; do
    if [ -f "$backup/$unit" ]; then
      cp "$backup/$unit" "$HOME/.config/systemd/user/$unit"
    else
      rm -f "$HOME/.config/systemd/user/$unit"
    fi
  done
  systemctl --user daemon-reload
  systemctl --user start "$UNIT"
  sleep 4
  systemctl --user is-active "$UNIT"
  echo "rolled back from $backup"
  exit 0
fi

if [ "$MODE" != "--apply" ]; then
  echo "DRY RUN"
  echo "profile: $PROFILE"
  echo "bundle:  $SRC"
  echo "would back up runtime/jobs/private fingerprints, install fix02,"
  echo "edit morning to 08:00 + evening prompt, refresh fingerprints,"
  echo "enable prayer scheduler, restart gateway and create no-agent one-shots"
  exit 0
fi

install -d -m 700 "$BACKUP"
cp "$PROFILE/SOUL.md" "$PROFILE/cron/jobs.json" "$BACKUP/"
cp "$PROFILE/plugins/mariyam_cron_reliability/__init__.py" \
  "$BACKUP/mariyam_cron_reliability.py"
cp "$PROFILE/plugins/mariyam_cron_reliability/plugin.yaml" "$BACKUP/plugin.yaml"
cp "$APP/backend/server.py" "$APP/backend/external_data.py" "$BACKUP/"
[ ! -f "$APP/backend/news_sources.json" ] || \
  cp "$APP/backend/news_sources.json" "$BACKUP/"
cp "$APP/deploy/watchdog/cron_watchdog_jobs.json" "$BACKUP/"
install -m 600 "$MAP_PATH" "$BACKUP/cron-identity-map.json"
[ ! -d "$PROFILE/scripts/day_rhythm" ] || \
  cp -a "$PROFILE/scripts/day_rhythm" "$BACKUP/profile-day-rhythm"
for unit in "$PRAYER_SERVICE" "$PRAYER_TIMER"; do
  [ ! -f "$HOME/.config/systemd/user/$unit" ] || \
    cp "$HOME/.config/systemd/user/$unit" "$BACKUP/$unit"
done

systemctl --user stop "$UNIT"

install -d -m 755 "$APP/deploy/day_rhythm"
install -m 700 "$SRC/deploy/day_rhythm/mariyam-prayer-scheduler.py" \
  "$APP/deploy/day_rhythm/mariyam-prayer-scheduler.py"
install -m 644 "$SRC/deploy/day_rhythm/mariyam_day_rhythm.py" \
  "$APP/deploy/day_rhythm/mariyam_day_rhythm.py"
install -m 644 "$SRC/deploy/day_rhythm/$PRAYER_SERVICE" \
  "$HOME/.config/systemd/user/$PRAYER_SERVICE"
install -m 644 "$SRC/deploy/day_rhythm/$PRAYER_TIMER" \
  "$HOME/.config/systemd/user/$PRAYER_TIMER"

install -d -m 700 "$PROFILE/scripts/day_rhythm/reminders"
printf '' >"$PROFILE/scripts/day_rhythm/__init__.py"
chmod 600 "$PROFILE/scripts/day_rhythm/__init__.py"
install -m 600 "$SRC/deploy/day_rhythm/mariyam_day_rhythm.py" \
  "$PROFILE/scripts/day_rhythm/mariyam_day_rhythm.py"
install -d -m 700 "$APP/var/day-rhythm"

cp "$SRC/backend/server.py" "$APP/backend/server.py"
cp "$SRC/backend/external_data.py" "$APP/backend/external_data.py"
cp "$SRC/backend/news_sources.json" "$APP/backend/news_sources.json"
install -m 644 \
  "$SRC/deploy/hermes_plugins/mariyam_cron_reliability/__init__.py" \
  "$PROFILE/plugins/mariyam_cron_reliability/__init__.py"
install -m 644 \
  "$SRC/deploy/hermes_plugins/mariyam_cron_reliability/plugin.yaml" \
  "$PROFILE/plugins/mariyam_cron_reliability/plugin.yaml"
cp "$SRC/deploy/watchdog/cron_watchdog_jobs.json" \
  "$APP/deploy/watchdog/cron_watchdog_jobs.json"
chmod 644 "$PROFILE/SOUL.md"
cp "$SRC/deploy/hermes_profile_mariyam_oyijon/SOUL.md" "$PROFILE/SOUL.md"
chmod 444 "$PROFILE/SOUL.md"

morning_id="$(job_id mariyam_daily_morning)"
"$PY" -m hermes_cli.main --profile mariyam_oyijon cron edit "$morning_id" \
  --schedule "0 8 * * *" \
  --prompt "$(cat "$SRC/deploy/hermes_profile_mariyam_oyijon/cron/06_morning.md")"
evening_id="$(job_id mariyam_daily_evening)"
"$PY" -m hermes_cli.main --profile mariyam_oyijon cron edit "$evening_id" \
  --prompt "$(cat "$SRC/deploy/hermes_profile_mariyam_oyijon/cron/06_evening.md")"
"$PY" "$SRC/deploy/imp04_refresh_cron_fingerprints.py" --apply

systemctl --user daemon-reload
systemctl --user enable --now "$PRAYER_TIMER"
systemctl --user start "$UNIT"
sleep 4
systemctl --user is-active "$UNIT"
systemctl --user start "$PRAYER_SERVICE"
systemctl --user is-active "$PRAYER_TIMER"
echo "deployed; rollback: bash $SRC/deploy/fix02_deploy.sh --rollback $BACKUP"
