"""Shared data contracts, frozen at gate G0.

Every model forbids unknown fields and carries explicit size caps so that data
coming from a web page, a baseline file or a VLM reply cannot grow without
bound.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
)

# --------------------------------------------------------------------------- caps
MAX_TEXT_LEN = 200  # visible text, accessible name, neighbour texts
MAX_ATTRIBUTES = 30
MAX_CANDIDATES = 400  # extraction snapshot cap; Candidate.index < MAX_CANDIDATES
MAX_ANCESTORS = 6
MAX_NEIGHBORS = 5
MAX_CLASS_TOKENS = 50
MAX_ATTR_VALUE_LEN = 500
MAX_SELECTOR_LEN = 2000
MAX_NODEID_LEN = 1000
MAX_URL_LEN = 2048
MAX_REASON_LEN = 1000
MAX_TIER2_REASON_LEN = 300
MAX_MISMATCHES = 50
MAX_FEATURES = 20
MAX_DIFF_LEN = 200_000

ULID_PATTERN = r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

Text = Annotated[str, StringConstraints(max_length=MAX_TEXT_LEN)]
Url = Annotated[str, StringConstraints(max_length=MAX_URL_LEN)]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]
Ulid = Annotated[str, StringConstraints(pattern=ULID_PATTERN)]
Sha256 = Annotated[str, StringConstraints(pattern=SHA256_PATTERN)]
ShortKey = Annotated[str, StringConstraints(min_length=1, max_length=100)]

Sign = Literal[-1, 0, 1]


class BBox(BaseModel):
    """Bounding box in CSS px, viewport-relative at action time."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    w: Annotated[float, Field(ge=0.0)]
    h: Annotated[float, Field(ge=0.0)]


class ElementFingerprint(BaseModel):
    """Features of one interactive element, as extracted by extract.js.

    Text fields hold already-normalised values (NFKC, casefold, collapsed
    whitespace, zero-width characters stripped). Over-length input
    is rejected, not truncated: the extractor is responsible for truncation.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    role: Text | None  # computed ARIA role
    accessible_name: Text
    tag: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    text: Text  # visible innerText
    attributes: Annotated[
        dict[ShortKey, Annotated[str, StringConstraints(max_length=MAX_ATTR_VALUE_LEN)]],
        Field(max_length=MAX_ATTRIBUTES),
    ]  # id, name, type, placeholder, href path, data-testid, aria-*
    class_tokens: Annotated[list[ShortKey], Field(max_length=MAX_CLASS_TOKENS)]
    ancestor_path: Annotated[list[ShortKey], Field(max_length=MAX_ANCESTORS)]  # "tag[role]"
    neighbor_texts: Annotated[list[Text], Field(max_length=MAX_NEIGHBORS)]
    bbox: BBox
    viewport: tuple[Annotated[int, Field(gt=0)], Annotated[int, Field(gt=0)]]
    in_shadow_dom: bool


class ApiCall(BaseModel):
    """One same-origin XHR/fetch call, with its path templated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,10}$")]
    path_template: Url  # /api/orders/{id}
    status_class: Literal["2xx", "3xx", "4xx", "5xx", "failed", "unknown"]


def _api_call_sort_key(call: ApiCall) -> tuple[str, str, str]:
    return (call.path_template, call.method, call.status_class)


class PostConditionSignature(BaseModel):
    """Observable effect of one action (the contract, Phi)."""

    model_config = ConfigDict(extra="forbid")

    url_before: Url  # route template; query and fragment dropped
    url_after: Url
    api_calls: Annotated[frozenset[ApiCall], Field(max_length=100)]
    modal_delta: Sign
    dom_delta_sign: Sign
    strength: Literal["strong", "weak", "none"]  # strong: URL or API change; weak: modal/DOM only
    observations: Annotated[int, Field(ge=0)]  # green runs merged into this signature

    @field_serializer("api_calls")
    def _serialize_api_calls(self, calls: frozenset[ApiCall]) -> list[ApiCall]:
        # Deterministic order so baseline files only change when content does.
        return sorted(calls, key=_api_call_sort_key)


