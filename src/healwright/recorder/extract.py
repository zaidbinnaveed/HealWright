"""Python side of extract.js: load the script once, run it in one round trip.

Conversion of rows into ``ElementFingerprint`` (with text normalisation)
happens in the recorder.
"""

from __future__ import annotations

from functools import cache
from importlib.resources import files
from typing import Any, Literal, TypedDict

from playwright.sync_api import ElementHandle, Page

FIELDS = (
    "role",
    "name",
    "tag",
    "text",
    "attrs",
    "classes",
    "ancestors",
    "neighbors",
    "bbox",
    "in_shadow",
)


class Snapshot(TypedDict):
    v: int
    mode: Literal["snapshot", "target"]
    fields: list[str]
    viewport: list[int]
    has_iframes: bool
    has_shadow_roots: bool
    total: int
    truncated: bool
    rows: list[list[Any]]
    ms: float
    state: dict[str, int]


@cache
def extract_js() -> str:
    return files("healwright.recorder").joinpath("extract.js").read_text(encoding="utf-8")


def extract(
    page: Page,
    *,
    target: ElementHandle | None = None,
    keep: bool = False,
    max_candidates: int = 400,
) -> Snapshot:
    """Run extract.js once. ``target`` switches to single-element mode."""
    arg: dict[str, Any] = {"max": max_candidates, "keep": keep}
    if target is not None:
        arg["target"] = target
    result: Snapshot = page.evaluate(extract_js(), arg)
    return result


def target_expression() -> str:
    """JS for ``locator.evaluate_all``: target-mode extraction of the first match.

    ``evaluate_all`` does not wait, so this never delays the user's action; if
    nothing matches yet it returns only the page state (``rows == []``).
    """
    return (
        "(els) => { const extract = (\n"
        + extract_js()
        + "\n); return extract({ target: els.length ? els[0] : null }); }"
    )


def row_as_dict(row: list[Any]) -> dict[str, Any]:
    return dict(zip(FIELDS, row, strict=True))


__all__ = ["FIELDS", "Snapshot", "extract", "extract_js", "row_as_dict", "target_expression"]
