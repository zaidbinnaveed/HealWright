"""Measure green-run recording overhead (target < 10%).

Usage:  uv run python scripts/measure_overhead.py [--runs 3]

Runs the examples suite as a subprocess ``runs`` times with HEALWRIGHT_MODE=off
and ``runs`` times with HEALWRIGHT_MODE=record, INTERLEAVED (off, record, off,
record, ...) to spread machine noise evenly. Wall time includes pytest start-up
and browser launch, i.e. what a developer actually waits for.

The record runs share one temporary baseline directory, so the first record
run writes every baseline and later runs mostly confirm them; per-run times
are reported so that cold vs warm can be seen. Writes docs/measurements/.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_suite(mode: str, baseline_dir: Path, port: int) -> tuple[float, str]:
    env = {
        **os.environ,
        "HEALWRIGHT_MODE": mode,
        "HEALWRIGHT_BASELINE_DIR": str(baseline_dir),
        "CHAOS_PORT": str(port),
    }
    for name in ("CHAOS_BASE_URL", "CHAOS_SESSION", "CHAOS_ACTION_TIMEOUT_MS"):
        env.pop(name, None)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "examples", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        raise SystemExit(f"examples suite failed in mode={mode}:\n{proc.stdout[-3000:]}")
    return round(elapsed, 2), proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "measurements")
    args = parser.parse_args()

    off: list[float] = []
    record: list[float] = []
    summaries: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hw-overhead-") as tmp:
        baselines = Path(tmp) / "baselines"
        for _ in range(args.runs):
            t_off, _out = run_suite("off", baselines, args.port)
            off.append(t_off)
            t_rec, out = run_suite("record", baselines, args.port)
            record.append(t_rec)
            m = re.search(r"HealWright mode=record: .*", out)
            summaries.append(m.group(0) if m else "")

    mean_off, mean_rec = statistics.mean(off), statistics.mean(record)
    med_off, med_rec = statistics.median(off), statistics.median(record)
    # Paired overhead: each record run against the off run just before it (same machine state).
    paired = [round((r - o) / o * 100, 1) for o, r in zip(off, record, strict=True)]
    warm_paired = paired[1:]  # the first record run writes every baseline (cold)

    def spread(xs: list[float]) -> dict[str, float]:
        return {
            "min": round(min(xs), 2),
            "max": round(max(xs), 2),
            "stdev": round(statistics.stdev(xs), 2) if len(xs) > 1 else 0.0,
        }

    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "what": "examples suite wall time, subprocess, HEALWRIGHT_MODE off vs record, interleaved",
        "runs_per_mode": args.runs,
        "off_s": off,
        "record_s": record,
        "mean_off_s": round(mean_off, 2),
        "mean_record_s": round(mean_rec, 2),
        "overhead_pct": round((mean_rec - mean_off) / mean_off * 100, 1),
        "median_off_s": round(med_off, 2),
        "median_record_s": round(med_rec, 2),
        "median_overhead_pct": round((med_rec - med_off) / med_off * 100, 1),
        "spread_off_s": spread(off),
        "spread_record_s": spread(record),
        "paired_overhead_pct": paired,
        "median_paired_overhead_pct": round(statistics.median(paired), 1),
        "median_warm_paired_overhead_pct": (
            round(statistics.median(warm_paired), 1) if warm_paired else None
        ),
        "record_summaries": summaries,
        "target_pct": 10,
        "environment": {
            "processor": platform.processor(),
            "os": platform.platform(),
            "python": platform.python_version(),
        },
    }
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    path = args.out / f"recording-overhead-{stamp}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    keys = (
        "off_s",
        "record_s",
        "median_overhead_pct",
        "paired_overhead_pct",
        "median_paired_overhead_pct",
    )
    print(json.dumps({k: result[k] for k in keys}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
