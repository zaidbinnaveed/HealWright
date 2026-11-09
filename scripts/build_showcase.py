"""Generate frontend/showcase-public/ for the hosted, backend-free showcase build.

    uv run --with imageio-ffmpeg python scripts/build_showcase.py
    cd frontend && npm run build:showcase          # -> frontend/dist-showcase/

What it writes (nothing here is committed):
- a copy of frontend/public/ (favicons, social card, the fetched fonts);
- showcase/data/: a snapshot of real data, laid out like the API and read by the
  frontend in showcase mode: every run and heal event in the local artifact folder,
  their screenshots, candidate reports and patches, and the final eval benchmark
  (benchmark/results/eval-combined). Taken in-process from the API app, no server needed;
- showcase/media/: the backup demo video as a web MP4 (H.264, faststart) plus a poster
  frame, from docs/presentation/healwright-demo.webm (record it with record_demo.py).

ffmpeg comes from the imageio-ffmpeg wheel (``uv run --with``), or ``--ffmpeg PATH``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from healwright.api import create_app

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"
OUT = ROOT / "frontend" / "showcase-public"
DATA = OUT / "showcase" / "data"
MEDIA = OUT / "showcase" / "media"
VIDEO_IN = ROOT / "docs" / "presentation" / "healwright-demo.webm"
API = "/api/v1"
MAX_VIDEO_MB = 10.0


def write_json(rel: str, data: Any) -> None:
    path = DATA / f"{rel}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def static_urls(event: dict[str, Any]) -> dict[str, Any]:
    """Point an event's artifact URLs at the static copies."""
    urls = event.get("artifact_urls") or {}
    event["artifact_urls"] = {
        k: v.replace(f"{API}/heal-events/", "/showcase/data/heal-events/") for k, v in urls.items()
    }
    return event


def snapshot(client: TestClient) -> tuple[int, int]:
    def get(path: str) -> Any:
        res = client.get(API + path)
        res.raise_for_status()
        return res.json()

    runs: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = get("/runs?limit=100" + (f"&cursor={cursor}" if cursor else ""))
        runs += page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    write_json("runs", {"items": runs, "next_cursor": None})

    events = 0
    for run in runs:
        detail = get(f"/runs/{run['run_id']}")
        detail["events"] = [static_urls(e) for e in detail["events"]]
        write_json(f"runs/{run['run_id']}", detail)
        for ev in detail["events"]:
            eid = ev["id"]
            raw = get(f"/heal-events/{eid}")
            for url in (raw.get("artifact_urls") or {}).values():
                res = client.get(url)
                res.raise_for_status()
                dest = DATA / url.removeprefix(f"{API}/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(res.content)
            write_json(f"heal-events/{eid}", static_urls(raw))
            if raw.get("diff"):
                write_json(f"heal-events/{eid}/patch", get(f"/heal-events/{eid}/patch"))
            events += 1

    write_json("benchmarks/combined", get("/benchmarks/combined"))
    return len(runs), events


def find_ffmpeg(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError:
        found = shutil.which("ffmpeg")
        if found:
            return found
    raise SystemExit("no ffmpeg: run with `uv run --with imageio-ffmpeg` or pass --ffmpeg")


def video(ffmpeg: str, crf: int) -> float:
    if not VIDEO_IN.is_file():
        raise SystemExit(f"{VIDEO_IN} is missing: record it with scripts/record_demo.py")
    MEDIA.mkdir(parents=True, exist_ok=True)
    mp4 = MEDIA / "healwright-demo.mp4"
    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(VIDEO_IN)]
    subprocess.run(
        [
            *base,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        check=True,
    )
    # Poster: the broken product page with the outlined button (about 30 s in).
    subprocess.run(
        [
            *base,
            "-ss",
            "30",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(MEDIA / "healwright-demo-poster.jpg"),
        ],
        check=True,
    )
    return mp4.stat().st_size / 1e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ffmpeg", help="path to an ffmpeg with libx264")
    ap.add_argument("--crf", type=int, default=28, help="H.264 quality (higher = smaller)")
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(PUBLIC, OUT)
    if not (OUT / "fonts").is_dir():
        print("note: frontend/public/fonts/ is missing; run scripts/fetch_fonts.py to include them")

    with TestClient(create_app()) as client:
        n_runs, n_events = snapshot(client)
    size = video(find_ffmpeg(args.ffmpeg), args.crf)
    if size > MAX_VIDEO_MB:
        raise SystemExit(
            f"demo MP4 is {size:.1f} MB (> {MAX_VIDEO_MB} MB): rerun with a higher --crf"
        )
    print(
        f"showcase: {n_runs} runs, {n_events} heal events, benchmark, video {size:.1f} MB -> {OUT}"
    )


if __name__ == "__main__":
    main()
