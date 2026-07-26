#!/usr/bin/env bash
# Encrypted, read-only production backup.  Install outside git at /opt/hermes-mariyam/.
set -euo pipefail
umask 077

readonly APP_ROOT="${APP_ROOT:-/opt/hermes-mariyam}"
readonly SECRETS_DIR="${SECRETS_DIR:-/opt/hermes-mariyam-secrets}"
readonly STATE_DIR="${STATE_DIR:-$APP_ROOT/var/backup}"
readonly RCLONE_BIN="${RCLONE_BIN:-/home/timeagent/.local/bin/rclone}"
readonly REMOTE="${BACKUP_RCLONE_REMOTE:-hermes_mariyam_gdrive}"
readonly REMOTE_DIR="${BACKUP_RCLONE_DIR:-hermes-mariyam-backups}"
readonly KEEP_COUNT="${BACKUP_KEEP_COUNT:-30}"
readonly DB_CONTAINER="${BACKUP_DB_CONTAINER:-hermes_mariyam_postgres}"
readonly PASSPHRASE_FILE="$SECRETS_DIR/backup-gpg-passphrase"

write_manifest() {
  local container="$1" output="$2"
  /usr/bin/docker exec -i "$container" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' >"$output" <<'SQL'
SELECT json_build_object(
  'tables', json_build_object(
    'alert_events', (SELECT count(*) FROM alert_events), 'expense_categories', (SELECT count(*) FROM expense_categories),
    'health_notes', (SELECT count(*) FROM health_notes), 'monthly_budget_items', (SELECT count(*) FROM monthly_budget_items),
    'monthly_budget_plans', (SELECT count(*) FROM monthly_budget_plans), 'monthly_plan_cycles', (SELECT count(*) FROM monthly_plan_cycles),
    'plan_notes', (SELECT count(*) FROM plan_notes), 'quran_progress', (SELECT count(*) FROM quran_progress),
    'recurring_obligations', (SELECT count(*) FROM recurring_obligations),
    'transactions', (SELECT count(*) FROM transactions), 'usage_costs', (SELECT count(*) FROM usage_costs),
    'users', (SELECT count(*) FROM users)),
  'known_expense', (SELECT json_build_object('id', id, 'amount', amount, 'currency', currency)
    FROM transactions WHERE type = 'expense' ORDER BY id LIMIT 1));
SQL
}

for required in "$RCLONE_BIN" /usr/bin/gpg /usr/bin/docker "$PASSPHRASE_FILE"; do
  [[ -x "$required" || -r "$required" ]] || { echo "missing required backup dependency" >&2; exit 1; }
done
[[ "$KEEP_COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "BACKUP_KEEP_COUNT must be positive" >&2; exit 1; }

install -d -m 700 "$STATE_DIR"
workdir="$(mktemp -d "$STATE_DIR/work.XXXXXX")"
cleanup() {
  [[ "$workdir" == "$STATE_DIR"/work.* ]] && rm -rf -- "$workdir"
}
trap cleanup EXIT
stamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
name="mariyam_${stamp}.tar.gz.gpg"
archive="$workdir/$name"

# No SQL writes: pg_dump runs in the isolated PostgreSQL container.
/usr/bin/docker exec "$DB_CONTAINER" sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$workdir/database.dump"
write_manifest "$DB_CONTAINER" "$workdir/manifest.json"

# These paths contain the canonical profile state and its encrypted-at-rest secrets.
/usr/bin/tar -C / -czf "$workdir/profile-state.tar.gz" \
  opt/hermes-mariyam-secrets \
  home/timeagent/.hermes/profiles/mariyam_oyijon/config.yaml \
  home/timeagent/.hermes/profiles/mariyam_oyijon/SOUL.md
/usr/bin/tar -C "$workdir" -czf "$workdir/payload.tar.gz" database.dump manifest.json profile-state.tar.gz
install -d -m 700 "$workdir/gnupg"
GNUPGHOME="$workdir/gnupg" /usr/bin/gpg --batch --yes --symmetric --cipher-algo AES256 \
  --passphrase-file "$PASSPHRASE_FILE" --output "$archive" "$workdir/payload.tar.gz"

sha256="$(sha256sum "$archive" | awk '{print $1}')"
"$RCLONE_BIN" copyto "$archive" "$REMOTE:$REMOTE_DIR/$name"
"$RCLONE_BIN" lsf "$REMOTE:$REMOTE_DIR" --files-only | sort -r | tail -n +$((KEEP_COUNT + 1)) | \
  while IFS= read -r old; do "$RCLONE_BIN" deletefile "$REMOTE:$REMOTE_DIR/$old"; done

printf '{"ok":true,"archive":"%s","uploaded_at":"%s","sha256":"%s","remote":"%s"}\n' \
  "$name" "$(date -u +%FT%TZ)" "$sha256" "$REMOTE" >"$STATE_DIR/last-backup.json"
