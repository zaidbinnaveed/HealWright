"""Decision-margin gate: accept top-1 only if it is confident AND clearly ahead.

    accept  <=>  score(top1) >= tau_conf  AND  score(top1) - score(top2) >= delta_margin

With a single compatible candidate, top2 counts as 0. A failed gate escalates
to Tier 2 with the top candidates; it never picks anyway.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from healwright.models import Candidate

EPS = 1e-9  # float tolerance so a margin of exactly delta is accepted


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    top: Candidate | None
    margin: float
    reason: str


def decide(ranked: Sequence[Candidate], tau_conf: float, delta_margin: float) -> GateResult:
    if not ranked:
        return GateResult(False, None, 0.0, "no compatible candidate")
    top = ranked[0]
    second = ranked[1].score if len(ranked) > 1 else 0.0
    margin = top.score - second
    if top.score + EPS < tau_conf:
        return GateResult(False, top, margin, f"top score {top.score:.3f} < tau {tau_conf:.2f}")
    if margin + EPS < delta_margin:
        return GateResult(False, top, margin, f"margin {margin:.3f} < delta {delta_margin:.2f}")
    return GateResult(True, top, margin, f"score {top.score:.3f}, margin {margin:.3f}")


def escalation_set(ranked: Sequence[Candidate], k: int = 15) -> list[Candidate]:
    """Top-k candidates handed to Tier 2 when the gate fails."""
    return list(ranked[:k])


__all__ = ["GateResult", "decide", "escalation_set"]
