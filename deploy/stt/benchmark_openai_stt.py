#!/usr/bin/env python3
"""Reproducible imp09 benchmark for OpenAI transcription candidates.

Raw real-voice transcripts are written only to the operator-selected private
output directory. The generated summary contains aggregates, not transcripts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from mariyam_openai_stt import (
    ALLOWED_MODELS,
    DEFAULT_PROMPT,
    _read_private_key,
)


TOKEN_PRICES_PER_MILLION = {
    "gpt-4o-transcribe": (2.50, 10.00),
    "gpt-4o-mini-transcribe": (1.25, 5.00),
}
WHISPER_PRICE_PER_MINUTE = 0.006


def duration_seconds(path: Path) -> float:
    import av

    with av.open(str(path)) as container:
        if container.duration is not None:
            return float(container.duration / av.time_base)
        audio_stream = next(
            stream for stream in container.streams if stream.type == "audio"
        )
        if audio_stream.duration is None or audio_stream.time_base is None:
            raise RuntimeError(f"audio duration unavailable: {path.name}")
        return float(audio_stream.duration * audio_stream.time_base)


def usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {
        key: getattr(usage, key)
        for key in ("input_tokens", "output_tokens", "total_tokens")
        if getattr(usage, key, None) is not None
    }


def estimate_cost(model: str, duration: float, usage: dict[str, Any]) -> float:
    if model == "whisper-1":
        return duration / 60 * WHISPER_PRICE_PER_MINUTE
    input_price, output_price = TOKEN_PRICES_PER_MILLION[model]
    input_tokens = float(usage.get("input_tokens") or 0)
    output_tokens = float(usage.get("output_tokens") or 0)
    return (
        input_tokens * input_price + output_tokens * output_price
    ) / 1_000_000


def load_detector(plugin: Path | None) -> Callable[[str], str | None]:
    if plugin is None:
        return lambda _text: None
    spec = importlib.util.spec_from_file_location(
        "imp09_health_guard_benchmark", plugin
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load health guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.detect_health_keyword


def load_manifest(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_samples(root: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    real_dir = root / "data" / "voice-samples"
    for index, path in enumerate(sorted(real_dir.glob("*.ogg")), start=1):
        samples.append(
            {
                "dataset": "real",
                "index": index,
                "path": path,
                "gold": None,
            }
        )

    proxy_dir = root / ".imp09_proxy_voice"
    proxy_manifest = load_manifest(proxy_dir / "manifest.json")
    for index, (path, gold) in enumerate(
        zip(sorted(proxy_dir.glob("proxy-*.mp3")), proxy_manifest),
        start=1,
    ):
        samples.append(
            {
                "dataset": "proxy_expense",
                "index": index,
                "path": path,
                "gold": gold,
            }
        )

    health_dir = root / ".imp09_proxy_health"
    if health_dir.exists():
        health_manifest = load_manifest(health_dir / "manifest.json")
        for index, (path, gold) in enumerate(
            zip(sorted(health_dir.glob("health-*.mp3")), health_manifest),
            start=1,
        ):
            samples.append(
                {
                    "dataset": "proxy_health",
                    "index": index,
                    "path": path,
                    "gold": gold,
                }
            )
    return samples


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0
    position = round((len(ordered) - 1) * fraction)
    return ordered[position]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for model in sorted({str(row["model"]) for row in rows}):
        selected = [row for row in rows if row["model"] == model]
        successful = [row for row in selected if row["success"]]
        latencies = [float(row["latency_ms"]) for row in successful]
        health = [
            row
            for row in successful
            if row["dataset"] == "proxy_health"
        ]
        summary[model] = {
            "requests": len(selected),
            "success": len(successful),
            "errors": len(selected) - len(successful),
            "latency_ms_mean": round(statistics.mean(latencies), 1)
            if latencies
            else None,
            "latency_ms_p50": percentile(latencies, 0.50),
            "latency_ms_p95": percentile(latencies, 0.95),
            "estimated_cost_usd": round(
                sum(float(row.get("estimated_cost_usd") or 0) for row in selected),
                6,
            ),
            "medical_keyword_hits": sum(
                bool(row.get("health_trigger")) for row in health
            ),
            "medical_keyword_total": len(health),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--health-guard", type=Path)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=sorted(ALLOWED_MODELS),
        default=sorted(ALLOWED_MODELS),
    )
    args = parser.parse_args()

    from openai import OpenAI

    key = _read_private_key()
    if not key:
        raise SystemExit("OPENAI_API_KEY is not configured")
    samples = build_samples(args.dataset_root)
    sample_map = {
        (sample["dataset"], int(sample["index"])): sample
        for sample in samples
    }
    counts = {
        dataset: sum(sample["dataset"] == dataset for sample in samples)
        for dataset in ("real", "proxy_expense", "proxy_health")
    }
    if counts["real"] != 15 or counts["proxy_expense"] != 20:
        raise SystemExit(f"unexpected dataset counts: {counts}")

    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    result_path = args.output_dir / "results.jsonl"
    completed: set[tuple[str, str, int]] = set()
    rows: list[dict[str, Any]] = []
    if result_path.exists():
        for line in result_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(row)
            if row.get("success"):
                completed.add(
                    (row["model"], row["dataset"], int(row["index"]))
                )

    detector = load_detector(args.health_guard)
    client = OpenAI(
        api_key=key,
        base_url="https://api.openai.com/v1",
        timeout=60,
        max_retries=2,
    )
    try:
        with result_path.open("a", encoding="utf-8") as output:
            for model in args.models:
                for sample in samples:
                    identity = (
                        model,
                        sample["dataset"],
                        int(sample["index"]),
                    )
                    if identity in completed:
                        continue
                    path = sample["path"]
                    duration = duration_seconds(path)
                    started = time.perf_counter()
                    try:
                        with path.open("rb") as audio:
                            response = client.audio.transcriptions.create(
                                model=model,
                                file=audio,
                                prompt=DEFAULT_PROMPT,
                                response_format="json",
                                temperature=0,
                            )
                        transcript = str(
                            getattr(response, "text", "") or ""
                        ).strip()
                        if not transcript:
                            raise RuntimeError("empty transcript")
                        usage = usage_dict(response)
                        row = {
                            "model": model,
                            "dataset": sample["dataset"],
                            "index": sample["index"],
                            "name": path.name,
                            "sha256": hashlib.sha256(
                                path.read_bytes()
                            ).hexdigest(),
                            "duration_sec": round(duration, 3),
                            "success": True,
                            "latency_ms": round(
                                (time.perf_counter() - started) * 1000
                            ),
                            "transcript": transcript,
                            "health_trigger": detector(transcript),
                            "gold": sample["gold"],
                            "usage": usage,
                            "estimated_cost_usd": round(
                                estimate_cost(model, duration, usage), 8
                            ),
                        }
                    except Exception as exc:
                        row = {
                            "model": model,
                            "dataset": sample["dataset"],
                            "index": sample["index"],
                            "name": path.name,
                            "duration_sec": round(duration, 3),
                            "success": False,
                            "latency_ms": round(
                                (time.perf_counter() - started) * 1000
                            ),
                            "error_class": type(exc).__name__,
                            "error": str(exc)[:300],
                            "gold": sample["gold"],
                            "estimated_cost_usd": 0,
                        }
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                    output.flush()
                    rows.append(row)
                    print(
                        json.dumps(
                            {
                                "model": model,
                                "dataset": sample["dataset"],
                                "index": sample["index"],
                                "success": row["success"],
                                "latency_ms": row["latency_ms"],
                            }
                        ),
                        flush=True,
                    )
    finally:
        client.close()

    # Recalculate file-derived fields on every resumable run. This also makes
    # a corrected duration/cost formula repair an existing result set without
    # spending on duplicate API calls.
    for row in rows:
        sample = sample_map[(row["dataset"], int(row["index"]))]
        duration = duration_seconds(sample["path"])
        row["duration_sec"] = round(duration, 3)
        if row.get("success"):
            row["health_trigger"] = detector(str(row.get("transcript") or ""))
            row["estimated_cost_usd"] = round(
                estimate_cost(row["model"], duration, row.get("usage") or {}),
                8,
            )
    replacement = result_path.with_suffix(".jsonl.new")
    with replacement.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    replacement.replace(result_path)

    summary = {
        "dataset_counts": counts,
        "models": summarize(rows),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result_path.chmod(0o600)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
