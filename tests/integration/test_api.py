"""Triage API: every endpoint and every error code.

In-process TestClient against temporary run folders and a throwaway git repo. The demo
runner is replaced by a fake (the real one is exercised by test_api_demo_live.py).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ulid import ULID

from healwright.api import API, Paths, create_app
from healwright.api.demo import DemoRun, DemoRunner
from healwright.api.errors import MAX_BODY_BYTES
from healwright.cli import main as cli_main
from healwright.models import HealEvent
from tests.factories import decision, heal_event

pytestmark = pytest.mark.integration

SOURCE = 'def test_x(page):\n    page.goto("/")\n    page.click("#add-to-cart")\n'
HEALED = "def test_x(page):\n    page.goto(\"/\")\n    page.get_by_test_id('add-basket').click()\n"
PNG = b"\x89PNG\r\n\x1a\nfake"
TOKEN = "test-token-not-a-secret"


def make_diff(old: str, new: str, rel: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


class FakeDemo(DemoRunner):
    """Runs instantly, or blocks until ``release`` is set (to test DEMO_BUSY)."""

    def __init__(self, root: Path) -> None:
        super().__init__(root, root / "demo")
        self.release = threading.Event()
        self.release.set()
        self.fail = False

    def _steps(self, run: DemoRun) -> None:
        run.stage = "running_test"
        self.release.wait(10)
        if self.fail:
            raise RuntimeError("boom")
        run.outcome = "true_heal"
        run.test_passed = True


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    repo = tmp_path / "repo"
    (repo / "examples").mkdir(parents=True)
    test_file = repo / "examples" / "test_x.py"
    test_file.write_bytes(SOURCE.encode("utf-8"))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    artifacts = tmp_path / "artifacts"
    run_a, run_b = str(ULID()), str(ULID())
    ev_patch, ev_none, ev_tier2 = str(ULID()), str(ULID()), str(ULID())
    sha = hashlib.sha256(test_file.read_bytes()).hexdigest()
    events_a = [
        heal_event(
            id=ev_patch,
            run_id=run_a,
            artifacts={"before": "before.png", "patch": "patch.diff"},
            diff=make_diff(SOURCE, HEALED, "examples/test_x.py"),
            source_sha256=sha,
        ),
        heal_event(
            id=ev_none,
            run_id=run_a,
            decision=decision(
                status="needs_human",
                tier=None,
                chosen=None,
                locator=None,
                verification=None,
                reason="tier 1 not confident",
            ),
            artifacts={},
            diff=None,
            source_sha256=None,
        ),
    ]
    events_b = [
        heal_event(
            id=ev_tier2,
            run_id=run_b,
            decision=decision(tier=2),
            artifacts={},
            diff=None,
            source_sha256=None,
        )
    ]
    for run_id, events in ((run_a, events_a), (run_b, events_b)):
        folder = artifacts / "runs" / run_id
        folder.mkdir(parents=True)
        lines = [e.model_dump_json() for e in events]
        if run_id == run_b:
            lines.append("{not json")  # corrupt line: skipped, never fatal
        (folder / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    art = artifacts / "runs" / run_a / "artifacts" / ev_patch
    art.mkdir(parents=True)
    (art / "before.png").write_bytes(PNG)
    (art / "patch.diff").write_text(events_a[0].diff or "", encoding="utf-8")

    results = tmp_path / "results"
    bench = results / "2026-11-07" / "healwright-dev"
    bench.mkdir(parents=True)
    (bench / "results.json").write_text(
        json.dumps(
            {
                "system": "healwright",
                "split": "dev",
                "vlm_mode": "replay",
                "runs": 1,
                "rows": [],
                "aggregate": {"true_heals": 12},
            }
        ),
        encoding="utf-8",
    )
    (results / "2026-11-07" / "not-a-bench").mkdir()

    paths = Paths(
        repo_root=repo,
        artifact_root=artifacts,
        results_root=results,
        frontend_dist=tmp_path / "dist",
        demo_work=tmp_path / "demo",
    )
    demo = FakeDemo(artifacts)
    client = TestClient(create_app(paths, demo))
    return {
        "client": client,
        "repo": repo,
        "test_file": test_file,
        "paths": paths,
        "demo": demo,
        "run_a": run_a,
        "run_b": run_b,
        "ev_patch": ev_patch,
        "ev_none": ev_none,
        "ev_tier2": ev_tier2,
        "sha": sha,
    }


def err(res: Any, status: int, code: str) -> dict[str, Any]:
    assert res.status_code == status, res.text
    body: dict[str, Any] = res.json()["error"]
    assert body["code"] == code
    assert set(body) <= {"code", "message", "details", "request_id"}
    assert body["request_id"] == res.headers["X-Request-ID"]
    assert "Traceback" not in res.text
    return body


def accept(c: TestClient, event_id: str) -> None:
    res = c.post(f"{API}/heal-events/{event_id}/triage", json={"decision": "accepted"})
    assert res.status_code == 200, res.text


# ------------------------------------------------------------------ health, ids, envelope


def test_health_and_ready(env: dict[str, Any]) -> None:
    c = env["client"]
    assert c.get(f"{API}/health").json()["status"] == "ok"
    res = c.get(f"{API}/ready")
    assert res.status_code == 200
    assert res.json()["checks"] == {"artifact_root": True, "results_root": True, "git": True}


def test_ready_is_503_when_the_artifact_dir_is_missing(env: dict[str, Any]) -> None:
    p: Paths = env["paths"]
    broken = Paths(
        p.repo_root, p.artifact_root / "nope", p.results_root, p.frontend_dist, p.demo_work
    )
    res = TestClient(create_app(broken, env["demo"])).get(f"{API}/ready")
    assert res.status_code == 503
    assert res.json()["checks"]["artifact_root"] is False


def test_request_id_is_echoed_or_generated_and_logged(
    env: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    c = env["client"]
    with caplog.at_level(logging.INFO, logger="healwright.api"):
        res = c.get(f"{API}/health", headers={"X-Request-ID": "abc-123"})
    assert res.headers["X-Request-ID"] == "abc-123"
    assert any(getattr(r, "request_id", None) == "abc-123" for r in caplog.records)
    generated = c.get(f"{API}/health", headers={"X-Request-ID": "bad id <script>"})
    assert len(generated.headers["X-Request-ID"]) == 26


def test_unknown_api_route_is_not_found(env: dict[str, Any]) -> None:
    err(env["client"].get(f"{API}/nope"), 404, "NOT_FOUND")


def test_internal_error_is_500_without_a_trace(
    env: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    demo: FakeDemo = env["demo"]

    def explode(run_id: str) -> DemoRun:
        raise RuntimeError("secret internal detail")

    demo.get = explode  # type: ignore[method-assign]
    client = TestClient(env["client"].app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="healwright.api"):
        res = client.get(f"{API}/demo/runs/{ULID()}")
    body = err(res, 500, "INTERNAL_ERROR")
    assert "secret" not in res.text
    logged = [r for r in caplog.records if r.exc_info]  # the trace is LOGGED, with the id
    assert logged
    assert body["request_id"] in logged[-1].getMessage()


# ------------------------------------------------------------------ VALIDATION_ERROR (422)


@pytest.mark.parametrize(
    "path",
    [
        "/runs/not-a-ulid",
        "/heal-events/not-a-ulid",
        "/heal-events/not-a-ulid/patch",
        "/demo/runs/not-a-ulid",
        "/benchmarks/bad-id",
        "/runs?cursor=x",
        "/runs?limit=0",
        "/heal-events?cursor=x",
        "/heal-events?run_id=x",
        "/heal-events?status=bogus",
        "/heal-events?tier=3",
    ],
)
def test_validation_errors(env: dict[str, Any], path: str) -> None:
    body = err(env["client"].get(f"{API}{path}"), 422, "VALIDATION_ERROR")
    assert body["details"]["errors"]


def test_validation_errors_on_bodies_and_headers(env: dict[str, Any]) -> None:
    c = env["client"]
    ev = env["ev_patch"]
    url = f"{API}/heal-events/{ev}/triage"
    err(c.post(url, json={"decision": "maybe"}), 422, "VALIDATION_ERROR")
    err(c.post(url, json={"decision": "accepted", "note": "x" * 1001}), 422, "VALIDATION_ERROR")
    err(c.post(url, json={"decision": "accepted", "extra": 1}), 422, "VALIDATION_ERROR")
    err(c.post(f"{API}/demo/runs", json={"scenario_id": "../x"}), 422, "VALIDATION_ERROR")
    body = err(c.post(f"{API}/heal-events/{ev}/patch/apply"), 422, "VALIDATION_ERROR")
    assert body["details"]["errors"][0]["loc"] == ["header", "Idempotency-Key"]


# ------------------------------------------------------------------ runs


def test_runs_newest_first_with_cursor(env: dict[str, Any]) -> None:
    c = env["client"]
    first = c.get(f"{API}/runs", params={"limit": 1}).json()
    assert [r["run_id"] for r in first["items"]] == [env["run_b"]]
    assert first["next_cursor"] == env["run_b"]
    second = c.get(f"{API}/runs", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert [r["run_id"] for r in second["items"]] == [env["run_a"]]
    assert second["next_cursor"] is None
    run_a = second["items"][0]
    assert run_a["status_counts"]["healed"] == 1
    assert run_a["status_counts"]["needs_human"] == 1
    assert run_a["tier_counts"] == {"1": 1, "2": 0}


def test_run_detail_and_corrupt_lines(env: dict[str, Any]) -> None:
    c = env["client"]
    run_b = c.get(f"{API}/runs/{env['run_b']}").json()
    assert run_b["skipped_lines"] == 1
    assert [e["id"] for e in run_b["events"]] == [env["ev_tier2"]]
    err(c.get(f"{API}/runs/{ULID()}"), 404, "NOT_FOUND")


# ------------------------------------------------------------------ heal events


def test_heal_event_filters_and_cursor(env: dict[str, Any]) -> None:
    c = env["client"]
    everything = c.get(f"{API}/heal-events").json()["items"]
    assert {e["id"] for e in everything} == {env["ev_patch"], env["ev_none"], env["ev_tier2"]}
    by_status = c.get(f"{API}/heal-events", params={"status": "needs_human"}).json()["items"]
    assert [e["id"] for e in by_status] == [env["ev_none"]]
    by_tier = c.get(f"{API}/heal-events", params={"tier": 2}).json()["items"]
    assert [e["id"] for e in by_tier] == [env["ev_tier2"]]
    by_run = c.get(f"{API}/heal-events", params={"run_id": env["run_a"]}).json()["items"]
    assert len(by_run) == 2
    page = c.get(f"{API}/heal-events", params={"limit": 2}).json()
    rest = c.get(f"{API}/heal-events", params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert len(page["items"]) + len(rest["items"]) == 3
    err(c.get(f"{API}/heal-events", params={"run_id": str(ULID())}), 404, "NOT_FOUND")


def test_heal_event_detail(env: dict[str, Any]) -> None:
    c = env["client"]
    ev = c.get(f"{API}/heal-events/{env['ev_patch']}").json()
    HealEvent.model_validate({k: v for k, v in ev.items() if k not in ("triage", "artifact_urls")})
    assert ev["triage"]["status"] == "pending"
    assert ev["artifact_urls"] == {
        "before": f"{API}/heal-events/{env['ev_patch']}/artifacts/before.png",
        "patch": f"{API}/heal-events/{env['ev_patch']}/artifacts/patch.diff",
    }
    err(c.get(f"{API}/heal-events/{ULID()}"), 404, "NOT_FOUND")


def test_artifacts_are_an_enum_of_file_names(env: dict[str, Any]) -> None:
    c = env["client"]
    ev = env["ev_patch"]
    res = c.get(f"{API}/heal-events/{ev}/artifacts/before.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content == PNG
    assert c.get(f"{API}/heal-events/{ev}/artifacts/patch.diff").status_code == 200
    err(c.get(f"{API}/heal-events/{ev}/artifacts/som.jpg"), 404, "NOT_FOUND")  # not recorded
    err(c.get(f"{API}/heal-events/{ev}/artifacts/before"), 422, "VALIDATION_ERROR")
    err(c.get(f"{API}/heal-events/{ev}/artifacts/events.jsonl"), 422, "VALIDATION_ERROR")
    err(c.get(f"{API}/heal-events/{ev}/artifacts/..%2Fevents.jsonl"), 404, "NOT_FOUND")
    run_dir = env["paths"].artifact_root / "runs" / env["run_a"]
    (run_dir / "artifacts" / ev / "before.png").unlink()
    err(c.get(f"{API}/heal-events/{ev}/artifacts/before.png"), 404, "NOT_FOUND")


def test_patch_view_and_no_patch(env: dict[str, Any]) -> None:
    c = env["client"]
    p = c.get(f"{API}/heal-events/{env['ev_patch']}/patch").json()
    assert p["source_path"] == "examples/test_x.py"
    assert p["source_changed"] is False
    assert p["apply_check"]["ok"] is True
    err(c.get(f"{API}/heal-events/{env['ev_none']}/patch"), 404, "NO_PATCH")


# ------------------------------------------------------------------ triage


def test_triage_same_decision_is_idempotent(env: dict[str, Any]) -> None:
    c = env["client"]
    url = f"{API}/heal-events/{env['ev_patch']}/triage"
    first = c.post(url, json={"decision": "rejected", "note": "looks wrong"})
    assert first.json()["triage"]["status"] == "rejected"
    again = c.post(url, json={"decision": "rejected", "note": "looks wrong"})
    assert again.status_code == 200
    assert again.json()["triage"]["note"] == "looks wrong"


def test_triage_different_decision_is_already_triaged(env: dict[str, Any]) -> None:
    c = env["client"]
    url = f"{API}/heal-events/{env['ev_patch']}/triage"
    accept(c, env["ev_patch"])
    body = err(c.post(url, json={"decision": "rejected"}), 409, "ALREADY_TRIAGED")
    assert body["details"] == {"decision": "accepted"}
    missing = c.post(f"{API}/heal-events/{ULID()}/triage", json={"decision": "accepted"})
    err(missing, 404, "NOT_FOUND")


# ------------------------------------------------------------------ apply


def test_apply_order_and_idempotency(env: dict[str, Any]) -> None:
    c = env["client"]
    ev = env["ev_patch"]
    url = f"{API}/heal-events/{ev}/patch/apply"
    err(c.post(url, headers={"Idempotency-Key": "k1"}), 409, "NOT_ACCEPTED")
    accept(c, ev)
    res = c.post(url, headers={"Idempotency-Key": "k1"})
    assert res.status_code == 200, res.text
    assert res.json()["replayed"] is False
    assert env["test_file"].read_text(encoding="utf-8") == HEALED
    for key in ("k1", "k2"):  # applying again is a no-op, whatever the key
        again = c.post(url, headers={"Idempotency-Key": key})
        assert again.status_code == 200
        assert again.json()["replayed"] is True
    assert env["test_file"].read_text(encoding="utf-8") == HEALED
    assert c.get(f"{API}/heal-events/{ev}").json()["triage"]["status"] == "applied"


def test_apply_source_changed_reports_both_hashes(env: dict[str, Any]) -> None:
    c = env["client"]
    ev = env["ev_patch"]
    accept(c, ev)
    env["test_file"].write_text(SOURCE + "# edited\n", encoding="utf-8")
    res = c.post(f"{API}/heal-events/{ev}/patch/apply", headers={"Idempotency-Key": "k"})
    body = err(res, 409, "SOURCE_CHANGED")
    assert body["message"] == "examples/test_x.py changed after the patch was generated"
    actual = hashlib.sha256(env["test_file"].read_bytes()).hexdigest()
    assert body["details"] == {"expected_sha256": env["sha"], "actual_sha256": actual}
    assert env["test_file"].read_text(encoding="utf-8").endswith("# edited\n")


def test_apply_patch_invalid_and_no_patch(env: dict[str, Any]) -> None:
    """Same SHA as recorded, but a diff whose context does not match: PATCH_INVALID."""
    paths: Paths = env["paths"]
    run_dir = paths.artifact_root / "runs" / env["run_a"]
    bad_id = str(ULID())
    bad = heal_event(
        id=bad_id,
        run_id=env["run_a"],
        artifacts={},
        source_sha256=env["sha"],
        diff=make_diff("something\nelse\n", "x\n", "examples/test_x.py"),
    )
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(bad.model_dump_json() + "\n")
    c = env["client"]
    accept(c, bad_id)
    key = {"Idempotency-Key": "k"}
    err(c.post(f"{API}/heal-events/{bad_id}/patch/apply", headers=key), 422, "PATCH_INVALID")
    no_patch = c.post(f"{API}/heal-events/{env['ev_none']}/patch/apply", headers=key)
    err(no_patch, 404, "NO_PATCH")


def test_cli_apply_shares_the_checks(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(env["repo"])
    monkeypatch.setenv("HEALWRIGHT_ARTIFACT_DIR", str(env["paths"].artifact_root))
    assert cli_main(["apply", env["ev_none"]]) == 1
    assert "NO_PATCH" in capsys.readouterr().err
    assert cli_main(["apply", str(ULID())]) == 1
    assert cli_main(["apply", env["ev_patch"]]) == 0  # the CLI does not require "accepted"
    assert env["test_file"].read_text(encoding="utf-8") == HEALED
    assert cli_main(["apply", env["ev_patch"]]) == 0
    assert "ALREADY_APPLIED" in capsys.readouterr().out


# ------------------------------------------------------------------ 413, 503, 401


def test_payload_too_large(env: dict[str, Any]) -> None:
    big = {"decision": "accepted", "note": "x" * (MAX_BODY_BYTES + 10)}
    res = env["client"].post(f"{API}/heal-events/{env['ev_patch']}/triage", json=big)
    body = err(res, 413, "PAYLOAD_TOO_LARGE")
    assert body["details"] == {"max_bytes": MAX_BODY_BYTES}


def test_storage_unavailable_on_unreadable_or_unwritable_run_folders(env: dict[str, Any]) -> None:
    c = TestClient(env["client"].app, raise_server_exceptions=False)
    run_dir = env["paths"].artifact_root / "runs" / env["run_a"]
    (run_dir / "triage.json").mkdir()  # a directory where a file must be read / written
    res = c.post(f"{API}/heal-events/{env['ev_patch']}/triage", json={"decision": "accepted"})
    err(res, 503, "STORAGE_UNAVAILABLE")
    (run_dir / "triage.json").rmdir()
    events = run_dir / "events.jsonl"
    events.unlink()
    events.mkdir()  # the events file cannot be read
    err(c.get(f"{API}/runs/{env['run_a']}"), 503, "STORAGE_UNAVAILABLE")


def test_bearer_token_guards_every_api_request(env: dict[str, Any]) -> None:
    c = TestClient(create_app(env["paths"], env["demo"], api_token=TOKEN))
    res = c.get(f"{API}/health")
    err(res, 401, "UNAUTHORIZED")
    assert res.headers["WWW-Authenticate"] == "Bearer"
    err(c.get(f"{API}/runs", headers={"Authorization": "Bearer wrong"}), 401, "UNAUTHORIZED")
    ok = c.get(f"{API}/runs", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200
    pre = c.options(  # CORS preflight carries no credentials and must still work
        f"{API}/runs",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert pre.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_serve_refuses_a_non_local_bind_without_a_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HEALWRIGHT_API_TOKEN", raising=False)
    assert cli_main(["serve", "--host", "0.0.0.0"]) == 2
    assert "refusing to bind" in capsys.readouterr().err


# ------------------------------------------------------------------ benchmarks, scenarios


def test_benchmarks(env: dict[str, Any]) -> None:
    c = env["client"]
    items = c.get(f"{API}/benchmarks").json()["items"]
    assert [b["id"] for b in items] == ["2026-11-07--healwright-dev"]
    assert items[0]["aggregate"] == {"true_heals": 12}
    detail = c.get(f"{API}/benchmarks/2026-11-07--healwright-dev").json()
    assert detail["system"] == "healwright"
    err(c.get(f"{API}/benchmarks/2026-11-07--nope-dev"), 404, "NOT_FOUND")


def test_benchmarks_combined(env: dict[str, Any]) -> None:
    c = env["client"]
    results: Path = env["paths"].results_root
    assert c.get(f"{API}/benchmarks/combined").json() == {"systems": [], "scenarios": []}
    run = results / "2026-11-08" / "rawhtml-eval-r1"
    run.mkdir(parents=True)
    rows = [
        {"id": "eval-01", "class": "id_rename", "expected": "true_heal", "outcome": "true_heal"},
        {"id": "eval-02", "class": "id_rename", "expected": "true_heal", "outcome": "error"},
        {"id": "eval-48", "class": "regression_trap", "expected": "red", "outcome": "false_heal"},
    ]
    (run / "results.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    combined = results / "eval-combined" / "rawhtml"
    combined.mkdir(parents=True)
    per_run = [
        {"folder": "benchmark/results/2026-11-08/rawhtml-eval-r1", "vlm_mode": "record"},
        {"folder": "../../etc/passwd", "vlm_mode": "live"},  # never followed
    ]
    summary = {"true_heal_rate": {"values": [1.0], "mean": 1.0, "min": 1.0, "max": 1.0}}
    (combined / "combined.json").write_text(
        json.dumps(
            {
                "system": "rawhtml",
                "split": "eval",
                "runs": 1,
                "per_run": per_run,
                "summary": summary,
            }
        ),
        encoding="utf-8",
    )
    body = c.get(f"{API}/benchmarks/combined").json()
    (sys_,) = body["systems"]
    assert sys_["summary"] == summary
    assert [r["id"] for r in sys_["per_run"]] == ["2026-11-08--rawhtml-eval-r1"]
    assert sys_["patches"] == {"healed_events": 0, "apply_check_ok": 0, "no_patch": 0, "failed": 0}
    assert sys_["per_run"][0]["false_heals_on_traps"] is None  # fixture has no aggregate
    assert sys_["by_class"] == {
        "id_rename": {"scored": 1, "true_heal": 1, "false_heal": 0, "red": 0},
        "regression_trap": {"scored": 1, "true_heal": 0, "false_heal": 1, "red": 0},
    }
    assert [(s["id"], s["outcomes"]) for s in body["scenarios"]] == [
        ("eval-01", {"rawhtml": ["true_heal"]}),
        ("eval-02", {"rawhtml": ["error"]}),
        ("eval-48", {"rawhtml": ["false_heal"]}),
    ]


def test_benchmarks_combined_matches_the_committed_eval_summary() -> None:
    """The real eval-combined data: rates pass through exactly as combine wrote them."""
    from healwright.api.app import combined_view

    root = Path(__file__).resolve().parents[2] / "benchmark" / "results"
    body = combined_view(root)
    by_system = {s["system"]: s for s in body["systems"]}
    assert set(by_system) == {
        "native",
        "greedy",
        "tier1_only",
        "healwright",
        "healwright_noverify",
        "rawhtml",
    }
    raw = by_system["rawhtml"]["summary"]["true_heal_rate"]
    assert (raw["mean"], raw["min"], raw["max"]) == (0.95, 0.925, 0.975)
    assert len(by_system["healwright"]["per_run"]) == 3
    assert len(body["scenarios"]) == 50
    hw = by_system["healwright"]
    assert hw["patches"]["healed_events"] == hw["patches"]["apply_check_ok"] > 0
    # verifier experiment: same recorded Tier-2 answers (run 1), verifier on vs off
    assert hw["per_run"][0]["false_heals_on_traps"] == 0
    assert by_system["healwright_noverify"]["per_run"][0]["false_heals_on_traps"] == 3


def test_scenarios_are_dev_only(env: dict[str, Any]) -> None:
    items = env["client"].get(f"{API}/scenarios").json()["items"]
    assert len(items) == 16
    assert all(i["id"].startswith("dev-") for i in items)


# ------------------------------------------------------------------ demo


def _wait(c: TestClient, run_id: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for _ in range(100):
        state = c.get(f"{API}/demo/runs/{run_id}").json()
        if not state["running"]:
            break
        threading.Event().wait(0.05)
    return state


def test_demo_run_lifecycle_and_busy(env: dict[str, Any]) -> None:
    c = env["client"]
    demo: FakeDemo = env["demo"]
    demo.release.clear()
    res = c.post(f"{API}/demo/runs", json={"scenario_id": "dev-07-distractor"})
    assert res.status_code == 202
    run_id = res.json()["id"]
    busy = c.post(f"{API}/demo/runs", json={"scenario_id": "dev-01-id-rename"})
    err(busy, 409, "DEMO_BUSY")
    demo.release.set()
    state = _wait(c, run_id)
    assert state["stage"] == "done"
    assert state["outcome"] == "true_heal"
    assert state["heal_events"] == []


def test_demo_errors(env: dict[str, Any]) -> None:
    c = env["client"]
    unknown = c.post(f"{API}/demo/runs", json={"scenario_id": "eval-01-id-rename"})
    err(unknown, 404, "NOT_FOUND")
    err(c.get(f"{API}/demo/runs/{ULID()}"), 404, "NOT_FOUND")
    demo: FakeDemo = env["demo"]
    demo.fail = True
    run_id = c.post(f"{API}/demo/runs", json={"scenario_id": "dev-01-id-rename"}).json()["id"]
    state = _wait(c, run_id)
    assert state["stage"] == "error"
    assert "boom" in state["error"]


# ------------------------------------------------------------------ sys.path, CORS, frontend


def test_create_app_puts_the_repo_root_on_sys_path(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: `healwright serve` (console script) could not import chaos_store."""
    p: Paths = env["paths"]
    monkeypatch.setattr(sys, "path", [x for x in sys.path if x != str(p.repo_root)])
    create_app(p, env["demo"])
    assert sys.path[0] == str(p.repo_root)


