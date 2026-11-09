"""HealWright triage API, ``/api/v1``.

Reads the run folders (``<artifact_dir>/runs``) and ``benchmark/results``: the same
JSON the plugin and the benchmark write. No database. Serves the built frontend
(``frontend/dist``) at ``/`` when it exists. Bind to 127.0.0.1 only.
"""

from __future__ import annotations

import json
import mimetypes
import re
import subprocess
import sys
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, Header, Query
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StringConstraints

import healwright
from healwright.api.demo import DemoRunner, dev_scenarios
from healwright.api.errors import ApiError, install
from healwright.apply import apply_event, diff_target, sha256_file
from healwright.models import HealEvent
from healwright.patcher import git_apply_check
from healwright.store.index import RunInfo, find_event, load_run, run_ids
from healwright.store.triage import MAX_NOTE_LEN, TriageStore, effective

API = "/api/v1"
VITE_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
# Artifact names are an enum of the generated file names: no free-form paths.
# The Set-of-Mark image is a JPEG, hence som.jpg; sandbox.png is reserved.
ArtifactFile = Literal[
    "before.png", "som.jpg", "sandbox.png", "candidates.json", "patch.diff", "suggestion.txt"
]
ARTIFACT_FILES = (
    "before.png",
    "som.jpg",
    "sandbox.png",
    "candidates.json",
    "patch.diff",
    "suggestion.txt",
)
ULID_PATTERN = r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"
Ulid = Annotated[str, PathParam(pattern=ULID_PATTERN)]
UlidQuery = Annotated[str | None, Query(pattern=ULID_PATTERN)]
MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".diff": "text/x-diff",
    ".txt": "text/plain",
    ".json": "application/json",
}
# <date>--<system>-<split>[-<tag>], e.g. 2026-11-07--healwright-eval-r2 or ...-eval-combined
BENCH_ID_PATTERN = r"^(\d{4}-\d{2}-\d{2})--([a-z0-9_]+-(?:dev|eval|smoke)(?:-[a-z0-9]+)?)$"
BENCH_ID = re.compile(BENCH_ID_PATTERN)
STATUSES = (
    "healed",
    "suggested",
    "needs_human",
    "regression_suspected",
    "not_a_locator_failure",
    "error",
)


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    artifact_root: Path
    results_root: Path
    frontend_dist: Path
    demo_work: Path


class TriageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected"]
    note: Annotated[str, StringConstraints(max_length=MAX_NOTE_LEN)] = ""


class DemoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]
    watch: bool = False


class ShopBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]


# --------------------------------------------------------------------------- views


def event_view(run: RunInfo, event: HealEvent) -> dict[str, Any]:
    record = TriageStore(run.dir).get(event.id)
    data = event.model_dump(mode="json")
    data["triage"] = {
        "status": effective(record),
        "decision": record.decision if record else None,
        "note": record.note if record else "",
        "applied": bool(record and record.applied),
        "updated_at": record.updated_at if record else None,
    }
    data["artifact_urls"] = {
        key: f"{API}/heal-events/{event.id}/artifacts/{name}"
        for key, name in event.artifacts.items()
        if name in ARTIFACT_FILES
    }
    return data


def run_view(run: RunInfo) -> dict[str, Any]:
    statuses: Counter[str] = Counter(str(e.decision.status) for e in run.events)
    tiers = Counter(str(e.decision.tier) for e in run.events if e.decision.tier is not None)
    return {
        "run_id": run.run_id,
        "started_at": run.started_at,
        "event_count": len(run.events),
        "status_counts": {s: statuses.get(s, 0) for s in STATUSES},
        "tier_counts": {"1": tiers.get("1", 0), "2": tiers.get("2", 0)},
        "tests": sorted({e.key.test_nodeid for e in run.events}),
        "skipped_lines": run.skipped_lines,
    }


def bench_folders(results_root: Path) -> list[tuple[str, Path]]:
    if not results_root.is_dir():
        return []
    out = []
    for date_dir in results_root.iterdir():
        if not date_dir.is_dir():
            continue
        for folder in date_dir.iterdir():
            bid = f"{date_dir.name}--{folder.name}"
            if BENCH_ID.match(bid) and (folder / "results.json").is_file():
                out.append((bid, folder))
    return sorted(out, reverse=True)


