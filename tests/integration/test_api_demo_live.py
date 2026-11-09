"""The real demo runner end to end: Chaos Store, record
baselines, break, heal in replay mode, heal event visible through the API."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from healwright.api import API, Paths, create_app
from healwright.api.demo import DemoRunner

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.timeout(300)
def test_demo_run_heals_and_exposes_the_event(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    paths = Paths(
        ROOT, artifacts, ROOT / "benchmark" / "results", tmp_path / "dist", tmp_path / "demo"
    )
    runner = DemoRunner(artifacts, tmp_path / "demo")
    with TestClient(create_app(paths, runner)) as client:
        started = client.post(f"{API}/demo/runs", json={"scenario_id": "dev-01-id-rename"})
        assert started.status_code == 202
        run_id = started.json()["id"]
        stages = set()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            state = client.get(f"{API}/demo/runs/{run_id}").json()
            stages.add(state["stage"])
            if not state["running"]:
                break
            time.sleep(1)
        shots = {
            name: client.get(f"{API}/demo/runs/{run_id}/shots/{name}")
            for name in ("clean", "healed")
        }
    assert state["stage"] == "done", state
    assert set(state["shots"]) == {"clean", "healed"}, state
    for res in shots.values():
        assert res.status_code == 200
        assert res.content[1:4] == b"PNG"
    assert state["outcome"] == "true_heal", state
    assert "add_to_cart" in state["fired_actions"]
    assert [e["decision"]["status"] for e in state["heal_events"]] == ["healed"]
    assert "running_test" in stages or "recording_baselines" in stages
