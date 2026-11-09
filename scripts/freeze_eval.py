"""Write benchmark/eval_freeze.json: SHA-256 of every eval scenario file.

Usage: uv run python scripts/freeze_eval.py
Run ONCE, before any tuning, then commit. tests/integration/test_scenarios.py
fails if any eval file changes afterwards. Never re-freeze to absorb tuning.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    files = sorted((ROOT / "chaos_store" / "scenarios" / "eval").glob("*.yaml"))
    manifest = {
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "count": len(files),
        "files": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
    }
    out = ROOT / "benchmark" / "eval_freeze.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"froze {len(files)} eval scenarios -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
