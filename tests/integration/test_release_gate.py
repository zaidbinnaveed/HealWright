"""The three release-gate invariants, as automated tests.

1. No false green: the trap scenarios across the eval runs: zero false heals, and no heal of any
   kind on a regression trap. Checked on the committed eval results (fast, runs by default).
2. No false red: the unmutated example suite passes 20 times in record mode, and once more under
   each recorder fault (run folder not writable, corrupt baselines, recorder throws).
3. Patches are real fixes: every heal diff on the dev set passes ``git apply --check`` on a clean
   checkout, and after applying it the test passes natively with HealWright turned off.

2 and 3 take minutes: marker ``release_gate``, deselected unless ``--run-release-gate``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.integration.test_examples_suite import ROOT, passed_count, run_examples

RESULTS = ROOT / "benchmark" / "results"
TRAPS = {"distractor_trap", "regression_trap"}
RECORD_RUNS = int(os.environ.get("HW_GATE_RECORD_RUNS", "20"))


def _eval_runs(system: str) -> list[dict[str, Any]]:
    combined = json.loads(
        (RESULTS / "eval-combined" / system / "combined.json").read_text(encoding="utf-8")
    )
    runs = []
    for run in combined["per_run"]:
        folder = RESULTS.joinpath(*Path(run["folder"]).parts[-2:])
        runs.append(json.loads((folder / "results.json").read_text(encoding="utf-8")))
    return runs


@pytest.mark.integration
def test_invariant_1_no_false_green_on_any_trap_across_eval_runs() -> None:
    runs = _eval_runs("healwright")
    assert len(runs) >= 3
    assert sum(r["vlm_mode"] == "live" for r in runs) >= 2  # 1 record + 2 live
    for r in runs:
        traps = [row for row in r["rows"] if row["class"] in TRAPS]
        assert len(traps) == 10
        assert [row["id"] for row in traps if row["outcome"] == "false_heal"] == []
        for row in traps:
            if row["class"] == "regression_trap":
                assert not [e for e in row.get("events", []) if e["status"] == "healed"], row["id"]
        assert r["aggregate"]["false_heals_on_traps"] == 0


def _assert_green(result: subprocess.CompletedProcess[str], label: str) -> None:
    out = result.stdout[-3000:] + result.stderr[-1500:]
    assert result.returncode == 0, f"{label}\n{out}"
    assert passed_count(result.stdout) >= 30, label
    assert " failed" not in result.stdout, f"{label}\n{out}"


@pytest.mark.integration
@pytest.mark.release_gate
@pytest.mark.timeout(60 * 60)
def test_invariant_2_no_false_red(tmp_path: Path) -> None:
    baselines = tmp_path / "baselines"
    record = {
        "HEALWRIGHT_MODE": "record",
        "HEALWRIGHT_BASELINE_DIR": str(baselines),
        "HEALWRIGHT_ARTIFACT_DIR": str(tmp_path / "artifacts"),
    }
    for i in range(RECORD_RUNS):
        _assert_green(run_examples(env=record), f"record run {i + 1}/{RECORD_RUNS}")

    blocked = tmp_path / "artifacts-blocked"
    blocked.write_text("a file where the run folder should be", encoding="utf-8")
    _assert_green(
        run_examples(env={**record, "HEALWRIGHT_ARTIFACT_DIR": str(blocked)}),
        "fault: run folder not writable",
    )

    corrupted = 0
    for f in baselines.rglob("*.json"):
        f.write_text("{truncated", encoding="utf-8")
        corrupted += 1
    assert corrupted >= 30
    _assert_green(run_examples(env=record), "fault: corrupt baselines")

    faulty = run_examples("-p", "tests.fixtures.recorder_fault", env=record)
    _assert_green(faulty, "fault: recorder throws")
    errors = re.search(r"(\d+) recording errors", faulty.stdout)
    assert errors is not None
    assert int(errors.group(1)) > 0


def _git(cwd: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[bytes]:
    # Bytes, not text=True: on Windows text-mode stdin turns "\n" into "\r\n", and the patch
    # then no longer matches the LF test files (production code pipes bytes the same way).
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=cwd,
        input=stdin.encode("utf-8") if stdin is not None else None,
        capture_output=True,
        check=False,
    )


@pytest.mark.integration
@pytest.mark.release_gate
@pytest.mark.timeout(60 * 60)
def test_invariant_3_every_dev_heal_patch_applies_and_passes_natively(tmp_path: Path) -> None:
    import benchmark.run as bench
    from chaos_store.scenario import iter_scenarios
    from chaos_store.serve import serve_in_thread

    healable = [
        s
        for s in iter_scenarios()
        if s.split == "dev" and s.expected and s.expected.outcome == "healed"
    ]
    assert len(healable) >= 10
    checked = 0
    with serve_in_thread(control=True) as store:
        for n, s in enumerate(healable):
            work = tmp_path / s.id
            row = bench.run_scenario(s, "healwright", store, work, {}, "replay", n)
            assert row["outcome"] == "true_heal", (s.id, row)
            diffs = [
                e["diff"]
                for e in bench.heal_events(work, set())
                if e["decision"]["status"] == "healed" and e.get("diff")
            ]
            assert diffs, s.id
            for diff in diffs:
                assert _git(ROOT, "apply", "--check", "-", stdin=diff).returncode == 0, (
                    s.id,
                    diff,
                )  # clean checkout
                copy = tmp_path / f"copy-{s.id}"
                shutil.copytree(
                    ROOT / "examples",
                    copy / "examples",
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
                _git(copy, "init", "-q")
                applied = _git(copy, "apply", "-", stdin=diff)
                assert applied.returncode == 0, (s.id, applied.stderr)
                bench.control(store, "reset")
                bench.control(
                    store, "scenario", content=s.model_dump_json(by_alias=True, exclude_none=True)
                )
                try:
                    env = {
                        **os.environ,
                        "PYTHONPATH": str(ROOT),
                        "HEALWRIGHT_MODE": "off",
                        "CHAOS_BASE_URL": store,
                        "CHAOS_SESSION": f"gate-{n}",
                    }
                    native = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            s.test or "",
                            "-q",
                            "-p",
                            "no:cacheprovider",
                            "-p",
                            "no:healwright",
                        ],
                        cwd=copy,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=300,
                        check=False,
                    )
                finally:
                    bench.control(store, "reset")
                assert native.returncode == 0, (s.id, native.stdout[-2000:])
                checked += 1
    assert checked >= len(healable)
