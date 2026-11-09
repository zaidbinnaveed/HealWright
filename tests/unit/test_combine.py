"""benchmark.combine: mean / range across runs, provider failures counted separately."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmark.combine import combine, summary_md
from benchmark.run import provider_failures

pytestmark = pytest.mark.unit


def row(
    klass: str, outcome: str, status: str | None, reason: str = "", ms: float = 900.0
) -> dict[str, Any]:
    events = [{"status": status, "tier": 1, "total_ms": ms, "reason": reason}] if status else []
    return {"id": f"{klass}-{outcome}", "class": klass, "outcome": outcome, "events": events}


def write(tmp: Path, name: str, rows: list[dict[str, Any]], mode: str) -> Path:
    folder = tmp / name
    folder.mkdir()
    (folder / "results.json").write_text(
        json.dumps(
            {
                "system": "healwright",
                "split": "eval",
                "vlm_mode": mode,
                "started_at": "t",
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )
    return folder


def test_mean_and_range_across_runs(tmp_path: Path) -> None:
    a = write(
        tmp_path,
        "a",
        [row("id_rename", "true_heal", "healed"), row("id_rename", "red", "needs_human")],
        "record",
    )
    b = write(
        tmp_path,
        "b",
        [row("id_rename", "true_heal", "healed"), row("id_rename", "true_heal", "healed")],
        "live",
    )
    result = combine([a, b])
    s = result["summary"]["true_heal_rate"]
    assert s["values"] == [0.5, 1.0]
    assert (s["mean"], s["min"], s["max"]) == (0.75, 0.5, 1.0)
    md = summary_md(result)
    assert "0.75 | 0.5 to 1.0" in md
    assert "record, live" in md


def test_harness_errors_are_excluded_from_denominators(tmp_path: Path) -> None:
    rows = [row("id_rename", "true_heal", "healed")] * 39 + [row("copy_drift", "error", None)]
    a = write(tmp_path, "a", rows, "replay")
    s = combine([a])["summary"]
    assert s["true_heal_rate"]["values"] == [1.0]  # 39/39, not 39/40
    assert s["healable_scored"]["values"] == [39]
    assert s["errors"]["values"] == [1]
    assert s["scenarios_scored"]["values"] == [39]


def test_deadline_in_tier2_counts_only_with_provider_waits_in_the_run() -> None:
    from benchmark.combine import deadline_tier2_provider_waits

    rows = [
        row("css_refactor", "red", "error", "heal deadline of 30 s exceeded during tier2"),
        row("css_refactor", "red", "error", "heal deadline of 30 s exceeded during verify"),
        row("id_rename", "true_heal", "healed"),
    ]
    assert deadline_tier2_provider_waits(rows, {"groq": {"200": 5, "429": 2}}) == 1
    assert deadline_tier2_provider_waits(rows, {"groq": {"200": 5, "timeout": 1}}) == 1
    assert deadline_tier2_provider_waits(rows, {"groq": {"200": 5}}) == 0  # no waits
    assert deadline_tier2_provider_waits(rows, {}) == 0


def test_outcome_and_raw_rate_are_unchanged_by_the_deadline_count(tmp_path: Path) -> None:
    rows = [row("id_rename", "true_heal", "healed")] * 3 + [
        row("css_refactor", "red", "error", "heal deadline of 30 s exceeded during tier2")
    ]
    folder = write(tmp_path, "a", rows, "live")
    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    data["provider_calls"] = {"groq": {"429": 9, "200": 6}}
    (folder / "results.json").write_text(json.dumps(data), encoding="utf-8")
    s = combine([folder])["summary"]
    assert s["true_heal_rate"]["values"] == [0.75]  # raw: still 3 of 4
    assert s["deadline_tier2_provider_waits"]["values"] == [1]
    assert s["deadline_tier2_provider_waits_healable"]["values"] == [1]


def test_provider_failures_are_counted_not_hidden() -> None:
    rows = [
        row(
            "distractor_trap",
            "red",
            "needs_human",
            "Tier 2 failed: all providers failed: groq: rate limited (429)",
        ),
        row("id_rename", "red", "needs_human", "rawhtml: ProviderError: per-run call cap reached"),
        row("id_rename", "red", "needs_human", "tier 1 not confident"),
    ]
    assert provider_failures(rows) == 2


def test_inputs_must_be_one_system(tmp_path: Path) -> None:
    a = write(tmp_path, "a", [], "record")
    b = tmp_path / "b"
    b.mkdir()
    (b / "results.json").write_text(
        json.dumps(
            {
                "system": "rawhtml",
                "split": "eval",
                "vlm_mode": "live",
                "started_at": "t",
                "rows": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        combine([a, b])


def test_regression_red_is_split_by_cause_without_changing_outcomes(tmp_path: Path) -> None:
    from benchmark.combine import regression_red_causes

    rows = [
        row("regression_trap", "red", "regression_suspected", "Tier 2: target absent"),
        row("regression_trap", "red", "needs_human", "Tier 1 not confident; Tier 2 unavailable"),
        row("regression_trap", "red", "error", "heal deadline of 30 s exceeded during tier2"),
        row("regression_trap", "red", None),  # no heal event: cause not recorded
        row("regression_trap", "red", "error", "unexpected"),
        # raw-HTML baseline: its selector failed, it did not decide anything
        row("regression_trap", "red", "needs_human", "rawhtml: TimeoutError: Locator.click"),
        row("regression_trap", "false_heal", "healed"),  # not red: not counted
        row("distractor_trap", "red", "needs_human"),  # not a regression trap
    ]
    causes = regression_red_causes(rows)
    assert causes == {"declined": 2, "timeout": 1, "error": 3}
    assert sum(causes.values()) == 6  # = regression traps that stayed red
    s = combine([write(tmp_path, "a", rows, "replay")])["summary"]
    assert s["regression_red_timeout"]["values"] == [1]
    assert s["false_heals_on_traps"]["values"] == [1]  # existing metric unchanged
