"""Live demo runs for the frontend.

One run at a time. A run: start the Chaos Store (once, in this process, control
routes on), record baselines with 2 clean runs of the scenario's test, apply the
mutation, run the test once with HealWright in heal mode and VLM replay mode,
then classify the outcome from the store's action log, exactly like the
benchmark harness (it reuses ``benchmark.run``'s helpers).

Only DEV scenarios are offered: the demo must never produce results on the
frozen eval split. Requires running from the repository root (it imports the
``chaos_store`` and ``benchmark`` packages and runs the ``examples`` tests).
"""

from __future__ import annotations

import contextlib
import importlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from ulid import ULID

from healwright.api.errors import ApiError
from healwright.store.index import load_run, run_ids

log = logging.getLogger("healwright.api.demo")

Stage = Literal[
    "queued", "starting_store", "recording_baselines", "breaking", "running_test", "done", "error"
]


@dataclass
class DemoRun:
    id: str
    scenario_id: str
    stage: Stage = "queued"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    outcome: str | None = None
    test_passed: bool | None = None
    fired: list[str] = field(default_factory=list)
    expected_action: str | None = None
    event_ids: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    error: str | None = None
    watch: bool = False
    shots: dict[str, Path] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "stage": self.stage,
            "running": self.stage not in ("done", "error"),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": round((self.finished_at or time.time()) - self.started_at, 1),
            "outcome": self.outcome,
            "test_passed": self.test_passed,
            "fired_actions": self.fired,
            "expected_action": self.expected_action,
            "heal_event_ids": self.event_ids,
            "run_ids": self.run_ids,
            "error": self.error,
            "watch": self.watch,
            "shots": sorted(self.shots),
        }


WATCH_SLOWMO_MS = 400


def heal_run_args(shots: Path, *, watch: bool) -> list[str]:
    """Extra pytest args for the demo's heal run: an end-of-test screenshot, and in watch mode a
    visible browser slowed down so each action can be followed."""
    args = ["--screenshot=on", f"--output={shots}"]
    if watch:
        args += ["--headed", "--slowmo", str(WATCH_SLOWMO_MS)]
    return args


def dev_scenarios() -> list[dict[str, Any]]:
    out = []
    for s in _mod("chaos_store.scenario").iter_scenarios():
        if s.split != "dev" or s.expected is None:
            continue
        out.append(
            {
                "id": s.id,
                "class": s.klass,
                "test": s.test,
                "expected_outcome": s.expected.outcome,
                "expected_action": s.expected.action_id,
            }
        )
    return out


