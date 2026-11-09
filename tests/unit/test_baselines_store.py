"""Baseline store: paths, merging history, atomic write-if-changed, corruption."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healwright.errors import BaselineCorrupt
from healwright.models import PostConditionSignature
from healwright.store.baselines import (
    ObservedStep,
    baseline_path,
    load,
    merge_observed,
    record_passing_run,
)
from tests import factories as f

pytestmark = pytest.mark.unit

NODE = "examples/test_cart.py::test_add_to_cart[chromium]"


def obs(**kw: object) -> PostConditionSignature:
    return f.contract(observations=1, strength="weak", **kw)


def step(occurrence: int = 0, **kw: object) -> ObservedStep:
    return ObservedStep(
        key=f.step_key(test_nodeid=NODE, occurrence=occurrence),
        fingerprint=f.fingerprint(),
        observation=obs(**kw),
        source_line=8,
    )


def test_baseline_path_layout_and_safety(tmp_path: Path) -> None:
    p = baseline_path(tmp_path, NODE)
    assert p == tmp_path / "examples" / "test_cart.py" / "test_add_to_cart[chromium].json"
    evil = baseline_path(tmp_path, "../../etc/x.py::t<>:|?*")
    assert tmp_path in evil.parents
    assert ".." not in evil.parts
    assert all(c not in evil.name for c in "<>:|?*")


def test_merge_rolls_history_to_three_and_strengthens() -> None:
    t0 = datetime(2026, 11, 6, tzinfo=UTC)
    first = merge_observed(NODE, None, [step()], now=t0)
    assert first.steps[0].baseline.contract.strength == "weak"  # one observation
    second = merge_observed(NODE, first, [step()], now=t0)
    assert second.steps[0].baseline.contract.strength == "strong"
    assert second.steps[0].baseline.contract.observations == 2
    third = merge_observed(NODE, second, [step()], now=t0)
    fourth = merge_observed(NODE, third, [step()], now=t0)
    assert len(fourth.steps[0].history) == 3


def test_unchanged_run_keeps_original_timestamp() -> None:
    t0, t1 = datetime(2026, 11, 6, tzinfo=UTC), datetime(2026, 11, 7, tzinfo=UTC)
    f1 = merge_observed(NODE, None, [step()], now=t0)
    f2 = merge_observed(NODE, f1, [step()], now=t0)
    f3 = merge_observed(NODE, f2, [step()], now=t0)
    f4 = merge_observed(NODE, f3, [step()], now=t1)
    assert f4 == f3
    assert f4.steps[0].baseline.recorded_at == t0


def test_steps_without_fingerprint_are_skipped_and_stale_steps_dropped() -> None:
    existing = merge_observed(NODE, None, [step(0), step(1)])
    missing_fp = ObservedStep(f.step_key(test_nodeid=NODE), None, obs(), 8)
    again = merge_observed(NODE, existing, [missing_fp, step(1)])
    assert [s.baseline.key.occurrence for s in again.steps] == [1]


def test_record_passing_run_writes_only_on_change(tmp_path: Path) -> None:
    assert record_passing_run(tmp_path, NODE, [step()]) is True
    path = baseline_path(tmp_path, NODE)
    assert path.is_file()
    for _ in range(2):
        assert record_passing_run(tmp_path, NODE, [step()]) is True  # history grows to 3
    before = path.read_bytes()
    assert record_passing_run(tmp_path, NODE, [step()]) is False  # stable: no rewrite
    assert path.read_bytes() == before
    assert b"\r\n" not in before
    data = json.loads(before)
    assert data["schema_version"] == 1
    assert data["steps"][0]["baseline"]["contract"]["strength"] == "strong"
    assert not list(path.parent.glob(".tmp-*"))


def test_record_with_nothing_usable_writes_nothing(tmp_path: Path) -> None:
    empty = ObservedStep(f.step_key(test_nodeid=NODE), None, None, None)
    assert record_passing_run(tmp_path, NODE, [empty]) is False
    assert not baseline_path(tmp_path, NODE).exists()


def test_load_missing_unknown_and_corrupt(tmp_path: Path) -> None:
    path = baseline_path(tmp_path, NODE)
    assert load(path) is None
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version": 99, "steps": []}', encoding="utf-8")
    assert load(path) is None  # unknown schema version = missing, with a warning
    path.write_text('{"schema_version": 1, "test_nod', encoding="utf-8")
    with pytest.raises(BaselineCorrupt):
        load(path)
    path.write_text(
        '{"schema_version": 1, "test_nodeid": "x", "steps": [{"bad": 1}]}', encoding="utf-8"
    )
    with pytest.raises(BaselineCorrupt):
        load(path)


def test_corrupt_file_is_replaced_by_fresh_recording(tmp_path: Path) -> None:
    path = baseline_path(tmp_path, NODE)
    path.parent.mkdir(parents=True)
    path.write_text("{truncated", encoding="utf-8")
    assert record_passing_run(tmp_path, NODE, [step()]) is True
    loaded = load(path)
    assert loaded is not None
    assert loaded.steps[0].baseline.contract.observations == 1
