"""Merge the imp05 profile keys into the live profile config.yaml.

Two idempotent, line-based edits (every other line, comment and secret
reference is preserved):

1. ``plugins.enabled`` gains ``mariyam_outbound_filter`` — the profile plugin
   that drops English framework status lines (provider-fallback notice).
2. A top-level ``session_reset`` block (daily rollover at 02:00 local, silent)
   so a memory write performed after a session started reaches the model on the
   next day instead of never (Hermes keeps one frozen memory snapshot per
   session; the default reset policy is "none").

Usage: python3 imp05_patch_config.py <path-to-config.yaml>
"""
import pathlib
import sys

PLUGIN = "mariyam_outbound_filter"
SESSION_RESET_BLOCK = [
    "",
    "# imp05-opus: Hermes stores one system prompt per session and injects",
    "# MEMORY.md / USER.md as a frozen snapshot taken when that prompt was",
    "# built, so memory written mid-session stays invisible. Default reset",
    "# policy is 'none' -> the snapshot never refreshes. Daily rollover at",
    "# 02:00 Asia/Tashkent (Oyijon asleep, no cron slot) fixes that; notify is",
    "# off because Hermes' auto-reset notice is English.",
    "session_reset:",
    "  mode: daily",
    "  at_hour: 2",
    "  notify: false",
]

path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
changed = []

# --- 1. plugins.enabled ---------------------------------------------------
start = None
for i, line in enumerate(lines):
    if line.rstrip() == "plugins:":
        start = i
        break
if start is None:
    raise SystemExit("plugins: section not found")

enabled = None
for i in range(start + 1, len(lines)):
    stripped = lines[i].strip()
    if not stripped or stripped.startswith("#"):
        continue
    if not lines[i].startswith(" "):  # left the plugins block
        break
    if stripped == "enabled:":
        enabled = i
        break
if enabled is None:
    raise SystemExit("plugins.enabled not found")

end = enabled + 1
present = []
while end < len(lines) and lines[end].lstrip().startswith("- "):
    present.append(lines[end].lstrip()[2:].strip())
    end += 1

if PLUGIN in present:
    print("plugins.enabled already patched:", present)
else:
    indent = " " * (len(lines[end - 1]) - len(lines[end - 1].lstrip()))
    lines.insert(end, f"{indent}- {PLUGIN}")
    changed.append(f"plugins.enabled += {PLUGIN}")
    print("plugins.enabled was:", present)

# --- 2. session_reset -----------------------------------------------------
if any(line.rstrip() == "session_reset:" for line in lines):
    print("session_reset already present")
else:
    lines.extend(SESSION_RESET_BLOCK)
    changed.append("session_reset: daily/02:00/notify=false")

if not changed:
    raise SystemExit(0)

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("applied:", "; ".join(changed))
