"""Assemble frontend/.vercel/output (Vercel Build Output API v3) from dist-showcase/.

    uv run --with imageio-ffmpeg python scripts/build_showcase.py
    cd frontend && npm run build:showcase && cd ..
    uv run python scripts/make_vercel_output.py
    cd frontend && npx vercel deploy --prebuilt --prod

Why not ``vercel build``: on Windows its builder cache needs symlinks, which fail with
EPERM without Developer Mode. A static site needs no builder: the output is the built
files plus a route config equivalent to frontend/vercel.json (immutable cache headers on
/assets, files first, then the SPA fallback for every route except /showcase and /assets).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist-showcase"
OUTPUT = ROOT / "frontend" / ".vercel" / "output"

CONFIG = {
    "version": 3,
    "routes": [
        {
            "src": "^/assets/(.*)$",
            "headers": {"Cache-Control": "public, max-age=31536000, immutable"},
            "continue": True,
        },
        {"handle": "filesystem"},
        {"src": "^/(?!showcase/|assets/).*$", "dest": "/index.html"},
    ],
}


def main() -> None:
    if not (DIST / "index.html").is_file():
        raise SystemExit(f"{DIST} has no index.html: run `npm run build:showcase` first")
    if not (DIST / "showcase" / "data" / "runs.json").is_file():
        raise SystemExit("dist-showcase has no data snapshot: run scripts/build_showcase.py first")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.copytree(DIST, OUTPUT / "static")
    (OUTPUT / "config.json").write_text(json.dumps(CONFIG, indent=2) + "\n", encoding="utf-8")
    files = sum(1 for p in (OUTPUT / "static").rglob("*") if p.is_file())
    print(f"wrote {OUTPUT} ({files} static files)")


if __name__ == "__main__":
    main()
