"""Builders for valid contract objects, shared by unit and integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from healwright.models import (
    ApiCall,
    Baseline,
    BBox,
    Candidate,
    ElementFingerprint,
    HealDecision,
    HealEvent,
    PostConditionSignature,
    StepKey,
    Tier2Reply,
    VerificationResult,
)

ULID_A = "01JC8Z5V7Q2W3E4R5T6Y7V8J9P"
ULID_B = "01JC8Z5V7Q2W3E4R5T6Y7V8K9P"


def bbox(**kw: Any) -> BBox:
    return BBox(**({"x": 10.0, "y": 20.0, "w": 120.0, "h": 32.0} | kw))


def fingerprint(**kw: Any) -> ElementFingerprint:
    base: dict[str, Any] = {
        "role": "button",
        "accessible_name": "add to cart",
        "tag": "button",
        "text": "add to cart",
        "attributes": {"id": "add-to-cart", "data-testid": "add-to-cart", "type": "button"},
        "class_tokens": ["btn", "btn-primary"],
        "ancestor_path": ["form", "div", "main[main]", "body", "html"],
        "neighbor_texts": ["quantity", "$19.99"],
        "bbox": bbox(),
        "viewport": (1280, 800),
        "in_shadow_dom": False,
    }
    return ElementFingerprint(**(base | kw))


def api_call(**kw: Any) -> ApiCall:
    return ApiCall(**({"method": "POST", "path_template": "/api/cart", "status_class": "2xx"} | kw))


def contract(**kw: Any) -> PostConditionSignature:
    base: dict[str, Any] = {
        "url_before": "/product/{id}",
        "url_after": "/product/{id}",
        "api_calls": frozenset({api_call(), api_call(method="GET", path_template="/api/cart")}),
        "modal_delta": 1,
        "dom_delta_sign": 1,
        "strength": "strong",
        "observations": 3,
    }
    return PostConditionSignature(**(base | kw))


def step_key(**kw: Any) -> StepKey:
    base = {
        "test_nodeid": "examples/test_cart.py::test_add_to_cart",
        "action": "click",
        "selector": "#add-to-cart",
        "occurrence": 0,
    }
    return StepKey(**(base | kw))


def baseline(**kw: Any) -> Baseline:
    base: dict[str, Any] = {
        "key": step_key(),
        "fingerprint": fingerprint(),
        "contract": contract(),
        "source_line": 12,
        "recorded_at": datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
        "healwright_version": "0.1.0",
    }
    return Baseline(**(base | kw))


def candidate(**kw: Any) -> Candidate:
    base: dict[str, Any] = {
        "index": 3,
        "fingerprint": fingerprint(),
        "score": 0.91,
        "feature_scores": {"role": 1.0, "text": 0.95, "geometry": 0.8},
    }
    return Candidate(**(base | kw))


def verification(**kw: Any) -> VerificationResult:
    base: dict[str, Any] = {
        "outcome": "pass",
        "expected": contract(),
        "observed": contract(),
        "mismatches": [],
    }
    return VerificationResult(**(base | kw))


def decision(**kw: Any) -> HealDecision:
    base: dict[str, Any] = {
        "status": "healed",
        "tier": 1,
        "chosen": candidate(),
        "locator": 'page.get_by_role("button", name="Add to cart", exact=True)',
        "verification": verification(),
        "reason": "tier 1 margin gate passed; sandbox contract matched",
    }
    return HealDecision(**(base | kw))


def heal_event(**kw: Any) -> HealEvent:
    base: dict[str, Any] = {
        "id": ULID_A,
        "run_id": ULID_B,
        "key": step_key(),
        "decision": decision(),
        "timings_ms": {"extract": 41.5, "tier1": 3.2, "verify": 820.0, "total": 900.1},
        "artifacts": {"before": "before.png", "patch": "patch.diff"},
        "diff": "--- a/x.py\n+++ b/x.py\n",
        "source_sha256": "a" * 64,
    }
    return HealEvent(**(base | kw))


def tier2_reply(**kw: Any) -> Tier2Reply:
    return Tier2Reply(**({"mark_id": 4, "confidence": 0.82, "reason": "same label"} | kw))
