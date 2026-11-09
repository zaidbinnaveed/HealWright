"""Combine several runs of one system into mean / range per metric.

    uv run python -m benchmark.combine benchmark/results/2026-11-07/healwright-eval-r1 \\
        benchmark/results/2026-11-07/healwright-eval-r2 ... --out .../healwright-eval-combined

Every number comes from the input results.json files (never typed by hand). Each input
is one benchmark invocation (one run); its aggregate is recomputed from its rows with the
runner's own ``aggregate`` so all inputs use the same definitions.

**Harness errors are excluded from every denominator, for every system, the same way**:
rows whose outcome is ``error`` (the harness itself failed, e.g. a subprocess
timeout; the method was never scored) are dropped before any rate is computed, and
reported as a separate count with the number of scenarios actually scored. Per-run
summary.md files written by the runner use ALL rows; this combined summary is the
one to report.

``deadline_tier2_provider_waits`` counts scenarios
whose heal hit the whole-heal deadline DURING TIER 2 while the provider was rate-
limiting or timing out. Evidence, the strongest the frozen runner records: the heal
event's reason says "heal deadline ... exceeded during tier2" AND the same run's
``provider_calls`` contains at least one 429 or timeout (per-call timings per
scenario are not kept by the runner). The scenario's outcome stays red and the raw
rates stay the headline numbers; this is an explanatory count only, applied to every
system the same way.

``regression_red_*`` (user request 2026-11-08, reporting only) splits the regression
traps that stayed red by cause; the red count itself is unchanged. Per scenario, from
its heal events, in this order: **timeout** if any event's reason says "heal deadline"
(the 30 s whole-heal deadline); **declined** if the healer decided not to heal
(an event with status ``regression_suspected`` or ``needs_human``; NOT a raw-HTML
baseline ``needs_human``, whose reason starts with "rawhtml:": that baseline has no
gate, so its needs_human always means its selector or the provider call failed);
**error** for anything else, including a red trap with NO heal event (the cause was not recorded;
the frozen runner keeps no per-scenario log). The three always add up to the regression
traps that stayed red.

``provider_failures`` counts scenarios where the model call failed (rate limit, quota,
cap): those scenarios ended red because of the provider, not because of the method, and
are reported separately so they cannot hide inside "red".
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from benchmark.run import aggregate

METRICS: tuple[tuple[str, str], ...] = (
    ("true_heals", "True heals (healable)"),
    ("true_heal_rate", "True heal rate (healable)"),
    ("false_heals_on_traps", "False heals on traps"),
    ("silent_false_heal_rate", "Silent false-heal rate (all scenarios)"),
    ("precision_of_accepted_heals", "Precision of accepted heals"),
    ("tier1_share_of_heals", "Tier-1 share of heals"),
    ("latency_ms.tier1.p50", "Tier-1 heal latency p50 (ms)"),
    ("latency_ms.tier1.p95", "Tier-1 heal latency p95 (ms)"),
    ("latency_ms.tier2.p50", "Tier-2 heal latency p50 (ms)"),
    ("latency_ms.tier2.p95", "Tier-2 heal latency p95 (ms)"),
    ("latency_ms.all_heals.p50", "Heal latency, all heals, p50 (ms)"),
    ("latency_ms.all_heals.p95", "Heal latency, all heals, p95 (ms)"),
    ("provider_failures", "Scenarios lost to provider failures"),
    (
        "deadline_tier2_provider_waits",
        "Heal deadline exceeded during Tier 2 due to provider waits (outcome stays red)",
    ),
    (
        "deadline_tier2_provider_waits_healable",
        "  of which on healable scenarios (cost a heal; traps should be red anyway)",
    ),
    ("regression_red_declined", "Regression traps red: healer declined (no heal)"),
    ("regression_red_timeout", "Regression traps red: 30 s heal deadline hit"),
    ("regression_red_error", "Regression traps red: other error or no heal event recorded"),
    ("healable_scored", "Healable scenarios scored (denominator)"),
    ("scenarios_scored", "Scenarios scored (all)"),
    ("errors", "Harness errors (excluded from all rates)"),
)


def dig(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


TRAPS = ("distractor_trap", "regression_trap")


def deadline_tier2_provider_waits(
    rows: list[dict[str, Any]], provider_calls: dict[str, dict[str, int]]
) -> int:
    """Scenarios whose heal ran out of time in Tier 2 in a run with 429s / timeouts."""
    waited = any(
        status in ("429", "timeout") and count > 0
        for by_status in provider_calls.values()
        for status, count in by_status.items()
    )
    if not waited:
        return 0
    return sum(
        1
        for r in rows
        if any(
            "heal deadline" in str(e.get("reason", ""))
            and "during tier2" in str(e.get("reason", ""))
            for e in r.get("events", [])
        )
    )


DECLINED = ("regression_suspected", "needs_human")


def regression_red_cause(row: dict[str, Any]) -> str:
    """Why a regression trap stayed red: "timeout", "declined" or "error" (reporting only)."""
    events = row.get("events", [])
    if any("heal deadline" in str(e.get("reason", "")) for e in events):
        return "timeout"
    if any(
        e.get("status") in DECLINED and not str(e.get("reason", "")).startswith("rawhtml:")
        for e in events
    ):
        return "declined"
    return "error"


def regression_red_causes(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {"declined": 0, "timeout": 0, "error": 0}
    for r in rows:
        if r.get("class") == "regression_trap" and r.get("outcome") == "red":
            out[regression_red_cause(r)] += 1
    return out


def combine(folders: list[Path]) -> dict[str, Any]:
    runs = []
    for folder in folders:
        data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
        rows = data["rows"]
        scored = [r for r in rows if r.get("outcome") != "error"]
        agg = aggregate(scored)  # every rate is over SCORED scenarios only
        agg["errors"] = len(rows) - len(scored)
        agg["scenarios_scored"] = len(scored)
        agg["healable_scored"] = agg["healable"]
        calls = data.get("provider_calls", {})
        agg["deadline_tier2_provider_waits"] = deadline_tier2_provider_waits(scored, calls)
        healable = [r for r in scored if r.get("class") not in TRAPS]
        agg["deadline_tier2_provider_waits_healable"] = deadline_tier2_provider_waits(
            healable, calls
        )
        for cause, count in regression_red_causes(scored).items():
            agg[f"regression_red_{cause}"] = count
        runs.append(
            {
                "folder": folder.as_posix(),
                "system": data["system"],
                "split": data["split"],
                "vlm_mode": data["vlm_mode"],
                "started_at": data["started_at"],
                "aggregate": agg,
            }
        )
    systems = {r["system"] for r in runs}
    splits = {r["split"] for r in runs}
    if len(systems) != 1 or len(splits) != 1:
        raise SystemExit(f"inputs mix systems/splits: {systems} {splits}")
    summary: dict[str, Any] = {}
    for key, _label in METRICS:
        values = [dig(r["aggregate"], key) for r in runs]
        numbers = [float(v) for v in values if isinstance(v, int | float)]
        summary[key] = {
            "values": values,
            "mean": round(statistics.mean(numbers), 4) if numbers else None,
            "min": min(numbers) if numbers else None,
            "max": max(numbers) if numbers else None,
        }
    return {
        "system": runs[0]["system"],
        "split": runs[0]["split"],
        "runs": len(runs),
        "per_run": runs,
        "summary": summary,
    }


def summary_md(result: dict[str, Any]) -> str:
    modes = ", ".join(f"{r['vlm_mode']}" for r in result["per_run"])
    lines = [
        f"# Benchmark: {result['system']} on {result['split']}: {result['runs']} run(s) combined",
        "",
        f"VLM modes per run: {modes}. Generated from the runs' results.json files. "
        "Do not edit by hand.",
        "",
        "| Metric | Mean | Range (min to max) | Per run |",
        "| --- | --- | --- | --- |",
    ]
    for key, label in METRICS:
        s = result["summary"][key]
        if s["mean"] is None:
            lines.append(f"| {label} | n/a | n/a | {s['values']} |")
            continue
        lines.append(f"| {label} | {s['mean']} | {s['min']} to {s['max']} | {s['values']} |")
    lines += ["", "Inputs:", ""] + [
        f"- `{r['folder']}` ({r['vlm_mode']})" for r in result["per_run"]
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmark.combine")
    parser.add_argument("folders", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = combine(args.folders)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "combined.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.out / "summary.md").write_text(summary_md(result), encoding="utf-8")
    print(f"wrote {args.out}/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
