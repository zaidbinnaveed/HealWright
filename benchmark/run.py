"""Chaos Benchmark runner.

    uv run python -m benchmark.run --system healwright --split eval --vlm-mode replay --runs 1

HealWright is treated as a BLACK BOX: systems are selected with environment
variables, tests run as pytest subprocesses, and ground truth comes only from
the Chaos Store's server-side action log. Nothing here imports ``healwright``.

Per scenario: record baselines for the referenced test (2 clean runs, record
mode; cached per test within a run), apply the mutation server-wide, run the
test once under the system, then classify against the clean run's action log:

- false_heal: an action fired that the clean run never fired (e.g. the
  look-alike's), or any heal on a regression trap;
- true_heal: the test passed and the expected action fired;
- red: otherwise (the test failed without a wrong action);
- error: the harness itself failed (crash, timeout, collection error).

Writes benchmark/results/<date>/<system>/results.json and summary.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from chaos_store.scenario import Scenario, iter_scenarios
from chaos_store.serve import serve_in_thread

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmark" / "results"
VLM_CACHE = ROOT / "benchmark" / "vlm_cache"
# Benchmark pacing: free-tier rate limits cost waiting time, not scenarios.
BENCH_PACING = {"HEALWRIGHT_VLM_MAX_RETRIES": "4", "HEALWRIGHT_VLM_RETRY_AFTER_CAP_S": "60"}
# A scenario lost because the model call failed (not because of the method).
PROVIDER_FAILURE_MARKERS = ("all providers failed", "call cap", "per-run cap")


def provider_calls(work: Path) -> dict[str, dict[str, int]]:
    """Real HTTP calls per provider and status, from the run's JSON log (one line per call)."""
    out: dict[str, dict[str, int]] = {}
    for path in sorted((work / "artifacts" / "logs").glob("healwright.log*")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not str(rec.get("msg", "")).startswith("provider call"):
                continue
            provider = str(rec.get("provider", "?"))
            status = str(rec.get("error_code", "?"))
            out.setdefault(provider, {})
            out[provider][status] = out[provider].get(status, 0) + 1
    return out


def provider_failures(rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for r in rows
        if any(
            any(m in str(e.get("reason", "")) for m in PROVIDER_FAILURE_MARKERS)
            for e in r.get("events", [])
        )
    )


ACTION_TIMEOUT_MS = "5000"  # same for every system, so native does not wait 30 s per failure
SMOKE_10 = (
    "eval-01-id-rename",
    "eval-10-css-refactor",
    "eval-18-copy-drift",
    "eval-25-tag-to-aria",
    "eval-33-layout-move",
    "eval-39-i18n",
    "eval-42-distractor",
    "eval-44-distractor",
    "eval-46-regression",
    "eval-50-regression",
)

# system -> HealWright environment (None = plugin disabled)
SYSTEMS: dict[str, dict[str, str] | None] = {
    "native": None,
    "healwright": {"HEALWRIGHT_MODE": "heal"},
    "tier1_only": {"HEALWRIGHT_MODE": "heal", "HEALWRIGHT_VLM_RUN_CAP": "0"},
    "healwright_noverify": {"HEALWRIGHT_MODE": "heal", "HEALWRIGHT_VERIFY": "false"},
    "greedy": {
        "HEALWRIGHT_MODE": "heal",
        "HEALWRIGHT_TAU_CONF": "0",
        "HEALWRIGHT_DELTA_MARGIN": "0",
        "HEALWRIGHT_VERIFY": "false",
        "HEALWRIGHT_VLM_RUN_CAP": "0",
    },
    # raw-HTML baseline: page HTML -> one CSS selector, no gate, no verifier
    "rawhtml": {"HEALWRIGHT_MODE": "heal", "__args": "-p benchmark.rawhtml_plugin"},
}


def control(base: str, path: str, **kw: Any) -> httpx.Response:
    res = httpx.request(kw.pop("method", "POST"), f"{base}/__chaos/{path}", timeout=10, **kw)
    res.raise_for_status()
    return res


def actions(base: str, session: str) -> list[str]:
    data = control(base, "actions", method="GET", params={"session": session}).json()
    return [a["action_id"] for a in data["actions"]]


def descendants(pid: int, since: float) -> list[dict[str, Any]]:
    """Processes left by one pytest subprocess (hang capture; Windows CIM, best effort).

    Two sources: the live tree under ``pid`` (parent ids survive a parent's death),
    and any process created after ``since`` (epoch seconds). The second catches
    orphans whose chain broke: the venv python.exe is a launcher, so once pytest
    and its launcher are gone no live process points back to ``pid``. Processes
    from the second source may be unrelated (``in_tree`` False). [] on any failure.
    """
    if sys.platform != "win32":
        return []
    query = (
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,"
        "CommandLine,@{n='Created';e={if ($_.CreationDate) "
        "{(New-Object DateTimeOffset $_.CreationDate).ToUnixTimeMilliseconds()}}} "
        "| ConvertTo-Json"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", query],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
        procs = json.loads(out or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return descendants_of(pid, procs, since_ms=since * 1000)


def descendants_of(
    pid: int, procs: list[dict[str, Any]], since_ms: float | None = None
) -> list[dict[str, Any]]:
    tree: list[dict[str, Any]] = []
    frontier = {pid}
    while frontier:
        kids = [p for p in procs if p.get("ParentProcessId") in frontier and p not in tree]
        tree.extend(kids)
        frontier = {p["ProcessId"] for p in kids}
    query_pids = {p["ProcessId"] for p in procs if "Win32_Process" in (p.get("CommandLine") or "")}
    late = [
        p
        for p in procs
        if since_ms is not None
        and (p.get("Created") or 0) >= since_ms
        and p not in tree
        and p["ProcessId"] not in query_pids
        and p.get("ParentProcessId") not in query_pids
        and p["ProcessId"] != os.getpid()
    ]
    return [
        {
            "pid": p["ProcessId"],
            "ppid": p["ParentProcessId"],
            "name": p.get("Name"),
            "cmd": (p.get("CommandLine") or "")[:200],
            "in_tree": p in tree,
        }
        for p in tree + late
    ]


# Subprocess-timeout captures land here (one JSON per timeout); reporting only.
KI10_DIR = RESULTS / "ki10-diagnostics"
POST_KILL_WAIT_S = 30


def pytest_run(
    test: str, env: dict[str, str], timeout: int = 240
) -> subprocess.CompletedProcess[str]:
    """Run one pytest subprocess; same contract as ``subprocess.run(..., timeout=...)``.

    On a timeout, records (1) the partial stdout/stderr, (2) whether pytest
    itself had exited, i.e. only its output pipes were still held open,
    (3) leftover descendant processes, (4) the in-process faulthandler dump, then
    raises ``TimeoutExpired`` as before. The wait after the kill is bounded
    (``subprocess.run`` on Windows waits for the pipes with no limit).
    """
    dump = Path(tempfile.gettempdir()) / f"hw-ki10-{os.getpid()}-{time.monotonic_ns()}.txt"
    env = {**env, "HW_KI10_DUMP": str(dump)}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        test,
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "benchmark.ki10_faulthandler",
        *env.pop("__args", "").split(),
        *json.loads(env.pop("__argv", "[]")),  # a JSON list: arguments may contain spaces
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    chunks: dict[str, list[str]] = {"stdout": [], "stderr": []}

    def pump(name: str) -> None:
        stream = getattr(proc, name)
        for line in iter(stream.readline, ""):
            chunks[name].append(line)

    readers = [threading.Thread(target=pump, args=(n,), daemon=True) for n in chunks]
    for r in readers:
        r.start()
    t0 = time.monotonic()
    started = time.time()
    try:
        proc.wait(timeout=timeout)
        exited_at: float | None = round(time.monotonic() - t0, 1)
    except subprocess.TimeoutExpired:
        exited_at = None
    for r in readers:  # pytest gone: the pipes close unless a grandchild holds them
        r.join(timeout=max(0.0, timeout - (time.monotonic() - t0)))
    pipes_open = any(r.is_alive() for r in readers)
    if exited_at is not None and not pipes_open:
        dump.unlink(missing_ok=True)
        return subprocess.CompletedProcess(
            cmd, proc.returncode, "".join(chunks["stdout"]), "".join(chunks["stderr"])
        )
    # timeout: capture before killing anything
    kids = descendants(proc.pid, since=started)
    proc.kill()
    proc.wait()
    for r in readers:
        r.join(timeout=POST_KILL_WAIT_S)
    try:
        faulthandler_dump = dump.read_text(encoding="utf-8", errors="replace")
    except OSError:
        faulthandler_dump = ""
    stdout_tail = "".join(chunks["stdout"])[-4000:]
    record = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "test": test,
        "timeout_s": timeout,
        "pytest_exited": exited_at is not None,
        "pytest_exit_after_s": exited_at,
        "pytest_returncode": proc.returncode if exited_at is not None else None,
        "pipes_still_open_at_timeout": pipes_open,
        "pipes_still_open_after_kill": any(r.is_alive() for r in readers),
        "descendants_at_timeout": kids,
        "stdout_tail": stdout_tail,
        "stderr_tail": "".join(chunks["stderr"])[-4000:],
        "faulthandler_dump": faulthandler_dump[-8000:],
    }
    KI10_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in test.rsplit("::", 1)[-1])
    out = KI10_DIR / f"{stamp}-{name[-80:]}.json"
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    dump.unlink(missing_ok=True)
    raise subprocess.TimeoutExpired(
        cmd,
        timeout,
        output=stdout_tail,
        stderr=f"timeout capture: exited={record['pytest_exited']} pipes_open={pipes_open} "
        f"descendants={[k['name'] for k in kids]} -> {out.name}",
    )


def base_env(store: str, session: str, work: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("HEALWRIGHT_")}
    for k in (
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "GEMINI_MODEL",
        "GROQ_MODEL",
        "MISTRAL_MODEL",
    ):
        if k in os.environ:
            env[k] = os.environ[k]
    env.update(
        {
            "CHAOS_BASE_URL": store,
            "CHAOS_SESSION": session,
            "CHAOS_ACTION_TIMEOUT_MS": ACTION_TIMEOUT_MS,
            "HEALWRIGHT_BASELINE_DIR": str(work / "baselines"),
            "HEALWRIGHT_ARTIFACT_DIR": str(work / "artifacts"),
            # persistent + committed: record mode fills it, replay (and CI) reuses it
            "HEALWRIGHT_VLM_CACHE_DIR": str(VLM_CACHE),
        }
    )
    return env


def heal_events(work: Path, since: set[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted((work / "artifacts" / "runs").glob("*/events.jsonl")):
        if f in since:
            continue
        out.extend(
            json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return out


def classify(s: Scenario, passed: bool, fired: list[str], clean: list[str], healed: bool) -> str:
    assert s.expected is not None
    extra = Counter(fired) - Counter(clean)
    if extra:
        return "false_heal"
    if s.klass == "regression_trap" and (healed or passed):
        return "false_heal"
    if passed and s.expected.action_id in fired:
        return "true_heal"
    return "red"


def run_scenario(
    s: Scenario,
    system: str,
    store: str,
    work: Path,
    clean_cache: dict[str, list[str]],
    vlm_mode: str,
    n: int,
    providers: str | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    assert s.test is not None
    assert s.expected is not None
    control(store, "reset")
    row: dict[str, Any] = {"id": s.id, "class": s.klass, "expected": s.expected.outcome}
    t0 = time.perf_counter()
    try:
        if s.test not in clean_cache:  # baselines + clean action log, twice (strong contracts)
            for i in range(2):
                session = f"clean-{n}-{hashlib.sha256(s.test.encode()).hexdigest()[:10]}-{i}"
                env = base_env(store, session, work)
                env["HEALWRIGHT_MODE"] = "record"
                proc = pytest_run(s.test, env)
                if proc.returncode != 0:
                    raise RuntimeError(f"clean run failed: {proc.stdout[-500:]}")
                clean_cache[s.test] = actions(store, session)
        control(store, "scenario", content=s.model_dump_json(by_alias=True, exclude_none=True))
        session = f"bench-{n}-{s.id}"
        env = base_env(store, session, work)
        system_env = SYSTEMS[system]
        if system_env is None:
            env["__args"] = "-p no:healwright"
        else:
            env.update(system_env)
            env["HEALWRIGHT_VLM_MODE"] = vlm_mode
            env.update(BENCH_PACING)
            if providers:
                env["HEALWRIGHT_PROVIDERS"] = providers
            if cache_dir is not None:
                env["HEALWRIGHT_VLM_CACHE_DIR"] = str(cache_dir)
        before = set((work / "artifacts" / "runs").glob("*/events.jsonl"))
        proc = pytest_run(s.test, env)
        if proc.returncode not in (0, 1):  # 0 passed, 1 failed; anything else is a harness error
            raise RuntimeError(f"pytest exit {proc.returncode}: {proc.stdout[-500:]}")
        passed = proc.returncode == 0
        fired = actions(store, session)
        events = heal_events(work, before)
        healed = [e for e in events if e["decision"]["status"] == "healed"]
        row.update(
            {
                "outcome": classify(s, passed, fired, clean_cache[s.test], bool(healed)),
                "test_passed": passed,
                "fired": fired,
                "clean": clean_cache[s.test],
                "expected_action": s.expected.action_id,
                "events": [
                    {
                        "status": e["decision"]["status"],
                        "tier": e["decision"]["tier"],
                        "total_ms": e["timings_ms"].get("total"),
                        "reason": e["decision"]["reason"][:300],
                        "patch": patch_check(e) if e["decision"]["status"] == "healed" else None,
                    }
                    for e in events
                ],
            }
        )
    except (RuntimeError, subprocess.TimeoutExpired, httpx.HTTPError) as exc:
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
        detail = getattr(exc, "stderr", None)  # timeout capture summary (str on timeout)
        if isinstance(exc, subprocess.TimeoutExpired) and isinstance(detail, str):
            error += f" | {detail[:300]}"
        row.update({"outcome": "error", "error": error})
    finally:
        control(store, "reset")
    row["wall_s"] = round(time.perf_counter() - t0, 2)
    return row


def patch_check(event: dict[str, Any]) -> str:
    """G2: re-run ``git apply --check`` on a healed event's diff, independently of the plugin.

    Returns "ok", "no_patch" (no diff, e.g. unpatchable call site: suggestion only)
    or "failed: <git message>". The diff is checked against this repository,
    where the example tests live; nothing is applied.
    """
    diff = event.get("diff")
    if not diff:
        return "no_patch"
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "apply", "--check", "-"],
        cwd=ROOT,
        input=diff.encode("utf-8"),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode == 0:
        return "ok"
    return "failed: " + proc.stderr.decode("utf-8", "replace").strip()[:300]


def pct(values: list[float], p: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)
    return round(statistics.quantiles(values, n=100, method="inclusive")[p - 1], 1)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    healable = [r for r in rows if r["class"] not in ("distractor_trap", "regression_trap")]
    traps = [r for r in rows if r["class"] in ("distractor_trap", "regression_trap")]
    outcomes = Counter(r["outcome"] for r in rows)
    true_heals = sum(1 for r in healable if r["outcome"] == "true_heal")
    accepted = sum(1 for r in rows if any(e["status"] == "healed" for e in r.get("events", [])))
    correct_accepted = sum(
        1
        for r in rows
        if r["outcome"] == "true_heal" and any(e["status"] == "healed" for e in r.get("events", []))
    )
    healed_events = [e for r in rows for e in r.get("events", []) if e["status"] == "healed"]
    t1 = [e["total_ms"] for e in healed_events if e["tier"] == 1 and e["total_ms"] is not None]
    t2 = [e["total_ms"] for e in healed_events if e["tier"] == 2 and e["total_ms"] is not None]
    every = [e["total_ms"] for e in healed_events if e["total_ms"] is not None]
    return {
        "scenarios": len(rows),
        "outcomes": dict(outcomes),
        "true_heal_rate": round(true_heals / len(healable), 4) if healable else None,
        "true_heals": true_heals,
        "healable": len(healable),
        "false_heals_on_traps": sum(1 for r in traps if r["outcome"] == "false_heal"),
        "silent_false_heal_rate": round(outcomes["false_heal"] / len(rows), 4) if rows else None,
        "precision_of_accepted_heals": round(correct_accepted / accepted, 4) if accepted else None,
        "tier1_share_of_heals": round(len(t1) / len(healed_events), 4) if healed_events else None,
        "latency_ms": {
            "tier1": {"p50": pct(t1, 50), "p95": pct(t1, 95), "n": len(t1)},
            "tier2": {"p50": pct(t2, 50), "p95": pct(t2, 95), "n": len(t2)},
            "all_heals": {"p50": pct(every, 50), "p95": pct(every, 95), "n": len(every)},
        },
        "patches": {
            "healed_events": len(healed_events),
            "apply_check_ok": sum(1 for e in healed_events if e.get("patch") == "ok"),
            "no_patch": sum(1 for e in healed_events if e.get("patch") == "no_patch"),
            "failed": sum(1 for e in healed_events if str(e.get("patch", "")).startswith("failed")),
        },
        "provider_failures": provider_failures(rows),
        "errors": outcomes["error"],
    }


def summary_md(result: dict[str, Any]) -> str:
    agg = result["aggregate"]
    lines = [
        f"# Benchmark: {result['system']} on {result['split']} ({result['runs']} run(s), VLM {result['vlm_mode']})",
        "",
        f"Generated from results.json at {result['finished_at']}. Do not edit by hand.",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| True heal rate (healable) | {agg['true_heals']}/{agg['healable']} = {agg['true_heal_rate']} |",
        f"| False heals on traps | {agg['false_heals_on_traps']} |",
        f"| Silent false-heal rate (all) | {agg['silent_false_heal_rate']} |",
        f"| Precision of accepted heals | {agg['precision_of_accepted_heals']} |",
        f"| Tier-1 share of heals | {agg['tier1_share_of_heals']} |",
        f"| Tier-1 heal latency p50 / p95 (ms) | {agg['latency_ms']['tier1']['p50']} / {agg['latency_ms']['tier1']['p95']} |",
        f"| Tier-2 heal latency p50 / p95 (ms) | {agg['latency_ms']['tier2']['p50']} / {agg['latency_ms']['tier2']['p95']} |",
        f"| Heal latency, all heals, p50 / p95 (ms) | {agg['latency_ms']['all_heals']['p50']} / {agg['latency_ms']['all_heals']['p95']} |",
        f"| Healed events whose diff passes `git apply --check` | {agg['patches']['apply_check_ok']}/{agg['patches']['healed_events']} (no patch: {agg['patches']['no_patch']}, failed: {agg['patches']['failed']}) |",
        f"| Scenarios lost to provider failures (rate limit / quota / cap) | {agg.get('provider_failures', 0)} |",
        f"| Outcomes | {agg['outcomes']} |",
        "",
        "| Scenario | Class | Outcome | Heal events |",
        "| --- | --- | --- | --- |",
    ]
    for r in result["rows"]:
        ev = ", ".join(f"{e['status']}(t{e['tier']})" for e in r.get("events", [])) or "-"
        lines.append(f"| {r['id']} | {r['class']} | {r['outcome']} | {ev} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmark.run")
    parser.add_argument("--system", choices=sorted(SYSTEMS), required=True)
    parser.add_argument("--split", choices=("dev", "eval"), default="eval")
    parser.add_argument("--vlm-mode", choices=("live", "record", "replay"), default="replay")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--smoke", action="store_true", help="the 10 smoke scenarios only (CI)")
    parser.add_argument("--only", nargs="*", help="scenario ids to run")
    parser.add_argument("--fail-on-false-heal", action="store_true")
    parser.add_argument("--out", type=Path, default=RESULTS)
    parser.add_argument(
        "--tag",
        type=lambda t: (
            t
            if t.replace("_", "").isalnum() and t.islower()
            else parser.error("--tag: lower-case letters, digits")
        ),
        help="suffix for the results folder, e.g. r1 -> <system>-<split>-r1 (keeps runs apart)",
    )
    parser.add_argument(
        "--rebuild",
        type=Path,
        help="recompute aggregate + summary.md of an existing results folder (no runs)",
    )
    parser.add_argument(
        "--providers",
        help="override HEALWRIGHT_PROVIDERS for the system under test, e.g. groq (eval: Groq only)",
    )
    args = parser.parse_args(argv)
    if args.rebuild:
        path = args.rebuild / "results.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        result["aggregate"] = aggregate(result["rows"])
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        (args.rebuild / "summary.md").write_text(summary_md(result), encoding="utf-8")
        print(f"rebuilt {args.rebuild}")
        return 0
    scenarios = [s for s in iter_scenarios() if s.split == args.split]
    if args.smoke:
        scenarios = [s for s in iter_scenarios() if s.id in SMOKE_10]
    if args.only:
        scenarios = [s for s in scenarios if s.id in set(args.only)]
    started = datetime.now(UTC)
    split = "smoke" if args.smoke else args.split
    name = f"{args.system}-{split}" + (f"-{args.tag}" if args.tag else "")
    # live runs: fresh calls, replies saved to a run-specific folder (never mixed into the
    # shared record/replay cache)
    cache_dir = VLM_CACHE / "live" / name if args.vlm_mode == "live" else None
    rows: list[dict[str, Any]] = []
    calls: dict[str, dict[str, int]] = {}
    with (
        tempfile.TemporaryDirectory(prefix="hw-bench-") as tmp,
        serve_in_thread(control=True) as store,
    ):
        for n in range(args.runs):
            work = Path(tmp) / f"run{n}"
            clean_cache: dict[str, list[str]] = {}
            for s in scenarios:
                row = run_scenario(
                    s,
                    args.system,
                    store,
                    work,
                    clean_cache,
                    args.vlm_mode,
                    n,
                    providers=args.providers,
                    cache_dir=cache_dir,
                )
                row["run"] = n
                rows.append(row)
                print(
                    f"[{args.system}] run {n} {s.id}: {row['outcome']} ({row['wall_s']} s)",
                    flush=True,
                )
            for provider, by_status in provider_calls(work).items():
                for status, count in by_status.items():
                    calls.setdefault(provider, {})
                    calls[provider][status] = calls[provider].get(status, 0) + count
    result = {
        "system": args.system,
        "split": split,
        "vlm_mode": args.vlm_mode,
        "providers": args.providers or "default",
        "pacing": BENCH_PACING,
        "provider_calls": calls,
        "runs": args.runs,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": rows,
        "aggregate": aggregate(rows),
    }
    folder = args.out / started.strftime("%Y-%m-%d") / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (folder / "summary.md").write_text(summary_md(result), encoding="utf-8")
    shown = folder.relative_to(ROOT) if folder.is_relative_to(ROOT) else folder
    print(f"wrote {shown}/results.json")
    print(json.dumps(result["aggregate"], indent=2))
    if args.fail_on_false_heal and (
        result["aggregate"]["outcomes"].get("false_heal") or result["aggregate"]["errors"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
