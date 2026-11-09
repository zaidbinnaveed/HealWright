"""Heal engine. In-process; NEVER raises.

Pipeline for one broken step:
  2. classify: count matches of the original selector (1 = not a locator
     failure, >1 = strict-mode break reported only, 0 = locator break);
  3. guards: max heals per test, baseline present and readable, 30 s deadline;
  4. snapshot: one extract.js call (candidates kept in the page);
  5. Tier 1 + margin gate; on gate failure the injected Tier-2 picker (6.4), or
     ``needs_human`` when no picker is available;
  6. synthesise a unique locator for the chosen element;
  7. verify it in a sandbox context against the recorded contract (at most 3
     candidates; ``inconclusive`` -> ``suggested``);
  8. execute live and compare the live effect to the contract a second time.

Any ``Exception`` becomes status ``error``; the plugin then re-raises the
ORIGINAL Playwright error with a note. ``BaseException`` passes.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from playwright.sync_api import Locator, Page

from healwright.config import Settings
from healwright.errors import BaselineCorrupt
from healwright.locators import SynthesizedLocator, synthesize
from healwright.models import (
    Candidate,
    ElementFingerprint,
    HealDecision,
    HealStatus,
    StepKey,
    VerificationResult,
)
from healwright.plugin.proxy import PrefixStep
from healwright.recorder.contract import NetworkLog, observe
from healwright.recorder.extract import extract, row_as_dict
from healwright.recorder.fingerprint import fingerprint_from_row
from healwright.recorder.recorder import page_state
from healwright.store.baselines import baseline_path, load
from healwright.tier1 import decide, score_candidates
from healwright.verify.compare import compare
from healwright.verify.sandbox import STEP_TIMEOUT_MS, run_candidate, settle, stable_state

MAX_VERIFY = 3
_CANDIDATE_JS = "(i) => window.__healwright_candidates[i]"


@dataclass(frozen=True)
class Tier2Pick:
    """What a Tier-2 picker returns: an index into the candidates it was shown
    (``None`` = target absent), or an error description."""

    index: int | None
    error: str | None = None


class Tier2Picker(Protocol):
    def pick(
        self, page: Page, target: ElementFingerprint, action: str, candidates: Sequence[Candidate]
    ) -> Tier2Pick: ...


@dataclass(frozen=True)
class HealRequest:
    page: Page
    key: StepKey
    selector: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    prefix: Sequence[PrefixStep]
    baseline_root: Path
    settings: Settings
    heals_used: int = 0


@dataclass
class HealOutcome:
    decision: HealDecision
    spec: SynthesizedLocator | None = None
    result: Any = None
    acted_live: bool = False  # the healed action already ran on the real page
    timings_ms: dict[str, float] = field(default_factory=dict)
    screenshot: bytes | None = None
    som: bytes | None = None  # Set-of-Mark image shown to the VLM (report material)
    # report material (candidates.json artifact; not part of the HealEvent contract)
    candidates: list[Candidate] = field(default_factory=list)  # Tier-1 top 5
    gate: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)  # sandbox verify runs
    live_check: dict[str, Any] | None = None


class _DeadlineExceeded(Exception):
    pass


def perform(target: Locator, action: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return getattr(target, action)(*args, **kwargs)


def heal(
    req: HealRequest,
    tier2: Tier2Picker | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> HealOutcome:
    out = HealOutcome(decision=_decision("error", "not started"))
    started = clock()
    deadline = started + req.settings.heal_deadline_s
    marks = {"t": started}

    def lap(stage: str) -> None:
        now = clock()
        out.timings_ms[stage] = round((now - marks["t"]) * 1000, 2)
        marks["t"] = now
        if now > deadline:
            raise _DeadlineExceeded(stage)

    try:
        _run(req, tier2, out, lap)
    except _DeadlineExceeded as exc:
        out.decision = _decision(
            "error", f"heal deadline of {req.settings.heal_deadline_s:g} s exceeded during {exc}"
        )
    except Exception as exc:  # noqa: BLE001 - fail closed: the plugin re-raises the original error
        out.decision = _decision("error", f"internal error: {type(exc).__name__}")
    out.timings_ms["total"] = round((clock() - started) * 1000, 2)
    return out


def _decision(
    status: HealStatus,
    reason: str,
    tier: Literal[1, 2] | None = None,
    chosen: Candidate | None = None,
    spec: SynthesizedLocator | None = None,
    verification: VerificationResult | None = None,
) -> HealDecision:
    return HealDecision(
        status=status,
        tier=tier,
        chosen=chosen,
        locator=spec.code() if spec else None,
        verification=verification,
        reason=reason[:1000],
    )


def _run(
    req: HealRequest, tier2: Tier2Picker | None, out: HealOutcome, lap: Callable[[str], None]
) -> None:
    page, key, settings = req.page, req.key, req.settings
    if page.is_closed():
        out.decision = _decision("error", "page closed during the step")
        return

    # 2. classify
    matches = Page.locator(page, req.selector).count()
    lap("classify")
    if matches == 1:
        out.decision = _decision(
            "not_a_locator_failure", "element exists but did not become actionable in time"
        )
        return
    if matches > 1:
        out.decision = _decision(
            "not_a_locator_failure",
            f"selector matches {matches} elements (strict mode): reported, not healed in v1",
        )
        return

    # 3. guards
    if req.heals_used >= settings.max_heals_per_test:
        out.decision = _decision(
            "needs_human", f"already healed {req.heals_used} steps in this test (likely a redesign)"
        )
        return
    try:
        file = load(baseline_path(req.baseline_root, key.test_nodeid))
    except BaselineCorrupt as exc:
        out.decision = _decision("error", f"{BaselineCorrupt.code}: {exc}")
        return
    record = file.find(key) if file else None
    lap("baseline")
    if record is None:
        out.decision = _decision(
            "needs_human", "no baseline for this step: run once while green (record mode) first"
        )
        return
    baseline = record.baseline
    target = baseline.fingerprint
    if target.in_shadow_dom:
        out.decision = _decision("needs_human", "target was inside a shadow root (out of scope)")
        return

    # 4. snapshot
    snap = extract(page, keep=True)
    rows = snap["rows"]
    fingerprints = [fingerprint_from_row(r, snap["viewport"]) for r in rows]
    try:
        out.screenshot = page.screenshot(type="png", timeout=5_000)
    except Exception:  # noqa: BLE001 - a missing screenshot only affects the report
        out.screenshot = None
    lap("extract")

    # 5. Tier 1 + gate (Tier 2 on gate failure)
    ranked = score_candidates(target, fingerprints, limit=15)
    gate = decide(ranked, settings.tau_conf, settings.delta_margin)
    out.candidates = list(ranked[:5])
    out.gate = {
        "accepted": gate.accepted,
        "top_score": ranked[0].score if ranked else None,
        "second_score": ranked[1].score if len(ranked) > 1 else None,
        "margin": gate.margin,
        "reason": gate.reason,
        "tau": settings.tau_conf,
        "delta": settings.delta_margin,
        "tier2_floor": settings.tier2_floor,
        "compatible_candidates": len(ranked),
    }
    lap("tier1")
    tier: Literal[1, 2] = 1
    if gate.accepted:
        # the gated top-1, then (if it fails verification) runners-up that are not absurd
        to_verify = [ranked[0]] + [
            c for c in ranked[1:MAX_VERIFY] if c.score >= settings.tier2_floor
        ]
    else:
        if not ranked:
            status: HealStatus = "needs_human" if snap["has_iframes"] else "regression_suspected"
            out.decision = _decision(
                status,
                "no compatible candidate on the page"
                + (
                    " (page has iframes: the target may be inside one)"
                    if snap["has_iframes"]
                    else ""
                ),
            )
            return
        if tier2 is None or settings.vlm_run_cap == 0:
            out.decision = _decision(
                "needs_human",
                f"Tier 1 not confident ({gate.reason}); Tier 2 unavailable",
                chosen=gate.top,
            )
            return
        pick = tier2.pick(page, target, key.action, ranked)
        som = getattr(tier2, "last_image", None)
        out.som = som if isinstance(som, bytes) else None
        lap("tier2")
        tier = 2
        if pick.error:
            out.decision = _decision("needs_human", f"Tier 2 failed: {pick.error}", tier=2)
            return
        if pick.index is None:
            out.decision = _decision(
                "regression_suspected", "Tier 2: target absent from the page", tier=2
            )
            return
        chosen = ranked[pick.index]
        if chosen.score < settings.tier2_floor:
            out.decision = _decision(
                "needs_human",
                f"Tier 2 chose a candidate with Tier-1 score {chosen.score:.2f} < floor {settings.tier2_floor:.2f}",
                tier=2,
                chosen=chosen,
            )
            return
        to_verify = [chosen]

    # 6-7. synthesise + verify in a sandbox
    live_kwargs = {k: v for k, v in req.kwargs.items() if k != "timeout"}
    browser = page.context.browser
    if browser is None:
        out.decision = _decision("error", "no browser available for the sandbox")
        return
    viewport = page.viewport_size
    last: tuple[Candidate, SynthesizedLocator, VerificationResult] | None = None
    tried: list[str] = []
    for candidate in to_verify:
        element = page.evaluate_handle(_CANDIDATE_JS, candidate.index).as_element()
        if element is None:
            continue
        spec = synthesize(page, element, row_as_dict(rows[candidate.index]))
        lap("synth")
        if spec is None:
            continue
        if not settings.verify:
            # ABLATION (healwright_noverify / greedy): accept the first locatable
            # candidate, no sandbox and no live re-check
            out.spec = spec
            out.result = perform(
                spec.build(page), key.action, req.args, {**live_kwargs, "timeout": STEP_TIMEOUT_MS}
            )
            out.acted_live = True
            lap("live")
            out.decision = _decision(
                "healed",
                f"tier {tier}: {spec.strategy} locator; NOT verified (ablation: verify off)",
                tier=tier,
                chosen=candidate,
                spec=spec,
            )
            return

        def act(p: Page, s: SynthesizedLocator = spec) -> Any:
            return perform(s.build(p), key.action, req.args, live_kwargs)

        size = (
            {"width": int(viewport["width"]), "height": int(viewport["height"])}
            if viewport
            else None
        )
        run = run_candidate(browser, size, req.prefix, act)
        result = compare(baseline.contract, run.observed)
        lap("verify")
        label = candidate.fingerprint.accessible_name or candidate.fingerprint.tag
        tried.append(f"{label!r} ({result.outcome}: {'; '.join(result.mismatches) or 'ok'})")
        out.attempts.append(
            {
                "index": candidate.index,
                "label": label,
                "strategy": spec.strategy,
                "locator": spec.code(),
                "outcome": result.outcome,
                "mismatches": list(result.mismatches),
                "observed": (
                    run.observed.model_dump(mode="json") if run.observed is not None else None
                ),
            }
        )
        if result.outcome == "pass":
            last = (candidate, spec, result)
            break
        if result.outcome == "inconclusive":
            out.spec = spec
            out.decision = _decision(
                "suggested",
                "could not verify ("
                + (run.reason if run.observed is None else "; ".join(result.mismatches))
                + "): diff saved, test stays red",
                tier=tier,
                chosen=candidate,
                spec=spec,
                verification=result,
            )
            return
        last = (candidate, spec, result)
    if last is None or last[2].outcome != "pass":
        out.decision = _decision(
            "regression_suspected",
            "no candidate reproduced the recorded effect"
            + (": " + " | ".join(tried) if tried else ": no candidate could be located uniquely"),
            tier=tier,
            chosen=last[0] if last else None,
            spec=last[1] if last else None,
            verification=last[2] if last else None,
        )
        return
    candidate, spec, sandbox_result = last

    # 8. execute live and re-check the effect
    net = NetworkLog(page)
    net.attach()
    try:
        before = page_state(page)
        mark = net.mark()
        t0 = time.perf_counter()
        out.result = perform(
            spec.build(page), key.action, req.args, {**live_kwargs, "timeout": STEP_TIMEOUT_MS}
        )
        out.acted_live = True
        settle(page, net, t0, mark)
        observed = observe(before, stable_state(page), net.since(mark, started=t0))
    finally:
        net.detach()
    live = compare(baseline.contract, observed)
    out.live_check = {
        "outcome": live.outcome,
        "mismatches": list(live.mismatches),
        "observed": observed.model_dump(mode="json"),
    }
    lap("live")
    out.spec = spec
    if live.outcome != "pass":
        out.decision = _decision(
            "error",
            "live re-check failed after a passing sandbox: " + "; ".join(live.mismatches),
            tier=tier,
            chosen=candidate,
            spec=spec,
            verification=live,
        )
        return
    out.decision = _decision(
        "healed",
        f"tier {tier}: {spec.strategy} locator; sandbox and live effects match the recorded contract",
        tier=tier,
        chosen=candidate,
        spec=spec,
        verification=sandbox_result,
    )


__all__ = [
    "MAX_VERIFY",
    "HealOutcome",
    "HealRequest",
    "Tier2Pick",
    "Tier2Picker",
    "heal",
    "perform",
]