def bench_summary(bid: str, folder: Path) -> dict[str, Any]:
    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    return {
        "id": bid,
        "system": data.get("system"),
        "split": data.get("split"),
        "vlm_mode": data.get("vlm_mode"),
        "runs": data.get("runs"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "aggregate": data.get("aggregate"),
    }


COMBINED_DIR = "eval-combined"
OUTCOMES = ("true_heal", "false_heal", "red")
PATCH_KEYS = ("healed_events", "apply_check_ok", "no_patch", "failed")


def combined_view(results_root: Path) -> dict[str, Any]:
    """The final eval summary (`benchmark.combine` output) for the benchmark page.

    Systems come from `<results>/eval-combined/<system>/combined.json` as written.
    The per-class breakdown, the scenario table, per-run headline values and patch counts are
    derived from the per-run `results.json` files those files point to; harness errors are left out of the
    counts (scoring rule 2026-11-07) and listed as "error" in the scenario table.
    """
    systems: list[dict[str, Any]] = []
    scenarios: dict[str, dict[str, Any]] = {}
    root = results_root / COMBINED_DIR
    if not root.is_dir():
        return {"systems": [], "scenarios": []}
    for f in sorted(root.glob("*/combined.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        system = str(data.get("system") or f.parent.name)
        by_class: dict[str, dict[str, int]] = {}
        runs: list[dict[str, Any]] = []
        patches = dict.fromkeys(PATCH_KEYS, 0)
        for run in data.get("per_run") or []:
            parts = Path(str(run.get("folder", ""))).parts[-2:]
            results = results_root.joinpath(*parts) / "results.json"
            if len(parts) != 2 or not BENCH_ID.match("--".join(parts)) or not results.is_file():
                continue
            result = json.loads(results.read_text(encoding="utf-8"))
            agg = result.get("aggregate") or {}
            run_patches = agg.get("patches") or {}
            runs.append(
                {k: run.get(k) for k in ("vlm_mode", "started_at")}
                | {"id": "--".join(parts)}
                | {k: agg.get(k) for k in ("true_heal_rate", "false_heals_on_traps")}
                | {"patches": {k: run_patches.get(k, 0) for k in PATCH_KEYS}}
            )
            for k in PATCH_KEYS:
                patches[k] += int(run_patches.get(k, 0) or 0)
            rows = result.get("rows") or []
            for row in rows:
                sid, klass, outcome = row.get("id"), row.get("class"), row.get("outcome")
                entry = scenarios.setdefault(
                    sid,
                    {"id": sid, "class": klass, "expected": row.get("expected"), "outcomes": {}},
                )
                entry["outcomes"].setdefault(system, []).append(outcome)
                if outcome in OUTCOMES:
                    counts = by_class.setdefault(klass, {"scored": 0, **dict.fromkeys(OUTCOMES, 0)})
                    counts["scored"] += 1
                    counts[outcome] += 1
        systems.append(
            {
                "system": system,
                "split": data.get("split"),
                "runs": data.get("runs"),
                "summary": data.get("summary") or {},
                "per_run": runs,
                "by_class": by_class,
                "patches": patches,
            }
        )
    return {"systems": systems, "scenarios": sorted(scenarios.values(), key=lambda s: s["id"])}


# --------------------------------------------------------------------------- app


def create_app(
    paths: Paths | None = None,
    demo: DemoRunner | None = None,
    api_token: str | None = None,
) -> FastAPI:
    if paths is None:
        from healwright.config import load_settings

        settings = load_settings()
        if api_token is None and settings.api_token is not None:
            api_token = settings.api_token.get_secret_value()
        repo = Path.cwd()
        paths = Paths(
            repo_root=repo,
            artifact_root=settings.artifact_dir,
            results_root=repo / "benchmark" / "results",
            frontend_dist=repo / "frontend" / "dist",
            demo_work=settings.artifact_dir / "demo",
        )
    # The demo endpoints import the repo-root packages (chaos_store, benchmark). The
    # `healwright` console script does not put the working directory on sys.path
    # (pytest does), so add the repo root explicitly.
    if str(paths.repo_root) not in sys.path:
        sys.path.insert(0, str(paths.repo_root))
    runner = demo or DemoRunner(paths.artifact_root, paths.demo_work)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        runner.close()

    app = FastAPI(
        title="HealWright API",
        version=healwright.__version__,
        lifespan=lifespan,
        docs_url=f"{API}/docs",
        openapi_url=f"{API}/openapi.json",
        redoc_url=None,
    )
    app.state.paths = paths
    app.state.demo = runner
    app.add_middleware(
        CORSMiddleware,
        allow_origins=VITE_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    install(app, api_token)
    app.include_router(router(paths, runner), prefix=API)
    mount_frontend(app, paths.frontend_dist)
    return app


def router(paths: Paths, runner: DemoRunner) -> APIRouter:
    r = APIRouter()

    def get_event(event_id: str) -> tuple[RunInfo, HealEvent]:
        found = find_event(paths.artifact_root, event_id)
        if found is None:
            raise ApiError(404, "NOT_FOUND", f"no heal event {event_id}")
        return found

    @r.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": healwright.__version__}

    @r.get("/ready")
    def ready() -> JSONResponse:
        checks = {
            "artifact_root": paths.artifact_root.is_dir(),
            "results_root": paths.results_root.is_dir(),
            "git": _git_available(paths.repo_root),
        }
        ok = all(checks.values())
        body = {"status": "ready" if ok else "not_ready", "checks": checks}
        return JSONResponse(body, status_code=200 if ok else 503)

    @r.get("/runs")
    def runs(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: UlidQuery = None,
    ) -> dict[str, Any]:
        ids = run_ids(paths.artifact_root)
        if cursor is not None:
            ids = [i for i in ids if i < cursor]
        page = ids[:limit]
        items = [run_view(info) for i in page if (info := load_run(paths.artifact_root, i))]
        return {"items": items, "next_cursor": page[-1] if len(ids) > limit else None}

    @r.get("/runs/{run_id}")
    def run_detail(run_id: Ulid) -> dict[str, Any]:
        info = load_run(paths.artifact_root, run_id)
        if info is None:
            raise ApiError(404, "NOT_FOUND", f"no run {run_id}")
        events = sorted(info.events, key=lambda e: e.id)
        return {**run_view(info), "events": [event_view(info, e) for e in events]}

    @r.get("/heal-events")
    def heal_events(
        run_id: UlidQuery = None,
        status: Annotated[Literal[STATUSES] | None, Query()] = None,  # type: ignore[valid-type]
        tier: Annotated[int | None, Query(ge=1, le=2)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: UlidQuery = None,
    ) -> dict[str, Any]:
        ids = [run_id] if run_id else run_ids(paths.artifact_root)
        if run_id and load_run(paths.artifact_root, run_id) is None:
            raise ApiError(404, "NOT_FOUND", f"no run {run_id}")
        rows: list[tuple[RunInfo, HealEvent]] = []
        for rid in ids:
            info = load_run(paths.artifact_root, rid)
            if info is None:
                continue
            for e in info.events:
                if status and e.decision.status != status:
                    continue
                if tier and e.decision.tier != tier:
                    continue
                if cursor and e.id >= cursor:
                    continue
                rows.append((info, e))
        rows.sort(key=lambda pair: pair[1].id, reverse=True)
        page = rows[:limit]
        return {
            "items": [event_view(info, e) for info, e in page],
            "next_cursor": page[-1][1].id if len(rows) > limit else None,
        }

    @r.get("/heal-events/{event_id}")
    def heal_event(event_id: Ulid) -> dict[str, Any]:
        info, event = get_event(event_id)
        return event_view(info, event)

    @r.get("/heal-events/{event_id}/artifacts/{name}")
    def artifact(event_id: Ulid, name: ArtifactFile) -> Response:
        info, event = get_event(event_id)
        if name not in event.artifacts.values():
            raise ApiError(404, "NOT_FOUND", f"heal event {event_id} has no artifact {name}")
        path = info.dir / "artifacts" / event_id / name
        if not path.is_file():
            raise ApiError(404, "NOT_FOUND", f"artifact file {name} is missing")
        media = MEDIA.get(path.suffix, "application/octet-stream")
        return FileResponse(path, media_type=media, headers={"Cache-Control": "no-store"})

    @r.get("/heal-events/{event_id}/patch")
    def patch(event_id: Ulid) -> dict[str, Any]:
        _info, event = get_event(event_id)
        if not event.diff:
            raise ApiError(404, "NO_PATCH", "this heal event has no patch (suggestion only)")
        target = diff_target(event.diff)
        current = sha256_file(paths.repo_root / target) if target else None
        ok, msg = git_apply_check(paths.repo_root, event.diff)
        return {
            "event_id": event_id,
            "diff": event.diff,
            "source_path": target,
            "source_sha256": event.source_sha256,
            "current_sha256": current,
            "source_changed": current != event.source_sha256,
            "apply_check": {"ok": ok, "message": msg[:300]},
        }

    @r.post("/heal-events/{event_id}/triage")
    def triage(event_id: Ulid, body: TriageBody) -> dict[str, Any]:
        info, event = get_event(event_id)
        store = TriageStore(info.dir)
        record = store.get(event_id)
        if record is not None and record.decision is not None:
            if record.decision != body.decision:
                raise ApiError(
                    409,
                    "ALREADY_TRIAGED",
                    f"this heal event was already {record.decision}",
                    {"decision": record.decision},
                )
            return event_view(info, event)  # same decision again: idempotent
        store.decide(event_id, body.decision, body.note)
        return event_view(info, event)

    @r.post("/heal-events/{event_id}/patch/apply")
    def apply(
        event_id: Ulid,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ] = None,
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "an Idempotency-Key header is required",
                {"errors": [{"loc": ["header", "Idempotency-Key"], "msg": "Field required"}]},
            )
        info, event = get_event(event_id)
        record = TriageStore(info.dir).get(event_id)
        if record is not None and record.applied:
            # applying twice is idempotent: the file is already patched
            return {
                "event_id": event_id,
                "code": "APPLIED",
                "replayed": True,
                "event": event_view(info, event),
            }
        result = apply_event(
            paths.repo_root,
            paths.artifact_root,
            event_id,
            require_accepted=True,
            idempotency_key=idempotency_key,
        )
        status = {
            "NOT_FOUND": 404,
            "NO_PATCH": 404,
            "NOT_ACCEPTED": 409,
            "SOURCE_CHANGED": 409,
            "PATCH_INVALID": 422,
        }
        if result.code == "ALREADY_APPLIED":
            return {
                "event_id": event_id,
                "code": "APPLIED",
                "replayed": True,
                "event": event_view(info, event),
            }
        if result.code != "APPLIED":
            raise ApiError(status[result.code], result.code, result.message, result.details or None)
        return {
            "event_id": event_id,
            "code": result.code,
            "replayed": False,
            "source_path": result.source_path,
            "event": event_view(info, event),
        }

    @r.get("/benchmarks")
    def benchmarks() -> dict[str, Any]:
        return {"items": [bench_summary(bid, f) for bid, f in bench_folders(paths.results_root)]}

    @r.get("/benchmarks/combined")
    def benchmarks_combined() -> dict[str, Any]:
        return combined_view(paths.results_root)

    @r.get("/benchmarks/{bench_id}")
    def benchmark(
        bench_id: Annotated[str, PathParam(pattern=BENCH_ID_PATTERN)],
    ) -> dict[str, Any]:
        for bid, folder in bench_folders(paths.results_root):
            if bid == bench_id:
                data: dict[str, Any] = json.loads(
                    (folder / "results.json").read_text(encoding="utf-8")
                )
                return {"id": bid, **data}
        raise ApiError(404, "NOT_FOUND", f"no benchmark {bench_id}")

    @r.get("/scenarios")
    def scenarios() -> dict[str, Any]:
        return {"items": dev_scenarios()}

    @r.post("/demo/runs", status_code=202)
    def demo_start(body: DemoBody) -> dict[str, Any]:
        return runner.start(body.scenario_id, watch=body.watch).public()

    @r.post("/demo/shop")
    def demo_shop(body: ShopBody) -> dict[str, str]:
        return {"url": runner.open_shop(body.scenario_id)}

    @r.get("/demo/runs/{demo_id}/shots/{name}")
    def demo_shot(demo_id: Ulid, name: Literal["clean", "healed"]) -> FileResponse:
        shot = runner.get(demo_id).shots.get(name)
        if shot is None or not shot.is_file():
            raise ApiError(404, "NOT_FOUND", f"no {name} screenshot for demo run {demo_id}")
        return FileResponse(shot, media_type="image/png")

    @r.get("/demo/runs/{demo_id}")
    def demo_get(demo_id: Ulid) -> dict[str, Any]:
        run = runner.get(demo_id)
        data = run.public()
        events = []
        for eid in run.event_ids:
            found = find_event(paths.artifact_root, eid)
            if found:
                events.append(event_view(*found))
        data["heal_events"] = events
        return data

    @r.api_route("/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
    def api_not_found(rest: str) -> None:
        raise ApiError(404, "NOT_FOUND", f"no API route /{rest}")

    return r


def mount_frontend(app: FastAPI, dist: Path) -> None:
    # Windows can map .js to text/plain in the registry, which Python's mimetypes
    # reads; browsers then refuse to run the bundle. Register the right types.
    for media, ext in (
        ("text/javascript", ".js"),
        ("text/javascript", ".mjs"),
        ("text/css", ".css"),
        ("image/svg+xml", ".svg"),
        ("application/json", ".json"),
        ("font/woff2", ".woff2"),
    ):
        mimetypes.add_type(media, ext)
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if not index.is_file():
            return PlainTextResponse(
                "HealWright API is running. Frontend not built: run `npm run build` in frontend/.",
                status_code=200,
            )
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


def _git_available(repo_root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "--version"], cwd=repo_root, capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


__all__ = ["API", "Paths", "create_app"]
