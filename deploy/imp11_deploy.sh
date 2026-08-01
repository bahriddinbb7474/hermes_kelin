#!/usr/bin/env bash
set -euo pipefail
umask 077

ACTION="${1:-preflight}"
SRC="${2:-/tmp/imp11}"
ROOT=/opt/hermes-mariyam
BACKEND="$ROOT/backend"
FAMILY="$HOME/.hermes/profiles/mariyam_oyijon"
TEST_PROFILE="$HOME/.hermes/profiles/mariyam_test"
DB_CONTAINER=hermes_mariyam_postgres
UNIT=hermes-gateway-mariyam_oyijon.service
PY="$ROOT/.venv/bin/python"
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
MARKER="$TEST_PROFILE/var/imp11-backup-path"

require_layout() {
  test -d "$BACKEND"
  test -d "$FAMILY"
  test -d "$TEST_PROFILE"
  test -x "$PY"
  test -x "$HERMES_PY"
  test "$(docker inspect -f '{{.State.Running}}' "$DB_CONTAINER")" = true
}

db_exec() {
  local database="$1"
  shift
  docker exec -i "$DB_CONTAINER" sh -c 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"' sh "$database" "$@"
}

install_backend() {
  install -m 0644 "$SRC/backend/db.py" "$BACKEND/db.py"
  install -m 0644 "$SRC/backend/external_data.py" "$BACKEND/external_data.py"
  install -m 0644 "$SRC/backend/server.py" "$BACKEND/server.py"
  install -m 0644 "$SRC/backend/sql/006_user_news_sources.sql" "$BACKEND/sql/006_user_news_sources.sql"
}

install_guard() {
  local profile="$1"
  local target="$profile/plugins/mariyam_identity_guard"
  mkdir -p "$target"
  install -m 0644 "$SRC/deploy/hermes_plugins/mariyam_identity_guard/__init__.py" "$target/__init__.py"
  install -m 0644 "$SRC/deploy/hermes_plugins/mariyam_identity_guard/plugin.yaml" "$target/plugin.yaml"
}

require_layout

case "$ACTION" in
  preflight)
    echo "layout=PASS"
    echo "gateway=$(systemctl --user is-active "$UNIT")"
    "$PY" -m py_compile "$BACKEND/db.py" "$BACKEND/external_data.py" "$BACKEND/server.py"
    echo "compile_current=PASS"
    ;;

  test)
    test -f "$SRC/backend/sql/006_user_news_sources.sql"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    backup="$FAMILY/backups/imp11-$stamp"
    mkdir -p "$backup/files" "$TEST_PROFILE/var"
    chmod 0700 "$backup"
    cp "$BACKEND/db.py" "$BACKEND/external_data.py" "$BACKEND/server.py" "$backup/files/"
    if test -d "$FAMILY/plugins/mariyam_identity_guard"; then
      cp -a "$FAMILY/plugins/mariyam_identity_guard" "$backup/files/identity_guard"
    fi
    docker exec "$DB_CONTAINER" sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$backup/database.dump"
    chmod 0600 "$backup/database.dump"
    sha256sum "$backup/database.dump" >"$backup/database.dump.sha256"
    printf '%s\n' "$backup" >"$MARKER"

    install_backend
    install_guard "$TEST_PROFILE"
    db_exec hermes_test <"$BACKEND/sql/006_user_news_sources.sql"
    "$PY" -m py_compile "$BACKEND/db.py" "$BACKEND/external_data.py" "$BACKEND/server.py" \
      "$TEST_PROFILE/plugins/mariyam_identity_guard/__init__.py"
    (cd "$ROOT" && APP_ENV=test "$PY" - <<'PY'
import asyncio
from backend import server
async def main():
    tools = await server.list_tools()
    assert len(tools) == len(server.TOOLS) == len(server.DISPATCH) == 30
    assert tools[-1].name == "manage_news_sources"
asyncio.run(main())
print("test_inventory=30/30/30")
PY
    )
    db_exec hermes_test <<'SQL'
SELECT CASE WHEN to_regclass('public.user_news_sources') IS NOT NULL
            THEN 'test_migration=PASS' ELSE 'test_migration=FAIL' END;
