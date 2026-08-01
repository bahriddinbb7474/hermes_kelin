# fix02 — report

## Done

- Added a regression test that checks the installed Hermes `gateway.run` module
  still exports `_prepare_gateway_status_message`.
- The test skips when Hermes is not installed locally and fails with an
  actionable message when the installed module no longer has the hook.
- Moved Mariyam's daily session reset from 04:00 to 02:00 Asia/Tashkent.
- Updated the same hour in `deploy/imp05_patch_config.py`; `mode: daily` and
  `notify: false` are unchanged.
- The outbound-filter implementation itself was not changed.

## New regression test

```python
def _installed_hermes_root() -> Path | None:
    configured = os.environ.get("MARIYAM_HERMES_PYTHON")
    roots = []
    if configured:
        candidate = Path(configured)
        if not candidate.is_file():
            return None
        roots.append(candidate.parents[2])
    else:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            roots.append(Path(local_appdata) / "hermes" / "hermes-agent")
        roots.append(Path.home() / ".hermes" / "hermes-agent")

    for root in roots:
        if (root / "gateway" / "run.py").is_file():
            return root
    return None


def test_installed_hermes_gateway_exposes_status_hook(tmp_path):
    """Catch a Hermes upgrade that silently disables the profile filter."""
    hermes_root = _installed_hermes_root()
    if hermes_root is None:
        pytest.skip("Hermes runtime is not installed locally")

    site_packages = hermes_root / "venv" / "Lib" / "site-packages"
    if not site_packages.is_dir():
        site_packages = (
            hermes_root
            / "venv"
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        str(path)
        for path in (hermes_root, site_packages)
        if path.is_dir()
    )
    env["HERMES_HOME"] = str(tmp_path / "hermes-home")
    probe = (
        "import importlib; "
        "module = importlib.import_module('gateway.run'); "
        "print(hasattr(module, '_prepare_gateway_status_message'))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, (
        "Installed Hermes could not import gateway.run: "
        f"{completed.stderr.strip()}"
    )
    assert completed.stdout.strip().splitlines()[-1:] == ["True"], (
        "Installed Hermes gateway.run no longer exposes "
        "_prepare_gateway_status_message; update mariyam_outbound_filter "
        "to use the new status hook"
    )
```

## Changed files

- `deploy/hermes_profile_mariyam_oyijon/config.skill-protect.snippet.yaml`
- `deploy/imp05_patch_config.py`
- `tests/test_mariyam_skill_protection.py`
- `tasks/luna/fix02.report.md`

## Verification

- Targeted: `39 passed` in `tests/test_mariyam_skill_protection.py`.
- `py_compile`: passed for the changed Python files.
- `git diff --check`: passed.
- Full `pytest -q` could not complete in this Windows environment: collection
  stopped on 11 tests because the available Python 3.12 interpreter cannot
  load the Python 3.11 `asyncpg` binary from the local Hermes environment.
  Affected tests: `test_backup_status.py`, `test_mariyam_effective_prompt.py`,
  `test_stage51_expense_analytics.py`, `test_stage51_monthly_budget.py`,
  `test_stage53_product_plans.py`, `test_stage53a_approval_cycle.py`,
  `test_stage53a_get_cycle.py`, `test_stage53a_open_cycle.py`,
  `test_stage6_daily_life.py`, `test_stage6_recurring_obligations.py`, and
  `test_stage7_admin_report.py`.
- Remaining suite with those 11 collection blockers excluded: `257 passed`.

## Commit

- Implementation commit: `fec7ed9`
- Message: `test: guard outbound filter hook, move session reset to 02:00`
- Push to `origin/main`: pending at report creation.

## Live configuration reminder

After push, update the live file separately:
`~/.hermes/profiles/mariyam_oyijon/config.yaml` must also have
`session_reset.at_hour: 2`; repository changes do not modify the VPS.
