"""Measure Tier-1 scoring latency (target p95 < 10 ms; timer around the scorer only).

Usage:  uv run python scripts/measure_tier1.py [--reps 200]

Two workloads:
- synthetic: 300 button candidates (the design worst case), like the unit test;
- chaos_catalog: the real candidates of the Chaos Store catalog page, scored
  against the recorded fingerprint of ``#view-product-5`` (extracted live).
One warm-up call, then ``reps`` timed calls of ``score_candidates(..., limit=15)``.
Writes docs/measurements/tier1-scoring-<timestamp>.json.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chaos_store.serve import serve_in_thread  # noqa: E402
from healwright.models import BBox, ElementFingerprint  # noqa: E402
from healwright.recorder.extract import extract  # noqa: E402
from healwright.recorder.fingerprint import fingerprint_from_row  # noqa: E402
from healwright.tier1 import score_candidates  # noqa: E402
from tests.factories import fingerprint  # noqa: E402


def pct(samples: list[float], p: int) -> float:
    return round(statistics.quantiles(samples, n=100, method="inclusive")[p - 1], 3)


def time_it(
    target: ElementFingerprint, pool: list[ElementFingerprint], reps: int
) -> dict[str, object]:
    score_candidates(target, pool, limit=15)  # warm-up
    gc.collect()
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        score_candidates(target, pool, limit=15)
        samples.append((time.perf_counter() - t0) * 1000)
    return {
        "candidates": len(pool),
        "p50_ms": pct(samples, 50),
        "p95_ms": pct(samples, 95),
        "max_ms": round(max(samples), 3),
    }


def synthetic() -> tuple[ElementFingerprint, list[ElementFingerprint]]:
    target = fingerprint(neighbor_texts=["quantity", "$89.99", "trail running shoes"])
    pool = [
        fingerprint(
            accessible_name=f"item {i} label",
            text=f"item {i} label",
            attributes={"id": f"el-{i}", "data-testid": f"t-{i}", "type": "button"},
            class_tokens=["btn", f"c{i % 7}x"],
            neighbor_texts=[f"near {i}", "quantity", "$1.00"],
            bbox=BBox(x=(i * 37) % 1200, y=(i * 53) % 760, w=80, h=24),
        )
        for i in range(300)
    ]
    return target, pool


def chaos_catalog() -> tuple[ElementFingerprint, list[ElementFingerprint]]:
    with serve_in_thread() as base, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(base + "/")
        handle = page.query_selector("#view-product-5")
        assert handle is not None
        t = extract(page, target=handle)
        target = fingerprint_from_row(t["rows"][0], t["viewport"])
        snap = extract(page)
        pool = [fingerprint_from_row(r, snap["viewport"]) for r in snap["rows"]]
        browser.close()
    return target, pool


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=200)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "measurements")
    args = parser.parse_args()
    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "what": "score_candidates(limit=15) wall time, scorer only (no extraction)",
        "reps": args.reps,
        "synthetic_300": time_it(*synthetic(), args.reps),
        "chaos_catalog": time_it(*chaos_catalog(), args.reps),
        "target_p95_ms": 10,
        "environment": {"processor": platform.processor(), "python": platform.python_version()},
    }
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    path = args.out / f"tier1-scoring-{stamp}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    print(json.dumps({k: result[k] for k in ("synthetic_300", "chaos_catalog")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