BEGIN;
DROP TABLE user_news_sources;
SELECT CASE WHEN to_regclass('public.user_news_sources') IS NULL
            THEN 'test_rollback=PASS' ELSE 'test_rollback=FAIL' END;
ROLLBACK;
SQL
    echo "backup=$backup"
    echo "test_stage=PASS"
    ;;

  family)
    test -s "$MARKER"
    backup="$(cat "$MARKER")"
    test -d "$backup"
    install_backend
    install_guard "$FAMILY"
    db_exec "${POSTGRES_DB:-hermes}" <"$BACKEND/sql/006_user_news_sources.sql"
    "$PY" -m py_compile "$BACKEND/db.py" "$BACKEND/external_data.py" "$BACKEND/server.py" \
      "$FAMILY/plugins/mariyam_identity_guard/__init__.py"
    "$HERMES_PY" -m hermes_cli.main --profile mariyam_oyijon config check
    systemctl --user restart "$UNIT"
    test "$(systemctl --user is-active "$UNIT")" = active
    echo "gateway=active"
    echo "backup=$backup"
    echo "family_stage=PASS"
    ;;

  verify)
    (cd "$ROOT" && "$PY" - <<'PY'
import asyncio
from backend import server
async def main():
    tools = await server.list_tools()
    print(f"inventory={len(tools)}/{len(server.TOOLS)}/{len(server.DISPATCH)}")
    print(f"last_tool={tools[-1].name}")
asyncio.run(main())
PY
    )
    db_exec hermes <<'SQL'
SELECT 'migration=' || CASE WHEN to_regclass('public.user_news_sources') IS NOT NULL
                            THEN 'PASS' ELSE 'FAIL' END;
SELECT 'family_custom_sources=' || count(*) FROM user_news_sources;
SQL
    grep -H '^version:' \
      "$FAMILY/plugins/mariyam_identity_guard/plugin.yaml" \
      "$FAMILY/plugins/mariyam_outbound_filter/plugin.yaml"
    grep -nE 'busy_ack_enabled|long_running_notifications|memory_notifications|tool_progress|session_reset|at_hour|notify:|fallback_providers|gpt-5.6-luna|openrouter|n1n' \
      "$FAMILY/config.yaml"
    systemctl --user show "$UNIT" \
      -p ActiveState -p SubState -p ExecMainStatus -p NRestarts --no-pager
    ;;

  bad-url)
    # This acceptance probe is deliberately isolated from the family profile.
    set -a
    source "$TEST_PROFILE/.env"
    set +a
    (cd "$ROOT" && APP_ENV=test "$PY" - <<'PY'
import asyncio
from backend import server

async def main():
    pool = await server.get_pool()
    try:
        user_id = await pool.fetchval(
            "SELECT id FROM users WHERE role = 'oyijon' ORDER BY created_at LIMIT 1"
        )
        if user_id is None:
            raise RuntimeError("mariyam_test has no Oyijon fixture")
        for url in ("http://example.com/feed", "http://127.0.0.1/feed"):
            result = await server.t_manage_news_sources(
                pool,
                {
                    "user_id": user_id,
                    "action": "add",
                    "url": url,
                    "display_name": "Синов хабарлари",
                    "topics": ["Синов"],
                    "added_by": "oyijon",
                },
            )
            assert result["ok"] is False
            print(f"bad_url={url} result=REJECTED message={result['message_uz']}")
    finally:
        await pool.close()

asyncio.run(main())
PY
    )
    ;;

  acceptance-db)
    db_exec hermes <<'SQL'
SELECT display_name, url, active,
       to_char(added_at AT TIME ZONE 'Asia/Tashkent', 'YYYY-MM-DD HH24:MI') AS added_local,
       array_to_string(topics, ',') AS topics, added_by
  FROM user_news_sources
 ORDER BY id;
SELECT count(*) AS alerts_since_acceptance,
       count(*) FILTER (WHERE sent_to_admin) AS admin_alerts_sent
  FROM alert_events
 WHERE created_at >= TIMESTAMPTZ '2026-08-01 23:25:00+00';
SQL
    ;;

  *)
    echo "usage: $0 preflight|test|family|verify|bad-url|acceptance-db [bundle-dir]" >&2
    exit 2
    ;;
esac
