"""Tune Tier-1 weights, tau and delta on the DEV split only.

Two steps, so the slow browser part runs once and the grid runs in seconds:

  capture   For every DEV scenario: record baselines (2 green runs), apply the
            mutation, run the example test through PageProxy until the broken
            step times out, and save the step's baseline fingerprint plus every
            candidate fingerprint on the page. Then, for each of the top-K
            compatible candidates (default weights), replay the test to the
            broken step in a FRESH context, click that candidate, and save the
            actions the server logged. Labels come from the action log only.
            Writes docs/measurements/tune-capture-<ts>.json.

  grid      Offline grid over weights, sigma, tau and delta, modelling the engine
            (engine.py step 5): gate on top-1; if accepted, verify top-1 then up
            to 2 runners-up with score >= tier2_floor; the verifier accepts a
            candidate only if it fires the expected action (it rejects any other
            effect: proven on dev by tests/integration/test_benchmark_ablation.py).
            A gate-accepted candidate WITHOUT a label (outside the top-K clicked)
            counts as unsafe, and any point with an unsafe accept is discarded.
            Objective: max true heals on healable scenarios, then fewest
            wrong top-1 accepts (less reliance on the verifier), then the
            smallest change from the current defaults.
            Writes docs/measurements/tune-grid-<ts>.json.

The eval split is never loaded (scenarios are filtered to split == "dev").

Usage:
  uv run python scripts/tune_tier1.py capture [--top-k 8]
  uv run python scripts/tune_tier1.py grid --capture docs/measurements/tune-capture-....json
"""

from __future__ import annotations

import argparse
import importlib
import itertools
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.g1_check import LastStep, actions, control, record_baselines  # noqa: E402

from chaos_store.scenario import Scenario, iter_scenarios  # noqa: E402
from chaos_store.serve import serve_in_thread  # noqa: E402
from healwright.config import Settings  # noqa: E402
from healwright.models import ElementFingerprint  # noqa: E402
from healwright.plugin.proxy import ActionTracker, PageProxy, RunStats  # noqa: E402
from healwright.recorder.extract import extract  # noqa: E402
from healwright.recorder.fingerprint import fingerprint_from_row  # noqa: E402
from healwright.store.baselines import baseline_path, load  # noqa: E402
from healwright.tier1 import score_candidates  # noqa: E402
from healwright.tier1.scorer import FEATURES, Weights, prepare, role_group, score_batch  # noqa: E402

OUT = ROOT / "docs" / "measurements"
MAX_VERIFY = 3  # engine.py


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")


# --------------------------------------------------------------------------- capture


def break_test(pw_browser: Any, base: str, scenario: Scenario, settings: Settings) -> Any:
    """Run the scenario's test through PageProxy until it times out. Returns (ctx, page, key)."""
    assert scenario.test
    module_path, func_name = scenario.test.split("::")
    module = importlib.import_module(module_path.removesuffix(".py").replace("/", "."))
    test_fn = getattr(module, func_name)
    nodeid = f"{scenario.test}[chromium]"
    context = pw_browser.new_context(base_url=base, viewport={"width": 1280, "height": 800})
    context.set_default_timeout(settings.probe_timeout_ms)
    page = context.new_page()
    spy = LastStep()
    proxy = PageProxy(page, ActionTracker(test_nodeid=nodeid, stats=RunStats(), observers=[spy]))
    try:
        test_fn(proxy)
    except PlaywrightTimeoutError:
        return context, page, spy.key, nodeid
    context.close()
    raise RuntimeError("test did not break under the mutation")


def capture_one(
    browser: Any, base: str, scenario: Scenario, bdir: Path, settings: Settings, top_k: int
) -> dict[str, Any]:
    assert scenario.expected
    context, page, key, nodeid = break_test(browser, base, scenario, settings)
    try:
        if key is None:
            raise RuntimeError("no wrapped step was running when it broke")
        bfile = load(baseline_path(bdir, nodeid))
        record = bfile.find(key) if bfile else None
        if record is None:
            raise RuntimeError(f"no baseline for step {key.selector!r}")
        target = record.baseline.fingerprint
        snap = extract(page, keep=True)
        fps = [fingerprint_from_row(r, snap["viewport"]) for r in snap["rows"]]
    finally:
        context.close()
    ranked = score_candidates(target, fps, limit=top_k)
    labels: dict[int, list[str]] = {}
    for cand in ranked:
        ctx2, page2, _key2, _ = break_test(browser, base, scenario, settings)
        try:
            snap2 = extract(page2, keep=True)
            fp2 = fingerprint_from_row(snap2["rows"][cand.index], snap2["viewport"])
            if fp2.model_dump() != fps[cand.index].model_dump():
                raise RuntimeError(f"snapshot index {cand.index} not stable across replays")
            session = {c["name"]: c["value"] for c in ctx2.cookies()}["cw_session"]
            before = actions(base, session)
            page2.evaluate("(i) => window.__healwright_candidates[i].click()", cand.index)
            fired: list[str] = []
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline and not fired:
                page2.wait_for_timeout(100)
                fired = actions(base, session)[len(before) :]
            labels[cand.index] = fired
        finally:
            ctx2.close()
    return {
        "id": scenario.id,
        "class": scenario.klass,
        "expected_outcome": scenario.expected.outcome,
        "expected_action": scenario.expected.action_id,
        "step": key.selector,
        "target": target.model_dump(mode="json"),
        "candidates": [fp.model_dump(mode="json") for fp in fps],
        "labels": {str(i): fired for i, fired in labels.items()},
    }


