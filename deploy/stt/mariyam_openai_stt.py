#!/usr/bin/env python3
"""OpenAI transcription with a local faster-whisper fallback.

The command is intentionally profile-specific. It never prints the API key or
the transcript to logs. Hermes reads the transcript from ``--output``.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_MODELS = {
    "whisper-1",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
}
OPENAI_TIMEOUT_SECONDS = 25
OPENAI_MAX_RETRIES = 1
DEFAULT_ENV_FILE = Path(
    "/home/timeagent/.hermes/profiles/mariyam_oyijon/.env"
)
DEFAULT_AUDIT_FILE = Path(
    "/home/timeagent/.local/state/hermes-mariyam-stt/events.jsonl"
)
DEFAULT_PROMPT = (
    "Ўзбекча кундалик оилавий харажат ёки соғлиқ ҳақидаги аудиони фақат "
    "ўзбек кириллицасида кўчиринг. Айтилган сон ва суммани ўзгартирманг. "
    "Хоразм талаффузини ҳам ўзбекча ёзинг. Харажат луғати: озиқ-овқатда сут, "
    "коммунал тўловда сув, кийимда пойабзал. Тиббий шакллар: "
    "юрагим оғрияпти; кўкрагим оғрияпти; нафас олишим қийин; "
    "бошим айланяпти; ҳушим кетяпти; қон босимим жуда баланд; ёмон бўляпман."
)


def _read_private_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key

    env_path = Path(
        os.environ.get("MARIYAM_STT_ENV_FILE", str(DEFAULT_ENV_FILE))
    )
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "OPENAI_API_KEY":
            return value.strip().strip("'\"")
    return ""


def _extract_text(response: Any) -> str:
    if isinstance(response, dict):
        return str(response.get("text") or "").strip()
    return str(getattr(response, "text", "") or "").strip()


def _language_kwargs(language: str) -> dict[str, str]:
    """OpenAI currently rejects ISO code ``uz``; guide it via the prompt."""
    normalized = (language or "").strip().lower()
    if not normalized or normalized == "uz":
        return {}
    return {"language": normalized}


def transcribe_openai(
    input_path: Path,
    model: str,
    language: str,
) -> str:
    if model not in ALLOWED_MODELS:
        raise ValueError(f"unsupported OpenAI STT model: {model}")
    api_key = _read_private_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.openai.com/v1",
        timeout=OPENAI_TIMEOUT_SECONDS,
        max_retries=OPENAI_MAX_RETRIES,
    )
    try:
        with input_path.open("rb") as audio:
            response = client.audio.transcriptions.create(
                model=model,
                file=audio,
                prompt=os.environ.get("MARIYAM_STT_PROMPT", DEFAULT_PROMPT),
                response_format="json",
                temperature=0,
                **_language_kwargs(language),
            )
        text = _extract_text(response)
        if not text:
            raise RuntimeError("OpenAI STT returned an empty transcript")
        return text
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def transcribe_local(
    input_path: Path,
    language: str,
) -> str:
    from faster_whisper import WhisperModel

    model_name = os.environ.get(
        "MARIYAM_STT_FALLBACK_MODEL", "base"
    ).strip() or "base"
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(input_path),
        beam_size=5,
        language=language or "uz",
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    if not text:
        raise RuntimeError("local STT returned an empty transcript")
    return text


def _error_class(exc: BaseException) -> str:
    return type(exc).__name__[:80]


def _append_audit(event: dict[str, Any]) -> None:
    path = Path(
        os.environ.get("MARIYAM_STT_AUDIT_FILE", str(DEFAULT_AUDIT_FILE))
    )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=True) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def transcribe_with_fallback(
    input_path: Path,
    model: str,
    language: str,
) -> tuple[str, str, str | None]:
    try:
        return transcribe_openai(input_path, model, language), "openai", None
    except Exception as exc:
        return (
            transcribe_local(input_path, language),
            "local",
            _error_class(exc),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--model", choices=sorted(ALLOWED_MODELS), required=True
    )
    parser.add_argument("--language", default="uz")
    args = parser.parse_args()

    started = time.perf_counter()
    transcript, provider, fallback_reason = transcribe_with_fallback(
        args.input, args.model, args.language
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(transcript + "\n", encoding="utf-8")
    _append_audit(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "model": args.model if provider == "openai" else os.environ.get(
                "MARIYAM_STT_FALLBACK_MODEL", "base"
            ),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "fallback_reason": fallback_reason,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
