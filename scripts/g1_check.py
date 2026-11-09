"""Gate G1 check: numbers from files, never typed by hand.

Criterion 1: on the dev scenarios for id_rename and css_refactor, Tier 1 picks
the TRUE target in >= 80% of cases, checked against the server action log.
Criterion 2: the examples suite stays green in record mode 5 runs in a row.

Per scenario (all dev scenarios are run; criterion 1 uses only the id_rename
and css_refactor ones, the rest are reported for information):
  1. record baselines for the scenario's test: 2 green runs, record mode;
  2. apply the mutation server-wide;
  3. run the example test function directly through PageProxy with a 3 s
     probe timeout until the broken step times out;
  4. extract the page, score candidates against the step's baseline
     fingerprint with Tier 1, apply the margin gate;
  5. click the top-1 candidate and read which action the server logged.

There is no verifier in this check: for traps it shows what Tier 1 ALONE would
do, which is exactly why the verifier exists.

Usage: uv run python scripts/g1_check.py [--skip-suite]
Writes docs/measurements/g1-<timestamp>.json.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chaos_store.scenario import Scenario, iter_scenarios  # noqa: E402
from chaos_store.serve import free_port, serve_in_thread  # noqa: E402
from healwright.config import Settings  # noqa: E402
from healwright.models import StepKey  # noqa: E402
from healwright.plugin.proxy import ActionTracker, PageProxy, RunStats  # noqa: E402
from healwright.recorder.extract import extract  # noqa: E402
from healwright.recorder.fingerprint import fingerprint_from_row  # noqa: E402
from healwright.store.baselines import baseline_path, load  # noqa: E402
from healwright.tier1 import decide, score_candidates  # noqa: E402

G1_CLASSES = ("id_rename", "css_refactor")


class LastStep:
    """StepObserver that remembers the step about to run (the one that will fail)."""

    def __init__(self) -> None:
        self.key: StepKey | None = None

    def before_action(
        self, page: Page, key: StepKey, target: Locator, source_line: int | None
    ) -> None:
        self.key = key

    def before_goto(self, page: Page) -> None:
        return None


def control(base: str, path: str, **kw: Any) -> httpx.Response:
    res = httpx.request(kw.pop("method", "POST"), f"{base}/__chaos/{path}", timeout=10, **kw)
    res.raise_for_status()
    return res


def actions(base: str, session: str) -> list[str]:
    data = control(base, "actions", method="GET", params={"session": session}).json()
    return [a["action_id"] for a in data["actions"]]


def record_baselines(base: str, test: str, bdir: Path) -> None:
    env = {
        **os.environ,
        "HEALWRIGHT_MODE": "record",
        "HEALWRIGHT_BASELINE_DIR": str(bdir),
        "CHAOS_BASE_URL": base,
    }
    env.pop("CHAOS_SESSION", None)
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"baseline run failed for {test}:\n{proc.stdout[-2000:]}")


def probe(pw: Any, base: str, scenario: Scenario, bdir: Path, settings: Settings) -> dict[str, Any]:
    assert scenario.test
    assert scenario.expected
    module_path, func_name = scenario.test.split("::")
    module = importlib.import_module(module_path.removesuffix(".py").replace("/", "."))
    test_fn = getattr(module, func_name)
    nodeid = f"{scenario.test}[chromium]"

    browser = pw.chromium.launch(headless=True)
    try:
        context = browser.new_context(base_url=base, viewport={"width": 1280, "height": 800})
        context.set_default_timeout(settings.probe_timeout_ms)
        page = context.new_page()
        spy = LastStep()
        proxy = PageProxy(
            page, ActionTracker(test_nodeid=nodeid, stats=RunStats(), observers=[spy])
        )
        try:
            test_fn(proxy)
            return {"id": scenario.id, "error": "test did not break under the mutation"}
        except PlaywrightTimeoutError:
            pass
        key = spy.key
        if key is None:
            return {"id": scenario.id, "error": "no wrapped step was running when it broke"}
        bfile = load(baseline_path(bdir, nodeid))
        record = bfile.find(key) if bfile else None
        if record is None:
            return {"id": scenario.id, "error": f"no baseline for step {key.selector!r}"}
        target = record.baseline.fingerprint

        t0 = time.perf_counter()
        snap = extract(page, keep=True)
        fps = [fingerprint_from_row(r, snap["viewport"]) for r in snap["rows"]]
        ranked = score_candidates(target, fps, limit=15)
        gate = decide(ranked, settings.tau_conf, settings.delta_margin)
        tier1_ms = round((time.perf_counter() - t0) * 1000, 2)
        if not ranked:
            return {"id": scenario.id, "step": key.selector, "error": "no compatible candidate"}

        session = {c["name"]: c["value"] for c in context.cookies()}["cw_session"]
        before = actions(base, session)
        page.evaluate("(i) => window.__healwright_candidates[i].click()", ranked[0].index)
        fired: list[str] = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not fired:
            page.wait_for_timeout(100)
            fired = actions(base, session)[len(before) :]
        top = ranked[0]
        return {
            "id": scenario.id,
            "class": scenario.klass,
            "expected_outcome": scenario.expected.outcome,
            "step": key.selector,
            "top1": {
                "role": top.fingerprint.role,
                "name": top.fingerprint.accessible_name,
                "score": round(top.score, 4),
                "feature_scores": {k: round(v, 4) for k, v in top.feature_scores.items()},
            },
            "top2_score": round(ranked[1].score, 4) if len(ranked) > 1 else None,
            "gate_accepted": gate.accepted,
            "gate_reason": gate.reason,
            "candidates": len(fps),
            "extract_plus_tier1_ms": tier1_ms,
            "expected_action": scenario.expected.action_id,
            "fired_actions": fired,
            "top1_is_true_target": scenario.expected.action_id in fired,
        }
    finally:
        browser.close()


def run_suite_record(times: int) -> list[bool]:
    results = []
    with tempfile.TemporaryDirectory(prefix="g1-suite-") as tmp:
        for _ in range(times):
            env = {
                **os.environ,
                "HEALWRIGHT_MODE": "record",
                "HEALWRIGHT_BASELINE_DIR": str(Path(tmp) / "b"),
                "CHAOS_PORT": str(free_port()),
            }
            for name in ("CHAOS_BASE_URL", "CHAOS_SESSION", "CHAOS_ACTION_TIMEOUT_MS"):
                env.pop(name, None)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "examples", "-q", "-p", "no:cacheprovider"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            results.append(proc.returncode == 0)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-suite", action="store_true")
    args = parser.parse_args()
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    dev = [s for s in iter_scenarios() if s.split == "dev"]
    rows: list[dict[str, Any]] = []
    with (
        tempfile.TemporaryDirectory(prefix="g1-") as tmp,
        serve_in_thread() as base,
        sync_playwright() as pw,
    ):
        for scenario in dev:
            assert scenario.test
            bdir = Path(tmp) / scenario.id
            control(base, "reset")
            record_baselines(base, scenario.test, bdir)
            control(
                base, "scenario", content=scenario.model_dump_json(by_alias=True, exclude_none=True)
            )
            try:
                rows.append(probe(pw, base, scenario, bdir, settings))
            except Exception as exc:  # noqa: BLE001 - recorded as an errored row, never hidden
                rows.append({"id": scenario.id, "error": f"{type(exc).__name__}: {exc}"})
            control(base, "reset")

    g1_rows = [
        r
        for r in rows
        if r.get("class") in G1_CLASSES
        or ("error" in r and any(s.id == r["id"] and s.klass in G1_CLASSES for s in dev))
    ]
    hits = sum(1 for r in g1_rows if r.get("top1_is_true_target"))
    suite = [] if args.skip_suite else run_suite_record(5)
    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "gate": "G1",
        "tau_conf": settings.tau_conf,
        "delta_margin": settings.delta_margin,
        "criterion_1": {
            "classes": list(G1_CLASSES),
            "scenarios": len(g1_rows),
            "top1_true_target": hits,
            "rate": round(hits / len(g1_rows), 4) if g1_rows else None,
            "target": 0.8,
            "passed": bool(g1_rows) and hits / len(g1_rows) >= 0.8,
        },
        "criterion_2": {
            "record_mode_runs": len(suite),
            "green_runs": sum(suite),
            "passed": bool(suite) and all(suite),
        },
        "scenarios": rows,
    }
    out = ROOT / "docs" / "measurements"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"g1-{datetime.now(UTC).strftime('%Y-%m-%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    print(json.dumps({"criterion_1": result["criterion_1"], "criterion_2": result["criterion_2"]}))
    for r in rows:
        print(
            r["id"],
            r.get("step"),
            "->",
            (r.get("top1") or {}).get("name"),
            r.get("top1") and r["top1"]["score"],
            "gate",
            r.get("gate_accepted"),
            "fired",
            r.get("fired_actions"),
            r.get("error", ""),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
