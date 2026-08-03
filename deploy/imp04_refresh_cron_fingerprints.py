"""Recompute trusted cron fingerprints after a prompt change (imp04).

Runs on the VPS as the profile service user. Reads the live `cron/jobs.json`
and the private cron identity mapping, recomputes `job_fingerprint_sha256`
and `prompt_sha256` for every job already present in the mapping using the
guard's own canonicalisation, and writes the mapping back atomically with
mode 0600.

It never adds, removes or re-scopes a mapping entry: only the two hashes of
already-trusted jobs are refreshed. Any job id in the mapping that is missing
from jobs.json aborts the run.

Usage:
    python3 imp04_refresh_cron_fingerprints.py [--apply|--check]

Without a flag it only prints what would change (dry run, always exit 0).
``--check`` writes nothing and exits 1 if any trusted job would be refused by
the guard — that is the form deploy scripts use as a gate, so a forgotten
refresh fails the deploy instead of silently disarming a cron job (fix04).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

PROFILE = Path(
    os.environ.get("HERMES_HOME")
    or Path.home() / ".hermes" / "profiles" / "mariyam_oyijon"
)
JOBS = PROFILE / "cron" / "jobs.json"
GUARD = PROFILE / "plugins" / "mariyam_identity_guard" / "__init__.py"
MAP_PATH = Path(
    os.environ.get("MARIYAM_CRON_IDENTITY_MAP_FILE")
    or "/opt/hermes-mariyam-secrets/cron-identity-map.json"
)


def _load_guard():
    spec = importlib.util.spec_from_file_location("mariyam_identity_guard_fp", GUARD)
    if not spec or not spec.loader:
        raise SystemExit(f"cannot load guard module from {GUARD}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    flags = sys.argv[1:]
    apply = "--apply" in flags
    check = "--check" in flags
    if apply and check:
        raise SystemExit("--apply and --check are mutually exclusive")
    guard = _load_guard()

    jobs_raw = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = jobs_raw.get("jobs", jobs_raw)
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    by_id = {str(job.get("id")): job for job in jobs if isinstance(job, dict)}

    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    entries = mapping.get("jobs") or {}

    changes = []
    for job_id, entry in entries.items():
        job = by_id.get(job_id)
        if job is None:
            raise SystemExit(f"mapping job {job_id} is missing from {JOBS}")
        prompt = job.get("prompt") or ""
        new_fp = guard.cron_job_fingerprint(job)
        new_prompt = guard._sha256_text(prompt)
        if (
            new_fp != entry.get("job_fingerprint_sha256")
            or new_prompt != entry.get("prompt_sha256")
        ):
            changes.append((job_id, job.get("name"), entry.get("purpose")))
            entry["job_fingerprint_sha256"] = new_fp
            entry["prompt_sha256"] = new_prompt

    if not changes:
        print(f"fingerprints already current; {len(entries)} trusted job(s) verified")
        return 0

    for job_id, name, purpose in changes:
        print(f"refresh {job_id}  name={name}  purpose={purpose}")

    if check:
        print(
            f"\nFAIL: {len(changes)} trusted job(s) would be refused by the guard.\n"
            "Run this script with --apply (the cron identity map is stale after any\n"
            "change to a job prompt, schedule or delivery target)."
        )
        return 1

    if not apply:
        print(f"\n{len(changes)} entr(y|ies) would change; re-run with --apply")
        return 0

    payload = json.dumps(mapping, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    directory = MAP_PATH.parent
    old_umask = os.umask(0o077)
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, delete=False
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, MAP_PATH)
    finally:
        os.umask(old_umask)
    print(f"\nwrote {MAP_PATH} (mode 0600), {len(changes)} entr(y|ies) refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
