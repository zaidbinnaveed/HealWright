"""Download the website's display/body fonts from Fontshare into frontend/public/fonts/.

    uv run python scripts/fetch_fonts.py

Clash Display and Satoshi are free under the ITF Free Font License (FFL): self-hosting on our own
site is allowed, but the font files may not be redistributed (section 02), so they are not
committed (frontend/public/fonts/ is git-ignored). Run this once per clone before `npm run build`.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import httpx

DEST = Path(__file__).resolve().parents[1] / "frontend" / "public" / "fonts"
FONTS = {
    "clash-display": ["ClashDisplay-Variable.woff2"],
    "satoshi": ["Satoshi-Variable.woff2", "Satoshi-VariableItalic.woff2"],
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for slug, wanted in FONTS.items():
        if all((DEST / w).is_file() for w in wanted):
            print(f"{slug}: present")
            continue
        url = f"https://api.fontshare.com/v2/fonts/download/{slug}"
        res = httpx.get(
            url, headers={"User-Agent": "healwright-build"}, timeout=60, follow_redirects=True
        )
        res.raise_for_status()
        archive = zipfile.ZipFile(io.BytesIO(res.content))
        for name in archive.namelist():
            base = name.rsplit("/", 1)[-1]
            if base in wanted and "/WEB/" in name:
                (DEST / base).write_bytes(archive.read(name))
                print(f"{slug}: {base}")
        missing = [w for w in wanted if not (DEST / w).is_file()]
        if missing:
            print(f"{slug}: missing {missing}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
