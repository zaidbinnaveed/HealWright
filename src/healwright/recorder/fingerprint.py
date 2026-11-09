"""Convert an extract.js row into an ``ElementFingerprint``.

Used identically at record time (target mode) and heal time (snapshot rows),
so the scorer always compares like with like.
"""

from __future__ import annotations

from typing import Any

from healwright.models import (
    MAX_ANCESTORS,
    MAX_ATTR_VALUE_LEN,
    MAX_ATTRIBUTES,
    MAX_NEIGHBORS,
    MAX_TEXT_LEN,
    BBox,
    ElementFingerprint,
)
from healwright.recorder.extract import FIELDS
from healwright.verify.normalize import normalize_text, stable_class_tokens


def fingerprint_from_row(
    row: list[Any], viewport: list[int] | tuple[int, int]
) -> ElementFingerprint:
    data = dict(zip(FIELDS, row, strict=True))
    attrs_in: dict[str, Any] = data["attrs"] or {}
    attributes: dict[str, str] = {}
    for key, value in list(attrs_in.items())[:MAX_ATTRIBUTES]:
        if value is None or not key:
            continue
        attributes[str(key)[:100]] = str(value)[:MAX_ATTR_VALUE_LEN]
    neighbors = []
    for text in data["neighbors"] or []:
        norm = normalize_text(text, MAX_TEXT_LEN)
        if norm and norm not in neighbors:
            neighbors.append(norm)
    x, y, w, h = (float(v) for v in data["bbox"])
    role = data["role"]
    return ElementFingerprint(
        role=normalize_text(role, MAX_TEXT_LEN) or None if role else None,
        accessible_name=normalize_text(data["name"], MAX_TEXT_LEN),
        tag=str(data["tag"])[:50] or "unknown",
        text=normalize_text(data["text"], MAX_TEXT_LEN),
        attributes=attributes,
        class_tokens=stable_class_tokens([str(c) for c in data["classes"] or []]),
        ancestor_path=[str(a)[:100] for a in (data["ancestors"] or [])[:MAX_ANCESTORS]],
        neighbor_texts=neighbors[:MAX_NEIGHBORS],
        bbox=BBox(x=x, y=y, w=max(w, 0.0), h=max(h, 0.0)),
        viewport=(int(viewport[0]), int(viewport[1])),
        in_shadow_dom=bool(data["in_shadow"]),
    )


__all__ = ["fingerprint_from_row"]
