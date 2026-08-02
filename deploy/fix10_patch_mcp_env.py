#!/usr/bin/env python3
"""Add the OpenWeather env placeholder to Mariyam's MCP server, preserving YAML."""
from __future__ import annotations

import argparse
import copy
import os
import re
import tempfile
from pathlib import Path

import yaml


PLACEHOLDER = "${OPENWEATHER_API_KEY}"
ANCHOR = re.compile(r"^(?P<indent>\s*)DATABASE_URL:\s*\$\{DATABASE_URL\}\s*$")


def patch_config(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    before = yaml.safe_load(raw)
    env = before["mcp_servers"]["mariyam_backend"]["env"]
    existing = env.get("OPENWEATHER_API_KEY")
    if existing == PLACEHOLDER:
        return False
    if existing is not None:
        raise ValueError("OPENWEATHER_API_KEY must remain an environment placeholder")

    lines = raw.splitlines(keepends=True)
    anchors = [(index, ANCHOR.fullmatch(line.rstrip("\r\n"))) for index, line in enumerate(lines)]
    anchors = [(index, match) for index, match in anchors if match]
    if len(anchors) != 1:
        raise ValueError("expected exactly one DATABASE_URL placeholder anchor")
    index, match = anchors[0]
    newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines.insert(index + 1, f"{match.group('indent')}OPENWEATHER_API_KEY: {PLACEHOLDER}{newline}")
    updated = "".join(lines)

    after = yaml.safe_load(updated)
    expected = copy.deepcopy(before)
    expected["mcp_servers"]["mariyam_backend"]["env"]["OPENWEATHER_API_KEY"] = PLACEHOLDER
    if after != expected:
        raise ValueError("refusing a config change outside the MCP env placeholder")

    mode = path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        handle.write(updated)
        temp_path = Path(handle.name)
    try:
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    print("changed=" + str(patch_config(args.config)).lower())


if __name__ == "__main__":
    main()
