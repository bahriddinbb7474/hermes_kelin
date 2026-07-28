"""Print the Hermes cron job id for a job name (imp04 deploy helper)."""

import json
import os
import sys
from pathlib import Path

PROFILE = Path(
    os.environ.get("HERMES_HOME")
    or Path.home() / ".hermes" / "profiles" / "mariyam_oyijon"
)
name = sys.argv[1]
raw = json.loads((PROFILE / "cron" / "jobs.json").read_text(encoding="utf-8"))
jobs = raw.get("jobs", raw)
if isinstance(jobs, dict):
    jobs = list(jobs.values())
matches = [job for job in jobs if isinstance(job, dict) and job.get("name") == name]
if len(matches) != 1:
    raise SystemExit(f"expected exactly one job named {name}, found {len(matches)}")
print(matches[0]["id"])
