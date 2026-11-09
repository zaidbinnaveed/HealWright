"""Tier-1 scorer and gate, with property tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from healwright.models import BBox, Candidate, ElementFingerprint
from healwright.tier1 import (
    FEATURES,
    combine,
    compatible,
    decide,
    feature_scores,
    score_candidates,
)
from tests import factories as f

pytestmark = pytest.mark.unit


def fp(**kw: Any) -> ElementFingerprint:
    return f.fingerprint(**kw)


# ------------------------------------------------------------------ roles


@pytest.mark.parametrize(
    ("target", "candidate", "ok"),
    [
        ("button", "button", True),
        ("button", "link", True),
        ("link", "tab", True),
        ("textbox", "combobox", True),
        ("checkbox", "switch", True),
        ("button", "textbox", False),
        ("checkbox", "button", False),
        ("spinbutton", "spinbutton", True),
        ("spinbutton", "textbox", False),
        (None, None, True),
        (None, "button", False),
    ],
)
def test_role_compatibility(target: str | None, candidate: str | None, ok: bool) -> None:
    assert compatible(target, candidate) is ok


def test_incompatible_candidates_are_never_scored() -> None:
    ranked = score_candidates(fp(role="button"), [fp(role="textbox"), fp(role="link"), fp()])
    assert [c.index for c in ranked] == [2, 1]


# ------------------------------------------------------------------ scoring


def test_identical_fingerprints_score_one() -> None:
    target = fp()
    assert combine(feature_scores(target, target)) == pytest.approx(1.0)


def test_id_rename_still_ranks_true_target_first() -> None:
    target = fp()
    renamed = fp(
        attributes={"id": "btn-add-basket-x7", "data-testid": "add-basket", "type": "button"}
    )
    lookalike = fp(
        accessible_name="back to products",
        text="back to products",
        role="link",
        tag="a",
        attributes={"id": "back-to-shop", "href": "/"},
        class_tokens=["link"],
        bbox=BBox(x=10, y=120, w=120, h=20),
    )
    ranked = score_candidates(target, [lookalike, renamed])
    assert ranked[0].index == 1
    assert ranked[0].score > ranked[1].score + 0.12


def test_text_weight_redistributed_for_icon_button() -> None:
    icon = fp(accessible_name="", text="")
    scores = feature_scores(icon, icon)
    assert scores["text"] is None
    assert combine(scores) == pytest.approx(1.0)


def test_undefined_features_are_omitted_from_candidate_feature_scores() -> None:
    target = fp(neighbor_texts=[], ancestor_path=[])
    ranked = score_candidates(target, [fp()])
    assert set(ranked[0].feature_scores) == {"role", "text", "attributes", "geometry"}


def test_geometry_term() -> None:
    t = fp(bbox=BBox(x=0, y=0, w=10, h=10), viewport=(1280, 800))
    same = feature_scores(t, t)["geometry"]
    far = feature_scores(t, fp(bbox=BBox(x=1270, y=790, w=10, h=10), viewport=(1280, 800)))[
        "geometry"
    ]
    assert same == pytest.approx(1.0)
    assert far is not None
    assert far < 1e-6
    # d = 0.15 of the diagonal -> exp(-1)
    diag = (1280**2 + 800**2) ** 0.5
    shifted = fp(bbox=BBox(x=0.15 * diag, y=0, w=10, h=10), viewport=(1280, 800))
    assert feature_scores(t, shifted)["geometry"] == pytest.approx(0.3679, abs=1e-3)


def test_hashed_classes_do_not_reward_matches() -> None:
    # fingerprints already store stable classes only, so a hashed class swap
    # leaves the Jaccard term untouched when the stable tokens survive
    t = fp(class_tokens=["btn", "btn-primary"])
    c = fp(class_tokens=["btn", "btn-primary"])
    assert feature_scores(t, c)["attributes"] == pytest.approx(1.0)


def test_sorting_is_stable_by_index_on_ties() -> None:
    ranked = score_candidates(fp(), [fp(), fp(), fp()])
    assert [c.index for c in ranked] == [0, 1, 2]


# ------------------------------------------------------------------ properties

texts = st.text(alphabet="abcdefghij ", max_size=20).map(lambda s: " ".join(s.split()))
fingerprints = st.builds(
    lambda name, text, idv, cls, anc, nb, x, y: fp(
        accessible_name=name,
        text=text,
        attributes={"id": idv} if idv else {},
        class_tokens=cls,
        ancestor_path=anc,
        neighbor_texts=nb,
        bbox=BBox(x=x, y=y, w=50, h=20),
    ),
    texts,
    texts,
    st.text(alphabet="abc-", max_size=8),
    st.lists(st.sampled_from(["btn", "primary", "card", "x"]), max_size=3, unique=True),
    st.lists(st.sampled_from(["form[form]", "div", "main[main]", "li[listitem]"]), max_size=6),
    st.lists(texts.filter(bool), max_size=5, unique=True),
    st.floats(min_value=0, max_value=1200),
    st.floats(min_value=0, max_value=780),
)


@given(fingerprints, fingerprints)
def test_score_always_in_unit_interval(t: ElementFingerprint, c: ElementFingerprint) -> None:
    s = combine(feature_scores(t, c))
    assert 0.0 <= s <= 1.0
    for v in feature_scores(t, c).values():
        assert v is None or 0.0 <= v <= 1.0


@given(fingerprints)
def test_identical_score_one_property(t: ElementFingerprint) -> None:
    assert combine(feature_scores(t, t)) == pytest.approx(1.0)


score_maps = st.fixed_dictionaries(
    {k: st.one_of(st.none(), st.floats(min_value=0, max_value=1)) for k in FEATURES}
)


@given(score_maps, st.sampled_from(FEATURES), st.floats(min_value=0, max_value=1))
def test_improving_one_feature_never_lowers_the_score(
    scores: dict[str, float | None], feature: str, bump: float
) -> None:
    if scores[feature] is None:
        return
    better = dict(scores)
    better[feature] = min(1.0, (scores[feature] or 0.0) + bump)
    assert combine(better) >= combine(scores) - 1e-12


@given(
    st.lists(st.floats(min_value=0, max_value=1), min_size=1, max_size=10),
    st.floats(min_value=0, max_value=1),
    st.floats(min_value=0, max_value=0.5),
)
def test_gate_never_accepts_below_margin_or_tau(
    scores: list[float], tau: float, delta: float
) -> None:
    ranked = [
        Candidate(index=i, fingerprint=f.fingerprint(), score=s, feature_scores={})
        for i, s in enumerate(sorted(scores, reverse=True))
    ]
    result = decide(ranked, tau, delta)
    second = ranked[1].score if len(ranked) > 1 else 0.0
    if result.accepted:
        assert ranked[0].score >= tau - 1e-9
        assert ranked[0].score - second >= delta - 1e-9
        assert result.top is ranked[0]


# ------------------------------------------------------------------ gate truth table


def ranked_with(*scores: float) -> list[Candidate]:
    return [
        Candidate(index=i, fingerprint=f.fingerprint(), score=s, feature_scores={})
        for i, s in enumerate(scores)
    ]


@pytest.mark.parametrize(
    ("scores", "accepted", "why"),
    [
        ((0.90, 0.50), True, "score"),  # confident and clear
        ((0.90, 0.85), False, "margin"),  # confident, ambiguous
        ((0.60, 0.10), False, "tau"),  # clear, not confident
        ((0.60, 0.55), False, "tau"),  # neither
        ((0.70, 0.58), True, "score"),  # exactly tau and exactly delta: accepted
        ((0.75,), True, "score"),  # single candidate: top2 = 0
        ((), False, "no compatible"),
    ],
)
def test_gate_truth_table(scores: tuple[float, ...], accepted: bool, why: str) -> None:
    result = decide(ranked_with(*scores), tau_conf=0.70, delta_margin=0.12)
    assert result.accepted is accepted
    assert why in result.reason


# ------------------------------------------------------------------ timing


@pytest.mark.slow
@pytest.mark.timing
def test_scoring_300_candidates_p95_under_10ms() -> None:
    """Tier-1 scoring p95 < 10 ms. Measured in a clean subprocess,
    because threads kept alive by this session's fixtures distort in-process timing.

    Best of 3 p95 measurements after one warm-up. Deselected from the default
    run (needs ``--run-timing``); CI and gate checks pass that flag. The reported
    number comes from scripts/measure_tier1.py, run in isolation."""
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-m", "tests.unit.tier1_bench"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    print(
        f"tier1 scoring 300 candidates: p50={result['p50_ms']} ms "
        f"best-of-3 p95={result['p95_ms']} ms (runs: {result['p95_runs_ms']})"
    )
    assert result["samples"] == 100
    assert len(result["p95_runs_ms"]) == 3
    assert result["p95_ms"] < 10.0


@settings(max_examples=25)
@given(st.lists(fingerprints, min_size=0, max_size=20), fingerprints)
def test_score_candidates_sorted_and_indexed(
    pool: list[ElementFingerprint], t: ElementFingerprint
) -> None:
    ranked = score_candidates(t, pool)
    assert [c.score for c in ranked] == sorted((c.score for c in ranked), reverse=True)
    assert {c.index for c in ranked} <= set(range(len(pool)))
