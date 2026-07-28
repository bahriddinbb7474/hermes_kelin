"""Append the imp04 disabled_toolsets to the live profile config.yaml.

Line-based edit: keeps every other line, comment and secret reference intact.
Idempotent — re-running does not duplicate entries.
"""
import pathlib
import sys

NEW = ["browser", "file", "delegation", "session_search", "image_gen",
       "vision", "tts", "todo", "clarify"]

path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()

start = None
for i, line in enumerate(lines):
    if line.strip() == "disabled_toolsets:":
        start = i
        break
if start is None:
    raise SystemExit("disabled_toolsets: not found")

indent = " " * (len(lines[start]) - len(lines[start].lstrip()))
end = start + 1
present = []
while end < len(lines) and lines[end].lstrip().startswith("- "):
    present.append(lines[end].lstrip()[2:].strip())
    end += 1

missing = [name for name in NEW if name not in present]
if not missing:
    print("already patched:", present)
    raise SystemExit(0)

insert = [f"{indent}- {name}" for name in missing]
lines[end:end] = insert
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("was:", present)
print("added:", missing)
