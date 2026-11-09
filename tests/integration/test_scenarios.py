"""Scenario files are well-formed, and each one really breaks its referenced test natively."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chaos_store.scenario import SCENARIO_DIR, Scenario, iter_scenarios
from tests.conftest import LiveStore

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = iter_scenarios()
FILES = sorted(SCENARIO_DIR.rglob("*.yaml"))


def _test_exists(node_id: str) -> bool:
    path, _, name = node_id.partition("::")
    file = ROOT / path
    if not file.is_file():
        return False
    tree = ast.parse(file.read_text(encoding="utf-8"))
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body)


DEV = [s for s in SCENARIOS if s.split == "dev"]
EVAL = [s for s in SCENARIOS if s.split == "eval"]
EVAL_COUNTS = {
    "id_rename": 8,
    "css_refactor": 8,
    "copy_drift": 7,
    "tag_to_aria": 7,
    "layout_move": 6,
    "i18n": 4,
    "distractor_trap": 5,
    "regression_trap": 5,
}


def _counts(scenarios: list[Scenario]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in scenarios:
        assert s.klass is not None
        counts[s.klass] = counts.get(s.klass, 0) + 1
    return counts


def test_dev_split_has_two_scenarios_per_class() -> None:
    assert _counts(DEV) == dict.fromkeys(EVAL_COUNTS, 2)
    assert len(DEV) == 16


def test_eval_split_counts() -> None:
    """50 scenarios in the proposal's counts (40 healable + 10 traps)."""
    assert _counts(EVAL) == EVAL_COUNTS
    assert len(EVAL) == 50


def test_dev_and_eval_never_share_a_test_and_mutation() -> None:
    def fingerprint(s: Scenario) -> tuple[str | None, str]:
        return s.test, s.mutation.model_dump_json()

    assert not {fingerprint(s) for s in DEV} & {fingerprint(s) for s in EVAL}


def test_eval_set_is_frozen() -> None:
    """Any edit to an eval file must be deliberate: it changes the freeze manifest."""
    import hashlib
    import json

    manifest = json.loads((ROOT / "benchmark" / "eval_freeze.json").read_text(encoding="utf-8"))
    files = sorted((SCENARIO_DIR / "eval").glob("*.yaml"))
    actual = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    assert actual == manifest["files"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_scenario_file_is_consistent(path: Path) -> None:
    from chaos_store.scenario import parse_scenario_yaml

    s = parse_scenario_yaml(path.read_text(encoding="utf-8"))
    assert s.id == path.stem
    assert s.split == path.parent.name
    assert s.test is not None
    assert _test_exists(s.test), s.test
    assert s.expected is not None
    assert s.expected.action_id
    expected_outcome = {
        "distractor_trap": "red_or_true_heal",
        "regression_trap": "red",
    }.get(s.klass or "", "healed")
    assert s.expected.outcome == expected_outcome


def test_scenario_ids_are_unique() -> None:
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def _run_native(
    store: LiveStore, scenario: Scenario, session: str, *, expect_break: bool
) -> subprocess.CompletedProcess[str]:
    assert scenario.test is not None
    env = {**os.environ, "CHAOS_BASE_URL": store.base_url, "CHAOS_SESSION": session}
    env.pop("CHAOS_ACTION_TIMEOUT_MS", None)
    if expect_break:
        # short timeout only where a broken selector is EXPECTED; the clean run keeps
        # Playwright's default so a busy machine cannot make it fail spuriously
        env["CHAOS_ACTION_TIMEOUT_MS"] = "2000"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            scenario.test,
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:healwright",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.slow
@pytest.mark.timeout(180)
@pytest.mark.parametrize("scenario", DEV, ids=lambda s: s.id)
def test_scenario_breaks_its_test_natively(store: LiveStore, scenario: Scenario) -> None:
    """Unmutated: the referenced test passes. Mutated: it fails and never fires the expected action.
    (Dev split here; the 50 eval scenarios get the same check in tests/e2e/.)"""
    check_breaks_natively(store, scenario)


def check_breaks_natively(store: LiveStore, scenario: Scenario) -> None:
    assert scenario.expected is not None
    clean = _run_native(store, scenario, "scn-clean-0001", expect_break=False)
    out = clean.stdout[-2500:] + clean.stderr[-1000:]
    assert clean.returncode == 0, f"clean run failed: {out}"
    clean_ids = [a["action_id"] for a in store.actions("scn-clean-0001")]
    assert scenario.expected.action_id in clean_ids, f"clean actions {clean_ids}: {out}"

    store.set_scenario(scenario.model_dump_json(by_alias=True, exclude_none=True))
    broken = _run_native(store, scenario, "scn-broken-0001", expect_break=True)
    out = broken.stdout[-2500:] + broken.stderr[-1000:]
    assert broken.returncode != 0, f"{scenario.id} did not break {scenario.test}: {out}"
    assert "Timeout" in broken.stdout, f"broken for another reason: {out}"
    broken_ids = [a["action_id"] for a in store.actions("scn-broken-0001")]
    assert scenario.expected.action_id not in broken_ids, f"broken actions {broken_ids}: {out}"
