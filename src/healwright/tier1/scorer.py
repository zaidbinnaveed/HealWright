"""Tier-1 scorer: six features, weighted, no AI.

Every feature score is in [0, 1]. A feature that is undefined for the TARGET
(for example an icon button with no text, or an element with no attributes)
returns ``None`` and its weight is redistributed proportionally over the
defined features. With fixed weights the combined score is a weighted mean,
so it is always in [0, 1], equals 1.0 for identical fingerprints, and never
decreases when one feature score improves.

Candidates whose role is outside the target's compatibility group are never
scored.

Performance: the string features are computed in BATCH, one rapidfuzz call
per target string over all candidates (``process.extract_iter`` runs the loop
in C), instead of one Python->C call per candidate pair. This keeps scoring
300 candidates within the p95 < 10 ms budget.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from rapidfuzz.distance import Indel, JaroWinkler
from rapidfuzz.process import extract_iter

from healwright.models import Candidate, ElementFingerprint

FEATURES = ("role", "text", "attributes", "ancestors", "neighbors", "geometry")

ROLE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"button", "link", "menuitem", "tab"}),
    frozenset({"textbox", "searchbox", "combobox"}),
    frozenset({"checkbox", "switch", "radio"}),
)
SAME_GROUP_ROLE_SCORE = 0.6
ATTRIBUTE_KEYS = ("id", "data-testid", "name", "type", "placeholder", "href")


@dataclass(frozen=True)
class Weights:
    role: float = 0.25
    text: float = 0.25
    attributes: float = 0.15
    ancestors: float = 0.10
    neighbors: float = 0.10
    geometry: float = 0.15
    sigma: float = 0.15  # geometry: exp(-d^2 / sigma^2), d normalised by the viewport diagonal

    def of(self, feature: str) -> float:
        value: float = getattr(self, feature)
        return value


DEFAULT_WEIGHTS = Weights()


# --------------------------------------------------------------------------- roles


def role_group(role: str | None) -> frozenset[str | None]:
    for group in ROLE_GROUPS:
        if role in group:
            return frozenset(group)
    return frozenset({role})


def compatible(target_role: str | None, candidate_role: str | None) -> bool:
    return candidate_role in role_group(target_role)


# --------------------------------------------------------------------------- batch similarity

Scorer = Callable[..., float]


def _batch(query: str, choices: Sequence[str], scorer: Scorer) -> list[float]:
    """Similarity of ``query`` to every choice, in [0, 1], via one C-level loop.

    Semantics match a pairwise call: equal strings score 1.0, and an empty
    string against a non-empty one scores 0.0.
    """
    out = [0.0] * len(choices)
    if not choices:
        return out
    if not query:
        return [1.0 if not c else 0.0 for c in choices]
    for _choice, score, index in extract_iter(query, list(choices), scorer=scorer):
        out[index] = float(score)
    return out


def _text_batch(query: str, choices: Sequence[str]) -> list[float]:
    """Main text feature: mean of Jaro-Winkler and Indel (LCS-based) similarity."""
    jw = _batch(query, choices, JaroWinkler.normalized_similarity)
    indel = _batch(query, choices, Indel.normalized_similarity)
    return [0.5 * a + 0.5 * b for a, b in zip(jw, indel, strict=True)]


# --------------------------------------------------------------------------- scoring


@dataclass(frozen=True)
class PreparedTarget:
    """Target-side values computed once per heal, not once per candidate."""

    role: str | None
    name: str
    text: str
    attr_items: tuple[tuple[str, str], ...]
    classes: frozenset[str]
    ancestors: tuple[str, ...]
    neighbors: tuple[str, ...]
    cx: float
    cy: float
    diag: float
    inv_sigma2: float
    weights: tuple[tuple[str, float], ...]


def prepare(t: ElementFingerprint, weights: Weights = DEFAULT_WEIGHTS) -> PreparedTarget:
    keys = [k for k in ATTRIBUTE_KEYS if k in t.attributes]
    keys += sorted(k for k in t.attributes if k.startswith("aria-"))
    return PreparedTarget(
        role=t.role,
        name=t.accessible_name,
        text=t.text,
        attr_items=tuple((k, t.attributes[k]) for k in keys),
        classes=frozenset(t.class_tokens),
        ancestors=tuple(t.ancestor_path),
        neighbors=tuple(t.neighbor_texts),
        cx=t.bbox.x + t.bbox.w / 2,
        cy=t.bbox.y + t.bbox.h / 2,
        diag=math.hypot(*t.viewport) or 1.0,
        inv_sigma2=1.0 / (weights.sigma * weights.sigma),
        weights=tuple((f, weights.of(f)) for f in FEATURES),
    )


def score_batch(
    p: PreparedTarget, pool: Sequence[ElementFingerprint]
) -> list[dict[str, float | None]]:
    """Feature scores of every candidate in ``pool`` against the prepared target."""
    n = len(pool)
    if n == 0:
        return []

    # text: best of accessible name and visible text
    text: list[float | None] = [None] * n
    if p.name:
        text = list(_text_batch(p.name, [c.accessible_name for c in pool]))
    if p.text:
        by_text = _text_batch(p.text, [c.text for c in pool])
        text = [bt if cur is None else max(cur, bt) for cur, bt in zip(text, by_text, strict=True)]

    # attributes: per-key value similarity (Indel), plus Jaccard over stable class tokens
    attr_sum = [0.0] * n
    for key, value in p.attr_items:
        for i, s in enumerate(
            _batch(value, [c.attributes.get(key, "") for c in pool], Indel.normalized_similarity)
        ):
            attr_sum[i] += s

    # neighbourhood: for each target neighbour, its best match among each candidate's
    neighbors: list[float | None] = [None] * n
    if p.neighbors:
        flat: list[str] = []
        owner: list[int] = []
        for i, c in enumerate(pool):
            flat.extend(c.neighbor_texts)
            owner.extend([i] * len(c.neighbor_texts))
        totals = [0.0] * n
        for query in p.neighbors:
            best = [0.0] * n
            if flat:
                for _choice, score, index in extract_iter(
                    query, flat, scorer=Indel.normalized_similarity
                ):
                    j = owner[index]
                    if score > best[j]:
                        best[j] = float(score)
            for j in range(n):
                totals[j] += best[j]
        k = len(p.neighbors)
        neighbors = [totals[j] / k if pool[j].neighbor_texts else 0.0 for j in range(n)]

    out: list[dict[str, float | None]] = []
    n_attr = len(p.attr_items)
    for i, c in enumerate(pool):
        parts: list[float] = []
        if n_attr:
            parts.append(attr_sum[i] / n_attr)
        if p.classes:
            c_cls = set(c.class_tokens)
            parts.append(len(p.classes & c_cls) / len(p.classes | c_cls))
        b = c.bbox
        d = math.hypot(b.x + b.w / 2 - p.cx, b.y + b.h / 2 - p.cy) / p.diag
        out.append(
            {
                "role": 1.0 if p.role == c.role else SAME_GROUP_ROLE_SCORE,
                "text": text[i],
                "attributes": sum(parts) / len(parts) if parts else None,
                "ancestors": (
                    float(Indel.normalized_similarity(p.ancestors, c.ancestor_path))
                    if p.ancestors
                    else None
                ),
                "neighbors": neighbors[i],
                "geometry": math.exp(-(d * d) * p.inv_sigma2),
            }
        )
    return out


def score_prepared(p: PreparedTarget, c: ElementFingerprint) -> dict[str, float | None]:
    return score_batch(p, [c])[0]


def feature_scores(
    t: ElementFingerprint, c: ElementFingerprint, weights: Weights = DEFAULT_WEIGHTS
) -> dict[str, float | None]:
    return score_prepared(prepare(t, weights), c)


def combine(scores: Mapping[str, float | None], weights: Weights = DEFAULT_WEIGHTS) -> float:
    """Weighted mean over the defined features (undefined weights redistributed)."""
    total_w = 0.0
    total = 0.0
    for feature in FEATURES:
        value = scores.get(feature)
        if value is None:
            continue
        w = weights.of(feature)
        total_w += w
        total += w * min(max(value, 0.0), 1.0)
    return total / total_w if total_w > 0 else 0.0


def score_candidates(
    target: ElementFingerprint,
    candidates: Sequence[ElementFingerprint],
    weights: Weights = DEFAULT_WEIGHTS,
    limit: int | None = None,
) -> list[Candidate]:
    """Role-filter, score and sort (best first; ties by snapshot index).

    Scores every compatible candidate, but builds ``Candidate`` models only for
    the best ``limit`` (all if ``None``). The engine needs at most 15: two for
    the margin gate, fifteen for Tier 2. ``Candidate.index`` is the snapshot index.
    """
    prepared = prepare(target, weights)
    group = role_group(target.role)
    indexed = [(i, fp) for i, fp in enumerate(candidates[:400]) if fp.role in group]
    all_scores = score_batch(prepared, [fp for _, fp in indexed])
    rows: list[tuple[float, int, ElementFingerprint, dict[str, Any]]] = []
    for (index, fp), scores in zip(indexed, all_scores, strict=True):
        total_w = total = 0.0
        for name, w in prepared.weights:
            value = scores[name]
            if value is not None:
                total_w += w
                total += w * value
        rows.append((-(total / total_w) if total_w else 0.0, index, fp, scores))
    rows.sort(key=lambda r: (r[0], r[1]))
    if limit is not None:
        rows = rows[:limit]
    return [
        Candidate(
            index=index,
            fingerprint=fp,
            score=min(max(-neg, 0.0), 1.0),
            feature_scores={k: v for k, v in scores.items() if v is not None},
        )
        for neg, index, fp, scores in rows
    ]


__all__ = [
    "DEFAULT_WEIGHTS",
    "FEATURES",
    "ROLE_GROUPS",
    "PreparedTarget",
    "Weights",
    "combine",
    "compatible",
    "feature_scores",
    "prepare",
    "role_group",
    "score_batch",
    "score_candidates",
    "score_prepared",
]
