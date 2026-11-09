"""Benchmark classification and metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmark.run import ROOT, SMOKE_10, aggregate, classify, patch_check, summary_md
from chaos_store.scenario import Scenario, iter_scenarios

pytestmark = pytest.mark.unit

BY_ID = {s.id: s for s in iter_scenarios()}


def sc(klass: str, action: str = "confirm_order") -> Scenario:
    outcome = {"distractor_trap": "red_or_true_heal", "regression_trap": "red"}.get(klass, "healed")
    return Scenario.model_validate(
        {
            "id": "x",
            "class": klass,
            "test": "t.py::t",
            "expected": {"outcome": outcome, "action_id": action},
        }
    )


CLEAN = ["add_to_cart", "create_order", "confirm_order"]


@pytest.mark.parametrize(
    ("klass", "passed", "fired", "healed", "expected"),
    [
        ("id_rename", True, CLEAN, True, "true_heal"),
        ("id_rename", False, ["add_to_cart", "create_order"], False, "red"),
        ("id_rename", True, ["add_to_cart", "create_order", "cancel_order"], True, "false_heal"),
        ("distractor_trap", False, ["add_to_cart", "create_order"], False, "red"),
        ("distractor_trap", True, CLEAN, True, "true_heal"),
        (
            "distractor_trap",
            False,
            ["add_to_cart", "create_order", "cancel_order"],
            True,
            "false_heal",
        ),
        ("regression_trap", False, ["add_to_cart", "create_order"], False, "red"),
        ("regression_trap", False, ["add_to_cart", "create_order"], True, "false_heal"),  # any heal
        ("regression_trap", True, ["add_to_cart", "create_order"], False, "false_heal"),
    ],
)
def test_classify(klass: str, passed: bool, fired: list[str], healed: bool, expected: str) -> None:
    assert classify(sc(klass), passed, fired, CLEAN, healed) == expected


def row(
    klass: str, outcome: str, status: str | None = None, tier: int = 1, ms: float = 900.0
) -> dict[str, Any]:
    events = [{"status": status, "tier": tier, "total_ms": ms, "reason": ""}] if status else []
    return {"id": f"{klass}-{outcome}", "class": klass, "outcome": outcome, "events": events}


def test_aggregate_metrics() -> None:
    rows = [
        row("id_rename", "true_heal", "healed", 1, 800),
        row("css_refactor", "true_heal", "healed", 2, 3000),
        row("copy_drift", "red", "needs_human"),
        row("distractor_trap", "red", "needs_human"),
        row("regression_trap", "false_heal", "healed", 1, 700),
        row("id_rename", "error"),
    ]
    agg = aggregate(rows)
    assert agg["healable"] == 4
    assert agg["true_heals"] == 2
    assert agg["true_heal_rate"] == 0.5
    assert agg["false_heals_on_traps"] == 1
    assert agg["silent_false_heal_rate"] == round(1 / 6, 4)
    assert agg["precision_of_accepted_heals"] == round(2 / 3, 4)
    assert agg["tier1_share_of_heals"] == round(2 / 3, 4)
    assert agg["latency_ms"]["tier2"]["n"] == 1
    assert agg["errors"] == 1
    md = summary_md(
        {
            "system": "s",
            "split": "dev",
            "runs": 1,
            "vlm_mode": "replay",
            "finished_at": "t",
            "rows": rows,
            "aggregate": agg,
        }
    )
    assert "Do not edit by hand" in md
    assert "2/4 = 0.5" in md
    assert agg["patches"] == {"healed_events": 3, "apply_check_ok": 0, "no_patch": 0, "failed": 0}


def test_patches_are_counted_per_healed_event() -> None:
    rows = [row("id_rename", "true_heal", "healed"), row("css_refactor", "true_heal", "healed")]
    rows[0]["events"][0]["patch"] = "ok"
    rows[1]["events"][0]["patch"] = "failed: corrupt patch"
    agg = aggregate(rows)
    assert agg["patches"] == {"healed_events": 2, "apply_check_ok": 1, "no_patch": 0, "failed": 1}


def test_patch_check_runs_git_apply_check_against_the_repo() -> None:
    assert patch_check({"diff": None}) == "no_patch"
    assert patch_check({"diff": "not a patch\n"}).startswith("failed")
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[:3]
    context = "".join(f" {line}\n" for line in lines[1:])  # git anchors hunks by context
    good = f"--- a/README.md\n+++ b/README.md\n@@ -1,3 +1,3 @@\n-{lines[0]}\n+changed\n{context}"
    assert patch_check({"diff": good}) == "ok"


def test_smoke_10_covers_every_class_and_both_trap_types() -> None:
    classes = {BY_ID[i].klass for i in SMOKE_10}
    assert len(SMOKE_10) == 10
    assert classes == {
        "id_rename",
        "css_refactor",
        "copy_drift",
        "tag_to_aria",
        "layout_move",
        "i18n",
        "distractor_trap",
        "regression_trap",
    }


def test_provider_calls_are_counted_from_the_json_log(tmp_path: Path) -> None:
    from benchmark.run import provider_calls

    logs = tmp_path / "artifacts" / "logs"
    logs.mkdir(parents=True)
    lines = [
        {"msg": "provider call groq qwen -> 200", "provider": "groq", "error_code": "200"},
        {"msg": "provider call groq qwen -> 429", "provider": "groq", "error_code": "429"},
        {"msg": "provider call groq qwen -> 200", "provider": "groq", "error_code": "200"},
        {"msg": "api GET /x -> 200", "request_id": "r"},
    ]
    (logs / "healwright.log").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\nnot json\n", encoding="utf-8"
    )
    assert provider_calls(tmp_path) == {"groq": {"200": 2, "429": 1}}


def test_descendants_of_walks_the_parent_chain() -> None:
    from benchmark.run import descendants_of

    procs = [
        {"ProcessId": 10, "ParentProcessId": 1, "Name": "python.exe", "CommandLine": "pytest"},
        {"ProcessId": 11, "ParentProcessId": 10, "Name": "node.exe", "CommandLine": "driver"},
        {"ProcessId": 12, "ParentProcessId": 11, "Name": "chrome.exe", "CommandLine": None},
        {"ProcessId": 13, "ParentProcessId": 1, "Name": "other.exe", "CommandLine": ""},
    ]
    assert [p["name"] for p in descendants_of(10, procs)] == ["node.exe", "chrome.exe"]
    assert descendants_of(13, procs) == []
    # orphans: chain broken (parent 99 gone), created after the start -> listed, not in tree
    procs += [
        {"ProcessId": 20, "ParentProcessId": 99, "Name": "node.exe", "Created": 5000},
        {"ProcessId": 21, "ParentProcessId": 1, "Name": "old.exe", "Created": 100},
        {
            "ProcessId": 30,
            "ParentProcessId": 1,
            "Name": "powershell.exe",
            "Created": 6000,
            "CommandLine": "Get-CimInstance Win32_Process",
        },
        {"ProcessId": 31, "ParentProcessId": 30, "Name": "conhost.exe", "Created": 6000},
    ]
    late = descendants_of(13, procs, since_ms=1000)
    assert [(p["name"], p["in_tree"]) for p in late] == [("node.exe", False)]


@pytest.mark.integration
def test_pytest_run_ki10_capture_when_a_grandchild_holds_the_pipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hang mechanism: pytest exits, a grandchild keeps stdout open. The runner
    records that (instead of blocking until the grandchild exits) and raises."""
    import os
    import subprocess
    import sys
    import time

    import benchmark.run as run

    monkeypatch.setattr(run, "KI10_DIR", tmp_path / "diag")
    monkeypatch.setattr(run, "POST_KILL_WAIT_S", 1)
    test = tmp_path / "test_leak.py"
    test.write_text(
        "import subprocess, sys\n"
        "def test_leak():\n"
        "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],"
        " stdout=sys.stdout)\n",
        encoding="utf-8",
    )
    env = {**os.environ, "__args": "-s -p no:timeout"}
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as info:
        run.pytest_run(str(test), env, timeout=6)
    assert time.monotonic() - t0 < 18  # bounded, not the grandchild's 20 s
    (diag,) = (tmp_path / "diag").glob("*.json")
    record = json.loads(diag.read_text(encoding="utf-8"))
    assert record["pytest_exited"] is True
    assert record["pytest_returncode"] == 0
    assert record["pipes_still_open_at_timeout"] is True
    assert "1 passed" in record["stdout_tail"]
    if sys.platform == "win32":
        assert any(d["name"] == "python.exe" for d in record["descendants_at_timeout"])
    assert "pipes_open=True" in str(info.value.stderr)