def test_cors_allows_only_the_vite_dev_origin(env: dict[str, Any]) -> None:
    c = env["client"]
    pre = {"Access-Control-Request-Method": "POST"}
    ok = c.options(f"{API}/health", headers={"Origin": "http://localhost:5173", **pre})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = c.options(f"{API}/health", headers={"Origin": "http://evil.example", **pre})
    assert "access-control-allow-origin" not in bad.headers


def test_frontend_is_served_when_built(env: dict[str, Any]) -> None:
    c = env["client"]
    assert "Frontend not built" in c.get("/runs").text
    p: Paths = env["paths"]
    (p.frontend_dist / "assets").mkdir(parents=True)
    (p.frontend_dist / "index.html").write_text("<!doctype html><title>HW</title>", "utf-8")
    (p.frontend_dist / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    built = TestClient(create_app(p, env["demo"]))
    assert "<title>HW</title>" in built.get("/runs/123").text
    js = built.get("/assets/app.js")
    assert js.text == "console.log(1)"
    # regression: Windows' registry maps .js to text/plain; browsers then refuse the bundle
    assert js.headers["content-type"].startswith("text/javascript")
    assert built.get(f"{API}/health").json()["status"] == "ok"


def test_demo_watch_flag_is_recorded(env: dict[str, Any]) -> None:
    c = env["client"]
    started = c.post(f"{API}/demo/runs", json={"scenario_id": "dev-01-id-rename", "watch": True})
    assert started.status_code == 202, started.text
    assert started.json()["watch"] is True
    _wait(c, started.json()["id"])


def test_heal_run_args_headed_only_in_watch_mode(tmp_path: Path) -> None:
    from healwright.api.demo import WATCH_SLOWMO_MS, heal_run_args

    quiet = heal_run_args(tmp_path, watch=False)
    assert "--screenshot=on" in quiet
    assert "--headed" not in quiet
    loud = heal_run_args(tmp_path, watch=True)
    assert "--headed" in loud
    assert loud[-2:] == ["--slowmo", str(WATCH_SLOWMO_MS)]
    assert f"--output={tmp_path}" in quiet  # one argument, even with spaces in the path


def test_demo_shots_are_served_and_unknown_is_404(env: dict[str, Any], tmp_path: Path) -> None:
    c = env["client"]
    demo: FakeDemo = env["demo"]
    run_id = c.post(f"{API}/demo/runs", json={"scenario_id": "dev-01-id-rename"}).json()["id"]
    _wait(c, run_id)
    err(c.get(f"{API}/demo/runs/{run_id}/shots/clean"), 404, "NOT_FOUND")
    png = tmp_path / "end.png"
    png.write_bytes(PNG)
    demo.get(run_id).shots["clean"] = png
    res = c.get(f"{API}/demo/runs/{run_id}/shots/clean")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert c.get(f"{API}/demo/runs/{run_id}").json()["shots"] == ["clean"]
    assert c.get(f"{API}/demo/runs/{run_id}/shots/other").status_code == 422


def test_demo_shop_opens_a_broken_session(env: dict[str, Any]) -> None:
    import httpx

    c = env["client"]
    try:
        url = c.post(f"{API}/demo/shop", json={"scenario_id": "dev-01-id-rename"}).json()["url"]
        assert "/__chaos/enter?session=" in url
        with httpx.Client(follow_redirects=True, timeout=10) as browser:
            browser.get(url)  # sets the session cookie, lands on the shop
            base = url.split("/__chaos/")[0]
            broken = browser.get(f"{base}/product/1").text
        assert 'id="btn-add-basket-x7"' in broken  # dev-01's id rename applied to this session
        clean = httpx.get(f"{base}/product/1", timeout=10).text  # a fresh session is not broken
        assert 'id="add-to-cart"' in clean
        err(c.post(f"{API}/demo/shop", json={"scenario_id": "eval-01-id-rename"}), 404, "NOT_FOUND")
    finally:
        env["demo"].close()
