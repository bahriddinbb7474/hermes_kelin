"""Hardened guard for destructive test database targets (Блок 6Ж).

Prevents `tests/run_tests.py` (which executes `TRUNCATE ... RESTART IDENTITY
CASCADE`) from ever running against the production database, even if it is
reachable via localhost / 127.0.0.1 and even if ALLOW_DESTRUCTIVE_TESTS=1 is set.

Rules (all must hold for a target to be allowed):
  1. DATABASE_URL is required.
  2. APP_ENV must be strictly 'test'.
  3. Database name must end with '_test'.
  4. Database name exactly 'hermes' is banned unconditionally.
  5. localhost / 127.0.0.1 alone are NOT proof of a test database.
  6. For a local *_test database: APP_ENV=test + '_test' suffix is sufficient.
  7. For a remote *_test database: ALLOW_DESTRUCTIVE_TESTS=1 is additionally
     required.
  8. ALLOW_DESTRUCTIVE_TESTS=1 cannot bypass rules 2, 3, or 4.
  9. The check happens BEFORE any connection / TRUNCATE.
 10. Error messages never contain DATABASE_URL, password, or username.

This module has NO dependency on the backend or any database driver.
"""
from urllib.parse import urlparse

# Hosts that are considered "local" (loopback). Local alone is NOT sufficient
# to mark a database as a test target (rule 5).
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

PRODUCTION_DB_NAME = "hermes"
TEST_DB_SUFFIX = "_test"


class DestructiveTestTargetError(Exception):
    """Raised when a destructive test target is refused.

    The message intentionally omits DATABASE_URL, password and username.
    Safe-to-log metadata is available via the attributes below.
    """

    def __init__(self, message: str, *, reason: str, db_name=None, local=None):
        super().__init__(message)
        self.reason = reason
        self.db_name = db_name
        self.local = local


class GuardResult:
    """Returned when a destructive test target is accepted."""

    def __init__(self, *, db_name: str, local: bool):
        self.db_name = db_name
        self.local = local

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"GuardResult(db_name={self.db_name!r}, local={self.local})"


def _parse_db_name(database_url: str):
    """Return (db_name, is_local) from a URL without leaking secrets.

    Does not raise on parse errors; returns (None, False) for unparsable input.
    """
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/") or None
    host = parsed.hostname  # None for unix-socket / relative URLs
    is_local = (host is None) or (host in LOCAL_HOSTS)
    return db_name, is_local


def validate_destructive_test_target(
    database_url: str,
    app_env: str | None,
    allow_remote: bool,
) -> GuardResult:
    """Validate that a destructive test may target `database_url`.

    Raises DestructiveTestTargetError if the target must not be used.
    Returns GuardResult if the target is accepted.

    Args:
        database_url: The configured DATABASE_URL (required).
        app_env: Value of APP_ENV. Must be exactly 'test'.
        allow_remote: Equivalent to ALLOW_DESTRUCTIVE_TESTS == '1'. Required for
            remote (non-loopback) test databases; never bypasses other rules.
    """
    # Rule 1: DATABASE_URL is required.
    if not database_url:
        raise DestructiveTestTargetError(
            "DATABASE_URL is not set; refusing destructive tests",
            reason="missing_url",
        )

    db_name, is_local = _parse_db_name(database_url)

    # Rule 2: APP_ENV must be strictly 'test'.
    if app_env != "test":
        raise DestructiveTestTargetError(
            "APP_ENV must be 'test' to run destructive tests; refusing target",
            reason="app_env_not_test",
            db_name=db_name,
            local=is_local,
        )

    # Rule 4: production database name 'hermes' is banned unconditionally.
    # Checked BEFORE allow_remote so the override can never bypass it (rule 8).
    if db_name == PRODUCTION_DB_NAME:
        raise DestructiveTestTargetError(
            "production database 'hermes' is forbidden for destructive tests",
            reason="prod_db_name",
            db_name=db_name,
            local=is_local,
        )

    # Rule 3: database name must end with '_test'.
    if not db_name or not db_name.endswith(TEST_DB_SUFFIX):
        raise DestructiveTestTargetError(
            "test database name must end with '_test'; refusing target",
            reason="bad_db_suffix",
            db_name=db_name,
            local=is_local,
        )

    # Rule 7/8: a remote test database also requires the explicit override.
    if not is_local and not allow_remote:
        raise DestructiveTestTargetError(
            "remote test database requires ALLOW_DESTRUCTIVE_TESTS=1",
            reason="remote_requires_override",
            db_name=db_name,
            local=False,
        )

    return GuardResult(db_name=db_name, local=is_local)
