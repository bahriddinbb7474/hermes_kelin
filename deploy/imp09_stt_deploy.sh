#!/usr/bin/env bash
# Controlled imp09 deploy: OpenAI STT with local fallback + recurring prompt.
set -euo pipefail

PROFILE="${HERMES_HOME:-$HOME/.hermes/profiles/mariyam_oyijon}"
SRC="${IMP09_SRC:-/tmp/imp09}"
APP="${MARIYAM_APP:-/opt/hermes-mariyam}"
PY="$HOME/.hermes/hermes-agent/venv/bin/python"
UNIT="hermes-gateway-mariyam_oyijon.service"
MODEL="${MARIYAM_STT_MODEL:-${2:-}}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$HOME/imp09-backup-$STAMP"
MODE="${1:-}"

case "$MODEL" in
  whisper-1|gpt-4o-transcribe|gpt-4o-mini-transcribe) ;;
  *) echo "MARIYAM_STT_MODEL must name an accepted benchmark model" >&2; exit 2 ;;
esac

if [ "$MODE" = "--rollback" ]; then
  backup="${3:?rollback needs a backup dir as argument 3}"
  chmod 644 "$PROFILE/SOUL.md"
  cp "$backup/SOUL.md" "$PROFILE/SOUL.md"
  chmod 444 "$PROFILE/SOUL.md"
  cp "$backup/config.yaml" "$PROFILE/config.yaml"
  if [ -f "$backup/mariyam_health_guard.py" ]; then
    install -m 644 "$backup/mariyam_health_guard.py" \
      "$PROFILE/plugins/mariyam_health_guard/__init__.py"
  fi
  if [ -f "$backup/mariyam_openai_stt.py" ]; then
    install -m 700 "$backup/mariyam_openai_stt.py" \
      "$APP/deploy/stt/mariyam_openai_stt.py"
  else
    rm -f "$APP/deploy/stt/mariyam_openai_stt.py"
  fi
  systemctl --user restart "$UNIT"
  sleep 4
  systemctl --user is-active "$UNIT"
  echo "rolled back from $backup"
  exit 0
fi

grep -q '^OPENAI_API_KEY=.' "$PROFILE/.env" || {
  echo "OPENAI_API_KEY is missing from private profile .env" >&2
  exit 3
}

if [ "$MODE" != "--apply" ]; then
  echo "DRY RUN"
  echo "profile: $PROFILE"
  echo "model:   $MODEL"
  echo "would install OpenAI->local STT wrapper, patch config/SOUL and restart $UNIT"
  exit 0
fi

mkdir -p "$BACKUP" "$APP/deploy/stt"
cp "$PROFILE/SOUL.md" "$PROFILE/config.yaml" "$BACKUP/"
cp "$PROFILE/plugins/mariyam_health_guard/__init__.py" \
  "$BACKUP/mariyam_health_guard.py"
if [ -f "$APP/deploy/stt/mariyam_openai_stt.py" ]; then
  cp "$APP/deploy/stt/mariyam_openai_stt.py" "$BACKUP/"
fi

install -m 700 "$SRC/deploy/stt/mariyam_openai_stt.py" \
  "$APP/deploy/stt/mariyam_openai_stt.py"
install -m 644 \
  "$SRC/deploy/hermes_plugins/mariyam_health_guard/__init__.py" \
  "$PROFILE/plugins/mariyam_health_guard/__init__.py"
chmod 644 "$PROFILE/SOUL.md"
cp "$SRC/deploy/hermes_profile_mariyam_oyijon/SOUL.md" "$PROFILE/SOUL.md"
chmod 444 "$PROFILE/SOUL.md"
"$PY" "$SRC/deploy/imp09_patch_stt_config.py" \
  "$PROFILE/config.yaml" --model "$MODEL"
install -d -m 700 "$HOME/.local/state/hermes-mariyam-stt"

systemctl --user restart "$UNIT"
sleep 4
systemctl --user is-active "$UNIT"
echo "deployed model=$MODEL"
echo "rollback: MARIYAM_STT_MODEL=$MODEL bash $SRC/deploy/imp09_stt_deploy.sh --rollback $MODEL $BACKUP"
