"""Triage decisions per run: ``<artifact_dir>/runs/<run_id>/triage.json``.

``events.jsonl`` is append-only and written by the plugin during a test run, so
triage (a later, human decision) lives in a sidecar instead of rewriting events.
The effective ``triage_status`` of an event is derived from both (``effective``).

File format (schema_version 1)::

    {"schema_version": 1,
     "events": {"<event_id>": {"decision": "accepted" | "rejected",
                               "note": "...", "applied": false,
                               "updated_at": "<iso>", "idempotency_key": null}}}

Writes are atomic (temp file + replace) under a file lock.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Decision = Literal["accepted", "rejected"]
MAX_NOTE_LEN = 1000


class TriageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision | None = None
    note: Annotated[str, StringConstraints(max_length=MAX_NOTE_LEN)] = ""
    applied: bool = False
    updated_at: str = ""
    idempotency_key: Annotated[str, StringConstraints(max_length=200)] | None = None


class TriageFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    events: Annotated[dict[str, TriageRecord], Field(max_length=10_000)] = {}


def effective(record: TriageRecord | None) -> Literal["pending", "accepted", "rejected", "applied"]:
    if record is None or record.decision is None:
        return "applied" if record is not None and record.applied else "pending"
    if record.applied:
        return "applied"
    return record.decision


class TriageStore:
    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "triage.json"
        self._lock = FileLock(str(run_dir / ".triage.lock"))

    def load(self) -> TriageFile:
        if not self.path.is_file():
            return TriageFile()
        return TriageFile.model_validate_json(self.path.read_text(encoding="utf-8"))

    def get(self, event_id: str) -> TriageRecord | None:
        return self.load().events.get(event_id)

    def _write(self, data: TriageFile) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data.model_dump(), indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def decide(self, event_id: str, decision: Decision, note: str) -> TriageRecord:
        with self._lock:
            data = self.load()
            current = data.events.get(event_id, TriageRecord())
            record = current.model_copy(
                update={
                    "decision": decision,
                    "note": note,
                    "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
            data.events[event_id] = TriageRecord.model_validate(record.model_dump())
            self._write(data)
            return data.events[event_id]

    def mark_applied(self, event_id: str, idempotency_key: str | None) -> TriageRecord:
        with self._lock:
            data = self.load()
            current = data.events.get(event_id, TriageRecord())
            record = current.model_copy(
                update={
                    "applied": True,
                    "idempotency_key": idempotency_key,
                    "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
            data.events[event_id] = TriageRecord.model_validate(record.model_dump())
            self._write(data)
            return data.events[event_id]


__all__ = ["Decision", "TriageFile", "TriageRecord", "TriageStore", "effective"]
