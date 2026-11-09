"""Tier-2 picker: Set-of-Mark image + router -> a candidate index.

Implements ``engine.Tier2Picker``. Shows the top 15 Tier-1 candidates as
numbered marks; the model may only return one of those numbers or null. A
screenshot failure (after one retry) skips Tier 2 with an error, which the
engine turns into ``needs_human``.
"""

from __future__ import annotations

from collections.abc import Sequence

from playwright.sync_api import Page

from healwright.engine import Tier2Pick
from healwright.errors import BudgetExhausted, ProviderError
from healwright.models import Candidate, ElementFingerprint
from healwright.tier2.prompt import MarkRow, build_prompt, marks_table
from healwright.tier2.router import Router
from healwright.tier2.som import Mark, annotate

MAX_MARKS = 15


class VlmPicker:
    def __init__(self, router: Router, max_marks: int = MAX_MARKS) -> None:
        self.router = router
        self.max_marks = max_marks
        self.last_image: bytes | None = None
        self.last_provider: str | None = None

    def _screenshot(self, page: Page) -> bytes | None:
        for _ in range(2):  # the screenshot gets one retry
            try:
                return page.screenshot(type="png", timeout=5_000)
            except Exception:  # noqa: BLE001 - retried once, then Tier 2 is skipped
                continue
        return None

    def pick(
        self, page: Page, target: ElementFingerprint, action: str, candidates: Sequence[Candidate]
    ) -> Tier2Pick:
        self.last_image = None
        self.last_provider = None
        shown = list(candidates[: self.max_marks])
        if not shown:
            return Tier2Pick(None)
        png = self._screenshot(page)
        if png is None:
            return Tier2Pick(None, error="screenshot failed")
        size = page.viewport_size or {"width": 1280, "height": 800}
        marks, rows = [], []
        for i, c in enumerate(shown, start=1):
            b = c.fingerprint.bbox
            offscreen = (
                b.x + b.w <= 0 or b.y + b.h <= 0 or b.x >= size["width"] or b.y >= size["height"]
            )
            marks.append(Mark(i, b))
            rows.append(
                MarkRow(
                    i,
                    c.fingerprint.role,
                    c.fingerprint.accessible_name,
                    c.fingerprint.text,
                    offscreen,
                )
            )
        try:
            image = annotate(png, marks)
        except Exception as exc:  # noqa: BLE001 - e.g. oversized screenshot: skip Tier 2
            return Tier2Pick(None, error=f"annotation failed: {type(exc).__name__}")
        self.last_image = image
        prompt = build_prompt(target, action, rows)
        try:
            result = self.router.ask(
                prompt, image, set(range(1, len(shown) + 1)), marks_table(rows)
            )
        except BudgetExhausted as exc:
            return Tier2Pick(None, error=str(exc))
        except ProviderError as exc:
            return Tier2Pick(None, error=str(exc)[:300])
        self.last_provider = result.provider
        if result.reply.mark_id is None:
            return Tier2Pick(None)
        return Tier2Pick(result.reply.mark_id - 1)


__all__ = ["MAX_MARKS", "VlmPicker"]
