"""Install the profile-specific OpenAI→local STT command provider.

This is a line-based replacement so unrelated config and comments remain
untouched. Secrets stay in the private profile ``.env`` and are never written
to config.yaml.
"""

from __future__ import annotations

import argparse
from pathlib import Path


ALLOWED_MODELS = {
    "whisper-1",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
}


def stt_block(model: str) -> list[str]:
    return [
        "stt:",
        "  enabled: true",
        "  echo_transcripts: false",
        "  provider: mariyam_openai_fallback",
        "  providers:",
        "    mariyam_openai_fallback:",
        "      type: command",
        "      command: >-",
        "        /home/timeagent/.hermes/hermes-agent/venv/bin/python",
        "        /opt/hermes-mariyam/deploy/stt/mariyam_openai_stt.py",
        "        --input {input_path} --output {output_path}",
        "        --model {model} --language {language}",
        f"      model: {model}",
        "      language: uz",
        "      format: txt",
        "      timeout: 120",
    ]


def replace_top_level_block(lines: list[str], key: str, block: list[str]) -> list[str]:
    start = next(
        (index for index, line in enumerate(lines) if line == f"{key}:"),
        None,
    )
    if start is None:
        result = list(lines)
        if result and result[-1] != "":
            result.append("")
        result.extend(block)
        return result

    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line and not line.startswith((" ", "\t", "#")):
            break
        end += 1
    return lines[:start] + block + lines[end:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--model", choices=sorted(ALLOWED_MODELS), required=True)
    args = parser.parse_args()

    lines = args.config.read_text(encoding="utf-8").splitlines()
    updated = replace_top_level_block(lines, "stt", stt_block(args.model))
    args.config.write_text("\n".join(updated) + "\n", encoding="utf-8")
    print(f"configured OpenAI STT model: {args.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
