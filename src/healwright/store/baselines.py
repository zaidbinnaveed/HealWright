"""Baseline files: one JSON file per test, committed with the tests.

Path: ``<baseline_dir>/<test-file>/<test-name>.json``. Each step keeps its
last 3 observations; the stored contract is their stable intersection.
Writes are atomic (temp file + ``os.replace``) under a ``filelock`` and happen
only when the content changes, so a stable suite produces no git churn.

File format (store schema v1):
``{"schema_version": 1, "test_nodeid": ..., "steps": [{"baseline": Baseline,
"history": [PostConditionSignature, ...]}]}``
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from healwright import __version__
from healwright.errors import BaselineCorrupt
from healwright.models import Baseline, ElementFingerprint, PostConditionSignature, StepKey
from healwright.recorder.contract import MAX_HISTORY, merge

log = logging.getLogger("healwright.store")
STORE_SCHEMA_VERSION = 1
LOCK_NAME = ".baselines.lock"
_UNSAFE = re.compile(r"[^A-Za-z0-9_.\-\[\]]")


class StepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline: Baseline
    history: Annotated[list[PostConditionSignature], Field(min_length=1, max_length=MAX_HISTORY)]


class BaselineFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    test_nodeid: Annotated[str, Field(min_length=1, max_length=1000)]
    steps: list[StepRecord]

    def find(self, key: StepKey) -> StepRecord | None:
        return next((s for s in self.steps if s.baseline.key == key), None)


@dataclass(frozen=True)
class ObservedStep:
    """What the recorder saw for one step in one passing run."""

    key: StepKey
    fingerprint: ElementFingerprint | None
    observation: PostConditionSignature | None
    source_line: int | None


def baseline_path(root: Path, test_nodeid: str) -> Path:
    file_part, _, name = test_nodeid.partition("::")
    parts = [
        p
        for p in PurePosixPath(file_part.replace("\\", "/")).parts
        if p not in ("", ".", "..", "/")
    ]
    safe_parts = [_UNSAFE.sub("_", p)[:100] for p in parts] or ["_"]
    safe_name = _UNSAFE.sub("_", name or "test")[:150]
    return root.joinpath(*safe_parts) / f"{safe_name}.json"


def load(path: Path) -> BaselineFile | None:
    """Missing file or unknown schema version -> ``None``; unreadable -> ``BaselineCorrupt``."""
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BaselineCorrupt(f"{path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise BaselineCorrupt(f"{path.name}: not a JSON object")
    if raw.get("schema_version") != STORE_SCHEMA_VERSION:
        log.warning("healwright: unknown baseline schema in %s; treated as missing", path)
        return None
    try:
        return BaselineFile.model_validate(raw)
    except ValidationError as exc:
        steps = raw.get("steps")
        versions = (
            {
                s.get("baseline", {}).get("fingerprint", {}).get("schema_version")
                for s in steps
                if isinstance(s, dict)
            }
            if isinstance(steps, list)
            else set()
        )
        if versions - {1, None}:
            log.warning("healwright: unknown fingerprint schema in %s; treated as missing", path)
            return None
        raise BaselineCorrupt(f"{path.name}: {exc.error_count()} validation errors") from exc


def merge_observed(
    test_nodeid: str,
    existing: BaselineFile | None,
    observed: Sequence[ObservedStep],
    now: datetime | None = None,
) -> BaselineFile:
    """New file content for a passing run. Steps without a fingerprint or
    observation (e.g. element not yet rendered when captured) are skipped;
    steps no longer executed by the test are dropped."""
    now = now or datetime.now(UTC)
    records: list[StepRecord] = []
    seen: set[StepKey] = set()
    for step in observed:
        if step.fingerprint is None or step.observation is None or step.key in seen:
            continue
        seen.add(step.key)
        old = existing.find(step.key) if existing else None
        history = ([*old.history] if old else []) + [step.observation]
        history = history[-MAX_HISTORY:]
        source_line = step.source_line or (old.baseline.source_line if old else 1)
        candidate = Baseline(
            key=step.key,
            fingerprint=step.fingerprint,
            contract=merge(history),
            source_line=source_line,
            recorded_at=now,
            healwright_version=__version__,
        )
        if (
            old is not None
            and old.history == history
            and old.baseline.model_copy(update={"recorded_at": now}) == candidate
        ):
            records.append(old)  # unchanged: keep the original timestamp
        else:
            records.append(StepRecord(baseline=candidate, history=history))
    return BaselineFile(test_nodeid=test_nodeid, steps=records)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
        replaced = True
    finally:
        if not replaced:
            Path(tmp).unlink(missing_ok=True)


def record_passing_run(root: Path, test_nodeid: str, observed: Sequence[ObservedStep]) -> bool:
    """Merge one passing run into the test's baseline file. Returns True if written."""
    path = baseline_path(root, test_nodeid)
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / LOCK_NAME), timeout=10):
        try:
            existing = load(path)
        except BaselineCorrupt:
            log.warning("healwright: corrupt baseline %s replaced by a fresh recording", path)
            existing = None
        new = merge_observed(test_nodeid, existing, observed)
        if not new.steps:
            return False
        if existing is not None and new == existing:
            return False
        _atomic_write(path, new.model_dump_json(indent=2) + "\n")
        return True


__all__ = [
    "LOCK_NAME",
    "STORE_SCHEMA_VERSION",
    "BaselineFile",
    "ObservedStep",
    "StepRecord",
    "baseline_path",
    "load",
    "merge_observed",
    "record_passing_run",
]
