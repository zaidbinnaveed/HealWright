"""Contract tests for healwright.models."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

import pytest
from pydantic import BaseModel, ValidationError

from healwright import models
from tests import factories as f

pytestmark = pytest.mark.unit

BUILDERS: dict[str, Callable[..., BaseModel]] = {
    "BBox": f.bbox,
    "ElementFingerprint": f.fingerprint,
    "ApiCall": f.api_call,
    "PostConditionSignature": f.contract,
    "StepKey": f.step_key,
    "Baseline": f.baseline,
    "Candidate": f.candidate,
    "VerificationResult": f.verification,
    "HealDecision": f.decision,
    "HealEvent": f.heal_event,
    "Tier2Reply": f.tier2_reply,
}


def test_every_public_model_has_a_builder() -> None:
    public = {
        name
        for name, obj in vars(models).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == models.__name__
    }
    assert public == set(BUILDERS)


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_every_model_forbids_extra_fields(name: str) -> None:
    cls = type(BUILDERS[name]())
    assert cls.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_json_round_trip(name: str) -> None:
    obj = BUILDERS[name]()
    text = obj.model_dump_json()
    again = type(obj).model_validate_json(text)
    assert again == obj
    assert again.model_dump_json() == text


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_extra_field_rejected(name: str) -> None:
    obj = BUILDERS[name]()
    data = json.loads(obj.model_dump_json())
    data["unexpected"] = 1
    with pytest.raises(ValidationError, match="unexpected"):
        type(obj).model_validate(data)


@pytest.mark.parametrize("field", ["accessible_name", "text"])
def test_fingerprint_text_over_200_rejected(field: str) -> None:
    f.fingerprint(**{field: "x" * 200})
    with pytest.raises(ValidationError):
        f.fingerprint(**{field: "x" * 201})


def test_fingerprint_neighbor_text_over_200_rejected() -> None:
    with pytest.raises(ValidationError):
        f.fingerprint(neighbor_texts=["x" * 201])


def test_fingerprint_attribute_cap_is_30() -> None:
    f.fingerprint(attributes={f"a{i}": "v" for i in range(30)})
    with pytest.raises(ValidationError):
        f.fingerprint(attributes={f"a{i}": "v" for i in range(31)})


@pytest.mark.parametrize(
    ("field", "limit"), [("ancestor_path", 6), ("neighbor_texts", 5), ("class_tokens", 50)]
)
def test_fingerprint_list_caps(field: str, limit: int) -> None:
    f.fingerprint(**{field: ["t"] * limit})
    with pytest.raises(ValidationError):
        f.fingerprint(**{field: ["t"] * (limit + 1)})


def test_candidate_index_capped_at_400() -> None:
    f.candidate(index=399)
    with pytest.raises(ValidationError):
        f.candidate(index=400)


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_candidate_score_outside_unit_interval_rejected(score: float) -> None:
    with pytest.raises(ValidationError):
        f.candidate(score=score)


def test_tier2_reply_bounds() -> None:
    f.tier2_reply(mark_id=None, reason="x" * 300)
    with pytest.raises(ValidationError):
        f.tier2_reply(reason="x" * 301)
    with pytest.raises(ValidationError):
        f.tier2_reply(confidence=1.5)
    with pytest.raises(ValidationError):
        f.tier2_reply(mark_id=-1)


def test_tier2_reply_rejects_code_like_extra_output() -> None:
    with pytest.raises(ValidationError):
        models.Tier2Reply.model_validate(
            {"mark_id": 1, "confidence": 0.5, "reason": "r", "locator": "page.click('#x')"}
        )


def test_fingerprint_unknown_schema_version_rejected() -> None:
    data = json.loads(f.fingerprint().model_dump_json())
    data["schema_version"] = 2
    with pytest.raises(ValidationError):
        models.ElementFingerprint.model_validate(data)


def test_api_calls_serialise_in_stable_order() -> None:
    calls = [
        f.api_call(method="DELETE", path_template="/api/orders/{id}"),
        f.api_call(),
        f.api_call(method="GET", path_template="/api/cart"),
    ]
    a = f.contract(api_calls=frozenset(calls)).model_dump_json()
    b = f.contract(api_calls=frozenset(reversed(calls))).model_dump_json()
    assert a == b
    paths = [c["path_template"] for c in json.loads(a)["api_calls"]]
    assert paths == sorted(paths)


def test_api_call_and_step_key_are_hashable_and_frozen() -> None:
    assert len({f.api_call(), f.api_call()}) == 1
    assert len({f.step_key(), f.step_key(occurrence=1)}) == 2
    key = f.step_key()
    with pytest.raises(ValidationError):
        key.occurrence = 5


@pytest.mark.parametrize("method", ["post", "", "VERYLONGMETHOD"])
def test_api_call_method_must_be_upper_case_verb(method: str) -> None:
    with pytest.raises(ValidationError):
        f.api_call(method=method)


def test_step_key_action_must_be_allowlisted() -> None:
    with pytest.raises(ValidationError):
        f.step_key(action="goto")


def test_baseline_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        f.baseline(recorded_at=datetime(2026, 11, 6, 12, 0))


@pytest.mark.parametrize(
    ("field", "value"),
    [("id", "not-a-ulid"), ("source_sha256", "A" * 64), ("source_sha256", "a" * 63)],
)
def test_heal_event_identifier_formats(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        f.heal_event(**{field: value})


def test_heal_event_accepts_generated_ulids() -> None:
    from ulid import ULID

    event = f.heal_event(id=str(ULID()), run_id=str(ULID()))
    assert len(event.id) == 26


@pytest.mark.parametrize("name", ["../../etc/passwd", "a/b.png", "c:\\x.png", "with space.png"])
def test_heal_event_artifact_names_cannot_traverse(name: str) -> None:
    with pytest.raises(ValidationError):
        f.heal_event(artifacts={"before": name})


def test_heal_event_defaults() -> None:
    event = f.heal_event()
    assert event.schema_version == 1
    assert event.triage_status == "pending"


@pytest.mark.parametrize(
    "status",
    [
        "healed",
        "suggested",
        "needs_human",
        "regression_suspected",
        "not_a_locator_failure",
        "error",
    ],
)
def test_heal_decision_statuses(status: str) -> None:
    assert f.decision(status=status).status == status


def test_heal_decision_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        f.decision(status="probably_fine")
