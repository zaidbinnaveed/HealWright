"""Set-of-Mark annotation: numbered boxes on a viewport screenshot.

Pillow only (no OpenCV). Output: JPEG, quality 80, at most 1280 px wide. The
screenshot must be taken with device scale factor 1 so CSS px == image px.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from healwright.models import BBox

MAX_WIDTH = 1280
JPEG_QUALITY = 80
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
COLORS = ("#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#008080", "#9a6324", "#800000")


@dataclass(frozen=True)
class Mark:
    id: int
    bbox: BBox


def annotate(png: bytes, marks: Sequence[Mark]) -> bytes:
    if len(png) > MAX_SCREENSHOT_BYTES:
        raise ValueError("screenshot exceeds 5 MB")
    image = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for mark in marks:
        color = COLORS[(mark.id - 1) % len(COLORS)]
        b = mark.bbox
        x0, y0 = max(b.x, 0), max(b.y, 0)
        x1, y1 = min(b.x + b.w, image.width - 1), min(b.y + b.h, image.height - 1)
        if x1 <= x0 or y1 <= y0:
            continue  # off-screen: listed in the marks table, not drawn
        draw.rectangle((x0, y0, x1, y1), outline=color, width=3)
        label = str(mark.id)
        tx, ty = x0, max(y0 - 16, 0)
        tw = draw.textlength(label, font=font)
        draw.rectangle((tx, ty, tx + tw + 8, ty + 15), fill=color)
        draw.text((tx + 4, ty + 2), label, fill="white", font=font)
    if image.width > MAX_WIDTH:
        ratio = MAX_WIDTH / image.width
        image = image.resize((MAX_WIDTH, int(image.height * ratio)))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


__all__ = ["JPEG_QUALITY", "MAX_WIDTH", "Mark", "annotate"]
