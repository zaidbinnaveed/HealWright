"""Apply a heal event's patch. Shared by ``healwright apply`` and the API.

Checks, in order: the event exists (NOT_FOUND), it has a diff (NO_PATCH), it was
accepted when acceptance is required (NOT_ACCEPTED, API only), the source file
still has the SHA-256 recorded at heal time (SOURCE_CHANGED), and
``git apply --check`` passes (PATCH_INVALID). Only then is the patch applied.
Applying twice is a no-op that reports ``already_applied``.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from healwright.patcher import git_apply_check
from healwright.store.index import find_event
from healwright.store.triage import TriageStore

ApplyCode = Literal[
    "APPLIED",
    "ALREADY_APPLIED",
    "NOT_FOUND",
    "NO_PATCH",
    "NOT_ACCEPTED",
    "SOURCE_CHANGED",
    "PATCH_INVALID",
]
_TARGET = re.compile(r"^\+\+\+ b/(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ApplyResult:
    code: ApplyCode
    message: str
    event_id: str
    source_path: str | None = None
    details: dict[str, str | None] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.code in ("APPLIED", "ALREADY_APPLIED")


def diff_target(diff: str) -> str | None:
    """Repo-relative path of the file a single-file unified diff changes."""
    targets = _TARGET.findall(diff)
    if len(targets) != 1:
        return None
    path = str(targets[0])
    if path.startswith("/") or ".." in Path(path).parts:
        return None
    return path


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def apply_event(
    repo_root: Path,
    artifact_root: Path,
    event_id: str,
    *,
    require_accepted: bool = False,
    idempotency_key: str | None = None,
) -> ApplyResult:
    found = find_event(artifact_root, event_id)
    if found is None:
        return ApplyResult("NOT_FOUND", f"no heal event {event_id}", event_id)
    run, event = found
    triage = TriageStore(run.dir)
    record = triage.get(event_id)
    if not event.diff or not event.source_sha256:
        return ApplyResult("NO_PATCH", "this heal event has no patch (suggestion only)", event_id)
    target = diff_target(event.diff)
    if target is None:
        return ApplyResult("PATCH_INVALID", "the diff does not name exactly one file", event_id)
    if record is not None and record.applied:
        return ApplyResult("ALREADY_APPLIED", "patch was already applied", event_id, target)
    if require_accepted and (record is None or record.decision != "accepted"):
        return ApplyResult("NOT_ACCEPTED", "accept the heal before applying it", event_id, target)
    current = sha256_file(repo_root / target)
    if current != event.source_sha256:
        return ApplyResult(
            "SOURCE_CHANGED",
            f"{target} changed after the patch was generated",
            event_id,
            target,
            {"expected_sha256": event.source_sha256, "actual_sha256": current},
        )
    ok, err = git_apply_check(repo_root, event.diff)
    if not ok:
        return ApplyResult(
            "PATCH_INVALID", f"git apply --check failed: {err[:300]}", event_id, target
        )
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "apply", "-"],
        cwd=repo_root,
        input=event.diff.encode("utf-8"),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()[:300]
        return ApplyResult("PATCH_INVALID", f"git apply failed: {msg}", event_id, target)
    triage.mark_applied(event_id, idempotency_key)
    return ApplyResult("APPLIED", f"patched {target}", event_id, target)


__all__ = ["ApplyCode", "ApplyResult", "apply_event", "diff_target", "sha256_file"]
