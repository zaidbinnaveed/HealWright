"""Tier-1 scorer and decision-margin gate. No AI."""

from healwright.tier1.gate import GateResult, decide, escalation_set
from healwright.tier1.scorer import (
    DEFAULT_WEIGHTS,
    FEATURES,
    Weights,
    combine,
    compatible,
    feature_scores,
    score_candidates,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "FEATURES",
    "GateResult",
    "Weights",
    "combine",
    "compatible",
    "decide",
    "escalation_set",
    "feature_scores",
    "score_candidates",
]
