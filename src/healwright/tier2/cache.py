"""VLM response cache: one JSON file per request under ``cache/``.

Key = SHA-256(model, prompt version, image hash, marks table). Modes:
``live`` (always call), ``record`` (use cache, call and store on miss),
``replay`` (cache only; a miss is an error). Replay makes benchmark reruns,
the demo and CI cost zero API calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

VlmMode = Literal["live", "record", "replay"]


def cache_key(model: str, prompt_version: str, image: bytes, marks: str) -> str:
    h = hashlib.sha256()
    for part in (
        model.encode(),
        prompt_version.encode(),
        hashlib.sha256(image).digest(),
        marks.encode("utf-8"),
    ):
        h.update(len(part).to_bytes(8, "big"))
        h.update(part)
    return h.hexdigest()


class ResponseCache:
    def __init__(self, root: Path, mode: VlmMode) -> None:
        self.root = root
        self.mode = mode

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> str | None:
        if self.mode == "live":
            return None
        path = self.path(key)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        raw: str = data["raw"]
        return raw

    def put(self, key: str, raw: str, provider: str, model: str) -> None:
        if self.mode == "replay":
            return  # live: reads bypass the cache, but replies are still saved (audit)
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"provider": provider, "model": model, "raw": raw}, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=self.root)
        replaced = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path(key))
            replaced = True
        finally:
            if not replaced:
                Path(tmp).unlink(missing_ok=True)


__all__ = ["ResponseCache", "VlmMode", "cache_key"]