class StepKey(BaseModel):
    """Identity of one wrapped action inside one test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    test_nodeid: Annotated[str, StringConstraints(min_length=1, max_length=MAX_NODEID_LEN)]
    action: Literal["click", "fill", "check", "uncheck", "press", "select_option", "hover"]
    selector: Annotated[str, StringConstraints(min_length=1, max_length=MAX_SELECTOR_LEN)]
    occurrence: Annotated[int, Field(ge=0)]  # nth run of (action, selector) in this test


class Baseline(BaseModel):
    """Recorded fingerprint and contract for one step."""

    model_config = ConfigDict(extra="forbid")

    key: StepKey
    fingerprint: ElementFingerprint
    contract: PostConditionSignature
    source_line: Annotated[int, Field(ge=1)]
    recorded_at: AwareDatetime
    healwright_version: Annotated[str, StringConstraints(min_length=1, max_length=50)]


class Candidate(BaseModel):
    """One scored element from the extraction snapshot."""

    model_config = ConfigDict(extra="forbid")

    index: Annotated[int, Field(ge=0, lt=MAX_CANDIDATES)]  # position in the snapshot
    fingerprint: ElementFingerprint
    score: Unit
    feature_scores: Annotated[dict[ShortKey, Unit], Field(max_length=MAX_FEATURES)]


class VerificationResult(BaseModel):
    """Outcome of replaying a candidate action in the sandbox."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["pass", "fail", "inconclusive", "skipped"]
    expected: PostConditionSignature
    observed: PostConditionSignature | None
    mismatches: Annotated[
        list[Annotated[str, StringConstraints(max_length=MAX_REASON_LEN)]],
        Field(max_length=MAX_MISMATCHES),
    ]


HealStatus = Literal[
    "healed",
    "suggested",
    "needs_human",
    "regression_suspected",
    "not_a_locator_failure",
    "error",
]


class HealDecision(BaseModel):
    """What the engine decided for one broken step."""

    model_config = ConfigDict(extra="forbid")

    status: HealStatus
    tier: Literal[1, 2] | None
    chosen: Candidate | None
    locator: Annotated[str, StringConstraints(max_length=MAX_SELECTOR_LEN)] | None
    verification: VerificationResult | None
    reason: Annotated[str, StringConstraints(max_length=MAX_REASON_LEN)]


class HealEvent(BaseModel):
    """One line of .healwright/runs/<run_id>/events.jsonl.

    Artifact paths are relative to the event's artifact folder and are made of
    generated names only, never page content.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: Ulid
    run_id: Ulid
    key: StepKey
    decision: HealDecision
    timings_ms: Annotated[
        dict[ShortKey, Annotated[float, Field(ge=0.0)]], Field(max_length=MAX_FEATURES)
    ]  # per stage: extract, tier1, tier2, synth, verify, live, patch, total
    artifacts: Annotated[
        dict[
            ShortKey,
            Annotated[
                str,
                StringConstraints(max_length=255, pattern=r"^[A-Za-z0-9_.-]+$"),
            ],
        ],
        Field(max_length=MAX_FEATURES),
    ]  # e.g. {"before": "before.png", "som": "som.png", "patch": "patch.diff"}
    diff: Annotated[str, StringConstraints(max_length=MAX_DIFF_LEN)] | None
    source_sha256: Sha256 | None
    triage_status: Literal["pending", "applied", "rejected"] = "pending"


class Tier2Reply(BaseModel):
    """The only thing a VLM may return: a mark ID, never code."""

    model_config = ConfigDict(extra="forbid")

    mark_id: Annotated[int, Field(ge=0)] | None  # None = target absent
    confidence: Unit
    reason: Annotated[str, StringConstraints(max_length=MAX_TIER2_REASON_LEN)]


__all__ = [
    "MAX_ATTRIBUTES",
    "MAX_CANDIDATES",
    "MAX_TEXT_LEN",
    "ApiCall",
    "BBox",
    "Baseline",
    "Candidate",
    "ElementFingerprint",
    "HealDecision",
    "HealEvent",
    "HealStatus",
    "PostConditionSignature",
    "StepKey",
    "Tier2Reply",
    "VerificationResult",
]
