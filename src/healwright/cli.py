"""Command line.

    healwright apply <event_id>        apply a heal event's patch
    healwright serve [--host 127.0.0.1] [--port 8000]   triage API + built frontend

``apply`` prints a code and message and exits non-zero on failure:
NOT_FOUND, NO_PATCH, SOURCE_CHANGED, PATCH_INVALID (exit 1); ALREADY_APPLIED is a
success. It shares its checks with the API (``healwright.apply``). Unlike the API,
the CLI does not require the heal to be accepted first: running it is the decision.

``healwright report <run_id>`` writes the run's self-contained HTML report and prints its path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _apply(event_id: str) -> int:
    from healwright.apply import apply_event
    from healwright.config import load_settings

    settings = load_settings()
    result = apply_event(Path.cwd(), settings.artifact_dir, event_id)
    stream = sys.stdout if result.ok else sys.stderr
    stream.write(f"{result.code}: {result.message}\n")
    return 0 if result.ok else 1


LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _report(run_id: str) -> int:
    from healwright.config import load_settings
    from healwright.report import write_report
    from healwright.store.index import load_run

    info = load_run(load_settings().artifact_dir, run_id)
    if info is None:
        print(f"NOT_FOUND: no run {run_id}", file=sys.stderr)
        return 1
    print(write_report(info))
    return 0


def _serve(host: str, port: int) -> int:
    from healwright.config import load_settings

    settings = load_settings()
    # A non-local bind needs a token, unless public mode is on: then nothing that writes to
    # the repository is reachable (no triage, no patch apply).
    if host not in LOCAL_HOSTS and settings.api_token is None and not settings.public:
        sys.stderr.write(
            f"healwright: refusing to bind to {host}: set HEALWRIGHT_API_TOKEN first "
            "(every /api request then needs Authorization: Bearer <token>), "
            "or HEALWRIGHT_PUBLIC=1 for a read-only public demo\n"
        )
        return 2

    import uvicorn

    from healwright.api import create_app
    from healwright.logs import setup_logging

    setup_logging(settings.artifact_dir)
    # Behind a proxy (Hugging Face) X-Forwarded-For carries the visitor's address; the
    # cooldown keys on it (healwright.api.public.visitor_id).
    uvicorn.run(create_app(), host=host, port=port, log_level="info", proxy_headers=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="healwright")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="apply a heal event's patch")
    a.add_argument("event_id")
    rp = sub.add_parser("report", help="write a run's self-contained HTML report")
    rp.add_argument("run_id")
    s = sub.add_parser("serve", help="run the triage API and frontend on 127.0.0.1")
    s.add_argument("--host", default="127.0.0.1", help="non-local needs HEALWRIGHT_API_TOKEN")
    s.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.cmd == "apply":
        return _apply(args.event_id)
    if args.cmd == "report":
        return _report(args.run_id)
    return _serve(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