class DemoRunner:
    def __init__(self, artifact_root: Path, work_root: Path) -> None:
        self.artifact_root = artifact_root
        self.work_root = work_root
        self._lock = threading.Lock()
        self._runs: dict[str, DemoRun] = {}
        self._active: str | None = None
        self._stack = contextlib.ExitStack()
        self._store_url: str | None = None
        self._shop_url: str | None = None

    def close(self) -> None:
        self._stack.close()
        self._store_url = None
        self._shop_url = None

    def get(self, run_id: str) -> DemoRun:
        run = self._runs.get(run_id)
        if run is None:
            raise ApiError(404, "NOT_FOUND", f"no demo run {run_id}")
        return run

    def start(self, scenario_id: str, watch: bool = False) -> DemoRun:
        known = {s["id"] for s in dev_scenarios()}
        if scenario_id not in known:
            raise ApiError(404, "NOT_FOUND", f"no dev scenario {scenario_id}")
        with self._lock:
            if self._active is not None and self._runs[self._active].stage not in ("done", "error"):
                raise ApiError(409, "DEMO_BUSY", "a demo run is already in progress")
            run = DemoRun(id=str(ULID()), scenario_id=scenario_id, watch=watch)
            self._runs[run.id] = run
            self._active = run.id
        threading.Thread(target=self._execute, args=(run,), daemon=True).start()
        return run

    def open_shop(self, scenario_id: str) -> str:
        """A URL that opens the Chaos Store on a fresh session with the scenario applied.

        Uses its own store (never reset by demo runs), so the tab stays broken.
        """
        known = {s["id"] for s in dev_scenarios()}
        if scenario_id not in known:
            raise ApiError(404, "NOT_FOUND", f"no dev scenario {scenario_id}")
        scenario = _mod("chaos_store.scenario").load_scenario(scenario_id, _dev_dir())
        with self._lock:
            if self._shop_url is None:
                serve = _mod("chaos_store.serve").serve_in_thread
                self._shop_url = self._stack.enter_context(serve(control=True))
            shop = self._shop_url
        session = _mod("chaos_store.state").new_session_id()
        httpx.post(
            f"{shop}/__chaos/scenario",
            params={"session": session},
            content=scenario.model_dump_json(by_alias=True, exclude_none=True),
            timeout=10,
        ).raise_for_status()
        return f"{shop}/__chaos/enter?session={session}&next=/"

    def _store(self) -> str:
        if self._store_url is None:
            serve = _mod("chaos_store.serve").serve_in_thread
            self._store_url = self._stack.enter_context(serve(control=True))
        return self._store_url

    def _execute(self, run: DemoRun) -> None:
        try:
            self._steps(run)
            run.stage = "done"
        except Exception as exc:
            log.exception("demo run %s failed", run.id)
            run.error = f"{type(exc).__name__}: {str(exc)[:300]}"
            run.stage = "error"
        finally:
            run.finished_at = time.time()

    def _steps(self, run: DemoRun) -> None:
        bench = _mod("benchmark.run")
        actions, base_env, classify = bench.actions, bench.base_env, bench.classify
        control, pytest_run = bench.control, bench.pytest_run
        scenario = _mod("chaos_store.scenario").load_scenario(run.scenario_id, _dev_dir())
        assert scenario.test is not None
        assert scenario.expected is not None
        run.expected_action = scenario.expected.action_id
        run.stage = "starting_store"
        store = self._store()
        work = self.work_root / run.id
        control(store, "reset")

        run.stage = "recording_baselines"
        clean: list[str] = []
        for i in range(2):
            session = f"demo-clean-{run.id}-{i}"
            env = base_env(store, session, work)
            env["HEALWRIGHT_MODE"] = "record"
            if i == 0:
                env["__argv"] = json.dumps(["--screenshot=on", f"--output={work / 'shots-clean'}"])
            proc = pytest_run(scenario.test, env)
            if proc.returncode != 0:
                raise RuntimeError(f"clean run failed: {proc.stdout[-300:]}")
            clean = actions(store, session)
            if i == 0:
                self._keep_shot(run, "clean", work / "shots-clean")

        run.stage = "breaking"
        control(
            store, "scenario", content=scenario.model_dump_json(by_alias=True, exclude_none=True)
        )

        run.stage = "running_test"
        before = set(run_ids(self.artifact_root))
        session = f"demo-{run.id}"
        env = base_env(store, session, work)
        env["HEALWRIGHT_MODE"] = "heal"
        env["HEALWRIGHT_VLM_MODE"] = "replay"
        env["HEALWRIGHT_ARTIFACT_DIR"] = str(self.artifact_root)  # events show up in the API
        env["__argv"] = json.dumps(heal_run_args(work / "shots-healed", watch=run.watch))
        try:
            proc = pytest_run(scenario.test, env)
            run.fired = actions(store, session)  # read BEFORE the reset clears the log
        finally:
            control(store, "reset")
        if proc.returncode not in (0, 1):
            raise RuntimeError(f"pytest exit {proc.returncode}: {proc.stdout[-300:]}")
        run.test_passed = proc.returncode == 0
        self._keep_shot(run, "healed", work / "shots-healed")
        new_runs = [r for r in run_ids(self.artifact_root) if r not in before]
        run.run_ids = new_runs
        healed = False
        for rid in new_runs:
            info = load_run(self.artifact_root, rid)
            if info is None:
                continue
            for event in info.events:
                run.event_ids.append(event.id)
                healed = healed or event.decision.status == "healed"
        run.outcome = classify(scenario, run.test_passed, run.fired, clean, healed)

    @staticmethod
    def _keep_shot(run: DemoRun, name: str, folder: Path) -> None:
        """pytest-playwright writes one end-of-test screenshot per test under ``folder``."""
        found = sorted(folder.rglob("*.png")) if folder.is_dir() else []
        if found:
            run.shots[name] = found[-1]


def _mod(name: str) -> Any:
    """Repo-root packages (not part of the installed ``healwright`` package)."""
    return importlib.import_module(name)


def _dev_dir() -> Path:
    return Path(_mod("chaos_store.scenario").SCENARIO_DIR) / "dev"


__all__ = ["DemoRun", "DemoRunner", "dev_scenarios"]
