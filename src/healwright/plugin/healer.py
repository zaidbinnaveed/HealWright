"""Plugin glue between a failing wrapped action and the heal engine.

- Runs actions with the probe timeout (3 s, or the user's timeout if lower).
- On Playwright's ``TimeoutError`` (only), calls ``engine.heal``.
- Healed: the healed locator joins the replay prefix, the test is marked as
  healed (its baselines are never updated) and the action's result returns.
- Not healed: if the user's own timeout is longer than the probe, the ORIGINAL
  action is retried with the user's own arguments (a slow page must not turn
  a green test red). Otherwise, or if that retry also fails, the
  Playwright error is re-raised with a HealWright note.
- Every attempt writes one ``HealEvent`` line; write failures are only logged.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from healwright.config import Settings
from healwright.engine import HealOutcome, HealRequest, Tier2Picker, heal
from healwright.errors import PatchError
from healwright.models import HealEvent, StepKey
from healwright.patcher import git_apply_check, make_patch, suggestion
from healwright.plugin.proxy import ActionStep, ActionTracker, RunStats, Via
from healwright.store.runs import RunStore, new_id

log = logging.getLogger("healwright.plugin")


def _note(status: str, reason: str, event_id: str) -> str:
    return f"HealWright: {status.replace('_', ' ')}: {reason} (event {event_id})"


class Healer:
    def __init__(
        self,
        settings: Settings,
        baseline_root: Path,
        runs: RunStore,
        stats: RunStats,
        tier2: Tier2Picker | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.settings = settings
        self.baseline_root = baseline_root
        self.runs = runs
        self.stats = stats
        self.tier2 = tier2

    # ------------------------------------------------------------------ StepHealer
    def probe_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        user = kwargs.get("timeout")
        if user is not None and float(user) <= self.settings.probe_timeout_ms:
            return kwargs
        return {**kwargs, "timeout": self.settings.probe_timeout_ms}

    def _user_waits_longer(self, kwargs: dict[str, Any]) -> bool:
        user = kwargs.get("timeout")
        return user is None or float(user) > self.settings.probe_timeout_ms

    def handle(
        self,
        tracker: ActionTracker,
        page: Page,
        key: StepKey,
        via: Via,
        selector: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        error: PlaywrightTimeoutError,
        retry: Callable[[], Any],
    ) -> Any:
        if page.is_closed():
            raise error
        call_line = tracker.call_site_line()  # the test's frames are on the stack right now
        outcome = heal(
            HealRequest(
                page=page,
                key=key,
                selector=selector,
                args=args,
                kwargs=kwargs,
                prefix=list(tracker.prefix),
                baseline_root=self.baseline_root,
                settings=self.settings,
                heals_used=tracker.heals_used,
            ),
            tier2=self.tier2,
        )
        event_id = new_id()
        self._record(event_id, key, outcome, via, selector, tracker.test_file, call_line)
        status = outcome.decision.status
        self.stats.heal_status[status] += 1
        plain = {k: v for k, v in kwargs.items() if k != "timeout"}

        if status == "healed":
            tracker.healed = True
            tracker.heals_used += 1
            tracker.prefix.append(ActionStep(key, via, selector, args, plain, locator=outcome.spec))
            return outcome.result

        note = _note(status, outcome.decision.reason, event_id)
        if not outcome.acted_live and self._user_waits_longer(kwargs) and not page.is_closed():
            try:
                result = retry()  # the user's own action with the user's own timeout
            except PlaywrightTimeoutError as native:
                native.add_note(note)
                raise native from None
            except PlaywrightError:
                # e.g. the browser closed during the heal: fail closed with the ORIGINAL error
                error.add_note(note)
                raise error from None
            tracker.prefix.append(ActionStep(key, via, selector, args, plain))
            log.info("healwright: %s; original selector succeeded on retry", note)
            return result
        error.add_note(note)
        raise error

    # ------------------------------------------------------------------ events
    def _patch(
        self,
        event_id: str,
        key: StepKey,
        outcome: HealOutcome,
        via: Via,
        selector: str,
        test_file: str | None,
        line: int | None,
        artifacts: dict[str, str],
    ) -> tuple[str | None, str | None]:
        """Diff for healed/suggested steps (6.3); suggestion text when unpatchable."""
        spec = outcome.spec
        if spec is None or outcome.decision.status not in ("healed", "suggested"):
            return None, None
        if not (self.repo_root and test_file and line):
            missing = [
                n
                for n, v in (
                    ("repo root", self.repo_root),
                    ("test file", test_file),
                    ("call-site line", line),
                )
                if not v
            ]
            text = f"replace the selector {selector!r} with {spec.code('page')}\nreason: unknown {', '.join(missing)}\n"
            name = self.runs.save_artifact(event_id, "suggestion.txt", text.encode("utf-8"))
            if name:
                artifacts["suggestion"] = name
            return None, None
        path = Path(test_file)
        try:
            result = make_patch(self.repo_root, path, line, key.action, selector, via, spec)
            ok, err = git_apply_check(self.repo_root, result.diff)
            if not ok:
                raise PatchError(f"PATCH_INVALID: git apply --check failed: {err[:300]}")
        except (PatchError, OSError, UnicodeDecodeError) as exc:
            text = suggestion(path, line, selector, spec) + f"\nreason: {exc}\n"
            name = self.runs.save_artifact(event_id, "suggestion.txt", text.encode("utf-8"))
            if name:
                artifacts["suggestion"] = name
            return None, None
        name = self.runs.save_artifact(event_id, "patch.diff", result.diff.encode("utf-8"))
        if name:
            artifacts["patch"] = name
        return result.diff, result.source_sha256

    def _record(
        self,
        event_id: str,
        key: StepKey,
        outcome: HealOutcome,
        via: Via,
        selector: str,
        test_file: str | None,
        line: int | None,
    ) -> None:
        try:
            artifacts: dict[str, str] = {}
            if outcome.screenshot:
                name = self.runs.save_artifact(event_id, "before.png", outcome.screenshot)
                if name:
                    artifacts["before"] = name
            if outcome.som:
                name = self.runs.save_artifact(event_id, "som.jpg", outcome.som)
                if name:
                    artifacts["som"] = name
            if outcome.candidates or outcome.gate:
                report = {
                    "schema_version": 1,
                    "gate": outcome.gate,
                    "candidates": [c.model_dump(mode="json") for c in outcome.candidates],
                    "attempts": outcome.attempts,
                    "live_check": outcome.live_check,
                }
                name = self.runs.save_artifact(
                    event_id, "candidates.json", json.dumps(report).encode("utf-8")
                )
                if name:
                    artifacts["candidates"] = name
            diff, sha = self._patch(
                event_id, key, outcome, via, selector, test_file, line, artifacts
            )
            event = HealEvent(
                id=event_id,
                run_id=self.runs.run_id,
                key=key,
                decision=outcome.decision,
                timings_ms=outcome.timings_ms,
                artifacts=artifacts,
                diff=diff,
                source_sha256=sha,
            )
            if self.runs.append_event(event):
                self.stats.run_dir = str(self.runs.dir)
        except Exception:
            log.warning("healwright: could not record heal event %s", event_id, exc_info=True)


__all__ = ["Healer"]
