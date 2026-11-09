"""Read-only index over ``<artifact_dir>/runs/*`` for the API and the CLI.

Run ids and event ids are ULIDs, so lexical order is time order. Lines that do
not parse as a ``HealEvent`` are skipped and counted, never raised: one corrupt
line must not hide a whole run.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from ulid import ULID

from healwright.models import HealEvent

log = logging.getLogger("healwright.store")
ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")


@dataclass
class RunInfo:
    run_id: str
    dir: Path
    events: list[HealEvent] = field(default_factory=list)
    skipped_lines: int = 0

    @property
    def started_at(self) -> str:
        return ULID.from_str(self.run_id).datetime.astimezone(UTC).isoformat(timespec="seconds")


def is_ulid(value: str) -> bool:
    return bool(ULID_RE.match(value))


def runs_dir(artifact_root: Path) -> Path:
    return artifact_root / "runs"


def run_ids(artifact_root: Path) -> list[str]:
    """All run ids, newest first."""
    root = runs_dir(artifact_root)
    if not root.is_dir():
        return []
    return sorted((p.name for p in root.iterdir() if p.is_dir() and is_ulid(p.name)), reverse=True)


def load_run(artifact_root: Path, run_id: str) -> RunInfo | None:
    if not is_ulid(run_id):
        return None
    folder = runs_dir(artifact_root) / run_id
    if not folder.is_dir():
        return None
    info = RunInfo(run_id=run_id, dir=folder)
    path = folder / "events.jsonl"
    if path.exists():  # exists but unreadable (permissions, a directory): OSError, not "empty"
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                info.events.append(HealEvent.model_validate_json(line))
            except ValidationError:
                info.skipped_lines += 1
    if info.skipped_lines:
        log.warning("healwright: %d unreadable event lines in %s", info.skipped_lines, path)
    return info


def find_event(artifact_root: Path, event_id: str) -> tuple[RunInfo, HealEvent] | None:
    if not is_ulid(event_id):
        return None
    for run_id in run_ids(artifact_root):
        info = load_run(artifact_root, run_id)
        if info is None:
            continue
        for event in info.events:
            if event.id == event_id:
                return info, event
    return None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


__all__ = ["RunInfo", "find_event", "is_ulid", "load_run", "run_ids", "runs_dir"]
