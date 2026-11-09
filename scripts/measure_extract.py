"""Measure extract.js on the Chaos Store product page.

Usage:  uv run python scripts/measure_extract.py [--runs 20] [--path /product/1]

Starts the Chaos Store in a thread, launches headless Chromium (viewport
1280x800, DPR 1), runs one warm-up extraction (not counted), then N timed
runs. Writes raw samples and percentiles to docs/measurements/. Every reported
number must be copied from that file.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make chaos_store importable when run as a script

from chaos_store.serve import serve_in_thread  # noqa: E402
from healwright.recorder.extract import extract  # noqa: E402


def pct(samples: list[float], p: int) -> float:
    """Percentile with linear interpolation between closest ranks (inclusive method)."""
    return round(statistics.quantiles(samples, n=100, method="inclusive")[p - 1], 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--path", default="/product/1")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "measurements")
    args = parser.parse_args()

    round_trip: list[float] = []
    in_page: list[float] = []
    with serve_in_thread() as base_url, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
        page.goto(base_url + args.path)
        warm = extract(page)
        for _ in range(args.runs):
            t0 = time.perf_counter()
            snap = extract(page)
            round_trip.append(round((time.perf_counter() - t0) * 1000, 2))
            in_page.append(float(snap["ms"]))
        chromium_version = browser.version
        browser.close()

    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "what": "extract.js snapshot via page.evaluate, one round trip per run",
        "page": args.path,
        "runs": args.runs,
        "warmup_runs_excluded": 1,
        "candidates": warm["total"],
        "round_trip_ms": {
            "p50": pct(round_trip, 50),
            "p95": pct(round_trip, 95),
            "min": min(round_trip),
            "max": max(round_trip),
            "samples": round_trip,
        },
        "in_page_ms": {
            "p50": pct(in_page, 50),
            "p95": pct(in_page, 95),
            "samples": in_page,
        },
        "target_ms": 150,
        "environment": {
            "machine": platform.node(),
            "processor": platform.processor(),
            "os": platform.platform(),
            "python": platform.python_version(),
            "chromium": chromium_version,
            "headless": True,
            "viewport": [1280, 800],
        },
    }
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    path = args.out / f"extract-js-{stamp}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    print(json.dumps({k: result[k] for k in ("candidates", "round_trip_ms", "in_page_ms")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
