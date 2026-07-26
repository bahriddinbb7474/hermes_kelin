#!/usr/bin/env bash
set -euo pipefail
umask 077
readonly APP_ROOT="${APP_ROOT:-/opt/hermes-mariyam}"
readonly SECRETS_DIR="${SECRETS_DIR:-/opt/hermes-mariyam-secrets}"
readonly STATE_DIR="${STATE_DIR:-$APP_ROOT/var/backup}"
readonly RCLONE_BIN="${RCLONE_BIN:-/home/timeagent/.local/bin/rclone}"
readonly REMOTE="${BACKUP_RCLONE_REMOTE:-hermes_mariyam_gdrive}"
readonly REMOTE_DIR="${BACKUP_RCLONE_DIR:-hermes-mariyam-backups}"
readonly DB_CONTAINER="${BACKUP_DB_CONTAINER:-hermes_mariyam_postgres}"
readonly PASSPHRASE_FILE="$SECRETS_DIR/backup-gpg-passphrase"
archive="${1:-$(python3 -c 'import json; print(json.load(open("/opt/hermes-mariyam/var/backup/last-backup.json"))["archive"])')}"
[[ "$archive" =~ ^mariyam_[0-9TZ-]+\.tar\.gz\.gpg$ ]] || { echo "invalid archive name" >&2; exit 2; }
workdir="$(mktemp -d "$STATE_DIR/restore.XXXXXX")"
restore_container="mariyam_restore_check_$$"
cleanup() {
  [[ "$restore_container" == mariyam_restore_check_* ]] && docker rm -f "$restore_container" >/dev/null 2>&1 || true
  [[ "$workdir" == "$STATE_DIR"/restore.* ]] && rm -rf -- "$workdir"
}
trap cleanup EXIT
"$RCLONE_BIN" copyto "$REMOTE:$REMOTE_DIR/$archive" "$workdir/$archive"
install -d -m 700 "$workdir/gnupg" "$workdir/files"
GNUPGHOME="$workdir/gnupg" gpg --batch --yes --decrypt --passphrase-file "$PASSPHRASE_FILE" --output "$workdir/payload.tar.gz" "$workdir/$archive"
tar -C "$workdir" -xzf "$workdir/payload.tar.gz"
tar -C "$workdir/files" -xzf "$workdir/profile-state.tar.gz"
test -s "$workdir/files/home/timeagent/.hermes/profiles/mariyam_oyijon/config.yaml"
test -s "$workdir/files/home/timeagent/.hermes/profiles/mariyam_oyijon/SOUL.md"
test -s "$workdir/files/opt/hermes-mariyam-secrets/backend.env"
image="$(docker inspect --format '{{.Config.Image}}' "$DB_CONTAINER")"
password="$(openssl rand -hex 24)"
docker run -d --name "$restore_container" -e POSTGRES_PASSWORD="$password" -e POSTGRES_DB=mariyam_restore_check "$image" >/dev/null
for _ in $(seq 1 60); do docker exec "$restore_container" pg_isready -U postgres -d mariyam_restore_check >/dev/null 2>&1 && break; sleep 1; done
docker exec "$restore_container" pg_isready -U postgres -d mariyam_restore_check >/dev/null
docker cp "$workdir/database.dump" "$restore_container:/tmp/database.dump" >/dev/null
docker exec "$restore_container" pg_restore -U postgres -d mariyam_restore_check --no-owner --no-privileges /tmp/database.dump
docker exec -i "$restore_container" psql -U postgres -d mariyam_restore_check -At >"$workdir/restored-manifest.json" <<'SQL'
SELECT json_build_object(
  'tables', json_build_object(
    'alert_events', (SELECT count(*) FROM alert_events), 'expense_categories', (SELECT count(*) FROM expense_categories),
    'health_notes', (SELECT count(*) FROM health_notes), 'monthly_budget_items', (SELECT count(*) FROM monthly_budget_items),
    'monthly_budget_plans', (SELECT count(*) FROM monthly_budget_plans), 'monthly_plan_cycles', (SELECT count(*) FROM monthly_plan_cycles),
    'plan_notes', (SELECT count(*) FROM plan_notes), 'quran_progress', (SELECT count(*) FROM quran_progress),
    'transactions', (SELECT count(*) FROM transactions), 'usage_costs', (SELECT count(*) FROM usage_costs),
    'users', (SELECT count(*) FROM users)),
  'known_expense', (SELECT json_build_object('id', id, 'amount', amount, 'currency', currency)
    FROM transactions WHERE type = 'expense' ORDER BY id LIMIT 1));
SQL
python3 - "$workdir/manifest.json" "$workdir/restored-manifest.json" <<'PY'
import json, sys
expected, actual = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:])
if expected != actual:
    raise SystemExit(f"restore mismatch: expected={expected} actual={actual}")
print(json.dumps({"ok": True, **actual}, ensure_ascii=False))
PY
