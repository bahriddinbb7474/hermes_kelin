#!/usr/bin/env bash
# imp01: deploy canonical SOUL.md (ac692b6e...) to profile mariyam_oyijon.
# Does NOT carry SOUL text itself: it verifies a file already delivered
# separately (see SOURCE below), then backs up, writes, verifies, restarts
# only the Mariyam gateway, and rolls back on any mismatch. Touches nothing
# belonging to Time-Agent.
set -euo pipefail

SOURCE="${SOURCE:-/tmp/imp01_soul_ac692b6e.md}"
PROFILE="${HERMES_HOME:-$HOME/.hermes/profiles/mariyam_oyijon}"
SOUL="$PROFILE/SOUL.md"
UNIT="hermes-gateway-mariyam_oyijon.service"
OLD_SHA_EXPECTED="f3377d9c0e032127cd5675408b525437a39b36ba9d148ab1f594e84c889aa679"
NEW_SHA_EXPECTED="ac692b6e3356c43cf0b174e87ce0f2580b1dac75360a156ca3168256707823e3"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$SOUL.bak.$STAMP"

sha() { sed 's/\r$//' "$1" | sha256sum | cut -d' ' -f1; }
run() { echo "+ $*"; "$@"; }

echo "== imp01: deploy SOUL ac692b6e =="
echo "source:  $SOURCE"
echo "target:  $SOUL"

if [ ! -f "$SOURCE" ]; then
  echo "ERROR: $SOURCE not found. Deliver it first (scp), then re-run. Nothing changed."
  exit 1
fi

source_sha="$(sha "$SOURCE")"
echo "delivered file sha256 (LF-normalized): $source_sha"
if [ "$source_sha" != "$NEW_SHA_EXPECTED" ]; then
  echo "STOP: delivered file is not the expected SOUL."
  echo "  expected: $NEW_SHA_EXPECTED"
  echo "  actual:   $source_sha"
  echo "Nothing changed."
  exit 1
fi

if [ ! -f "$SOUL" ]; then
  echo "ERROR: $SOUL not found. Nothing changed."
  exit 1
fi

current_sha="$(sha "$SOUL")"
echo "current SOUL sha256 (LF-normalized): $current_sha"

if [ "$current_sha" = "$NEW_SHA_EXPECTED" ]; then
  echo "already up to date ($NEW_SHA_EXPECTED). Nothing to do."
  exit 0
fi

if [ "$current_sha" != "$OLD_SHA_EXPECTED" ]; then
  echo "STOP: current SHA does not match the expected pre-deploy SHA."
  echo "  expected old: $OLD_SHA_EXPECTED"
  echo "  actual now:   $current_sha"
  echo "Nothing changed. Do not re-run until this is resolved."
  exit 1
fi

run cp "$SOUL" "$BACKUP"
run chmod 600 "$BACKUP"
echo "backup: $BACKUP"

run chmod 644 "$SOUL"
run cp "$SOURCE" "$SOUL"
run chmod 444 "$SOUL"

written_sha="$(sha "$SOUL")"
if [ "$written_sha" != "$NEW_SHA_EXPECTED" ]; then
  echo "!!! WRITE VERIFICATION FAILED !!!"
  echo "  expected: $NEW_SHA_EXPECTED"
  echo "  got:      $written_sha"
  echo "Restoring backup automatically..."
  run chmod 644 "$SOUL"
  run cp "$BACKUP" "$SOUL"
  run chmod 444 "$SOUL"
  echo "Backup restored, permissions returned to 0444. SOUL NOT deployed."
  exit 1
fi

run systemctl --user restart "$UNIT"
sleep 3
service_status="$(systemctl --user is-active "$UNIT" || true)"

echo "== done =="
echo "old sha:  $current_sha"
echo "new sha:  $written_sha"
echo "backup:   $BACKUP"
echo "service:  $UNIT = $service_status"