def cmd_capture(top_k: int) -> Path:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    dev = [s for s in iter_scenarios() if s.split == "dev"]
    rows: list[dict[str, Any]] = []
    with (
        tempfile.TemporaryDirectory(prefix="tune-") as tmp,
        serve_in_thread() as base,
        sync_playwright() as pw,
    ):
        browser = pw.chromium.launch(headless=True)
        try:
            for scenario in dev:
                assert scenario.test
                bdir = Path(tmp) / scenario.id
                control(base, "reset")
                record_baselines(base, scenario.test, bdir)
                control(
                    base,
                    "scenario",
                    content=scenario.model_dump_json(by_alias=True, exclude_none=True),
                )
                t0 = time.perf_counter()
                try:
                    rows.append(capture_one(browser, base, scenario, bdir, settings, top_k))
                except Exception as exc:  # noqa: BLE001 - recorded, never hidden
                    rows.append({"id": scenario.id, "error": f"{type(exc).__name__}: {exc}"})
                control(base, "reset")
                print(f"{scenario.id}: {time.perf_counter() - t0:.1f} s", rows[-1].get("error", ""))
        finally:
            browser.close()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"tune-capture-{stamp()}.json"
    doc = {"captured_at": stamp(), "split": "dev", "top_k": top_k, "scenarios": rows}
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    return path


# --------------------------------------------------------------------------- grid


class Prepared:
    """Per scenario: compatible candidates' feature scores for each sigma."""

    def __init__(self, row: dict[str, Any], sigmas: list[float]) -> None:
        self.id = row["id"]
        self.klass = row["class"]
        self.healable = row["expected_outcome"] == "healed"
        self.expected_action = row["expected_action"]
        target = ElementFingerprint.model_validate(row["target"])
        fps = [ElementFingerprint.model_validate(c) for c in row["candidates"]]
        group = role_group(target.role)
        self.indices = [i for i, fp in enumerate(fps[:400]) if fp.role in group]
        pool = [fps[i] for i in self.indices]
        self.features = {s: score_batch(prepare(target, Weights(sigma=s)), pool) for s in sigmas}
        self.labels = {int(k): v for k, v in row["labels"].items()}

    def label(self, index: int) -> str:
        if index not in self.labels:
            return "unknown"
        return "true" if self.expected_action in self.labels[index] else "wrong"


def rank(p: Prepared, w: dict[str, float], sigma: float) -> list[tuple[float, int]]:
    out = []
    for idx, scores in zip(p.indices, p.features[sigma], strict=True):
        tw = tot = 0.0
        for f in FEATURES:
            v = scores[f]
            if v is not None:
                tw += w[f]
                tot += w[f] * v
        out.append((tot / tw if tw else 0.0, idx))
    out.sort(key=lambda r: (-r[0], r[1]))
    return out


def outcome(
    ranked: list[tuple[float, int]], p: Prepared, tau: float, delta: float, floor: float
) -> str:
    """'true_heal' | 'red' | 'unsafe' (accepted an unlabeled candidate). Plus top-1 wrong flag."""
    if not ranked:
        return "red"
    top = ranked[0][0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if top + 1e-9 < tau or top - second + 1e-9 < delta:
        return "red"  # Tier 2 replay miss -> needs_human (no keys)
    to_verify = [ranked[0]] + [c for c in ranked[1:MAX_VERIFY] if c[0] >= floor]
    for _score, idx in to_verify:
        lab = p.label(idx)
        if lab == "unknown":
            return "unsafe"
        if lab == "true":
            return "true_heal"
    return "red"


def cmd_grid(capture: Path) -> Path:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    doc = json.loads(capture.read_text(encoding="utf-8"))
    errors = [r for r in doc["scenarios"] if "error" in r]
    if errors:
        raise SystemExit(f"capture has errored scenarios: {[r['id'] for r in errors]}")
    sigmas = [0.10, 0.15, 0.25]
    scen = [Prepared(r, sigmas) for r in doc["scenarios"]]
    levels = [0.05, 0.15, 0.25, 0.35]
    taus = [0.60, 0.65, 0.70, 0.75, 0.80]
    deltas = [0.02, 0.04, 0.06, 0.08, 0.10, 0.12]
    d = Weights()
    default_w = {f: d.of(f) for f in FEATURES}

    def evaluate(w: dict[str, float], sigma: float, tau: float, delta: float) -> dict[str, Any]:
        res: dict[str, str] = {}
        wrong_top = 0
        for p in scen:
            r = rank(p, w, sigma)
            o = outcome(r, p, tau, delta, settings.tier2_floor)
            res[p.id] = o
            accepted = (
                bool(r)
                and r[0][0] + 1e-9 >= tau
                and (r[0][0] - (r[1][0] if len(r) > 1 else 0.0) + 1e-9 >= delta)
            )
            if accepted and p.label(r[0][1]) != "true":
                wrong_top += 1
        return {
            "true_heals": sum(1 for p in scen if p.healable and res[p.id] == "true_heal"),
            "unsafe": sum(1 for v in res.values() if v == "unsafe"),
            "trap_heals_to_true": sum(
                1 for p in scen if not p.healable and res[p.id] == "true_heal"
            ),
            "wrong_top1_accepts": wrong_top,
            "per_scenario": res,
        }

    t0 = time.perf_counter()
    best: tuple[Any, ...] | None = None
    best_row: dict[str, Any] | None = None
    tried = 0
    baseline_eval = evaluate(default_w, 0.15, settings.tau_conf, settings.delta_margin)
    for combo in itertools.product(levels, repeat=len(FEATURES)):
        w = dict(zip(FEATURES, combo, strict=True))
        for sigma in sigmas:
            ranked_all = {p.id: rank(p, w, sigma) for p in scen}
            for tau, delta in itertools.product(taus, deltas):
                tried += 1
                unsafe = 0
                heals = 0
                wrong = 0
                for p in scen:
                    o = outcome(ranked_all[p.id], p, tau, delta, settings.tier2_floor)
                    if o == "unsafe":
                        unsafe += 1
                        break
                    if p.healable and o == "true_heal":
                        heals += 1
                    r = ranked_all[p.id]
                    if (
                        r
                        and r[0][0] + 1e-9 >= tau
                        and r[0][0] - (r[1][0] if len(r) > 1 else 0.0) + 1e-9 >= delta
                        and p.label(r[0][1]) != "true"
                    ):
                        wrong += 1
                if unsafe:
                    continue
                total = sum(w.values())
                change = sum(abs(w[f] / total - default_w[f]) for f in FEATURES)
                change += (
                    abs(sigma - 0.15)
                    + abs(tau - settings.tau_conf)
                    + abs(delta - settings.delta_margin)
                )
                key = (-heals, wrong, round(change, 6))
                if best is None or key < best:
                    best = key
                    best_row = {"weights": w, "sigma": sigma, "tau": tau, "delta": delta}
    assert best_row is not None
    chosen = evaluate(best_row["weights"], best_row["sigma"], best_row["tau"], best_row["delta"])

    # robustness: how many neighbouring (tau, delta) points keep the same true heals with no unsafe
    neighbours = []
    for tau, delta in itertools.product(taus, deltas):
        e = evaluate(best_row["weights"], best_row["sigma"], tau, delta)
        neighbours.append(
            {
                "tau": tau,
                "delta": delta,
                "true_heals": e["true_heals"],
                "unsafe": e["unsafe"],
                "wrong_top1_accepts": e["wrong_top1_accepts"],
            }
        )
    total = sum(best_row["weights"].values())
    result = {
        "tuned_at": stamp(),
        "split": "dev",
        "capture": str(capture.relative_to(ROOT)) if capture.is_relative_to(ROOT) else str(capture),
        "points_tried": tried,
        "seconds": round(time.perf_counter() - t0, 1),
        "healable": sum(1 for p in scen if p.healable),
        "traps": sum(1 for p in scen if not p.healable),
        "current": {
            "weights": default_w,
            "sigma": 0.15,
            "tau": settings.tau_conf,
            "delta": settings.delta_margin,
            **baseline_eval,
        },
        "chosen": {
            **best_row,
            "weights_normalised": {f: round(v / total, 4) for f, v in best_row["weights"].items()},
            **chosen,
        },
        "tau_delta_surface_for_chosen_weights": neighbours,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"tune-grid-{stamp()}.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    print(json.dumps({k: result[k] for k in ("current", "chosen")}, indent=1))
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--top-k", type=int, default=8)
    g = sub.add_parser("grid")
    g.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "capture":
        cmd_capture(args.top_k)
    else:
        cmd_grid(args.capture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
