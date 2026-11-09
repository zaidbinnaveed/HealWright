"""Deterministic locator synthesis.

Strategies, first match wins:
  1. ``get_by_test_id(tid)`` when the element has a data-testid
  2. ``get_by_role(role, name=..., exact=True)``
  3. ``get_by_label(label, exact=True)`` for form fields
  4. a role locator scoped inside the nearest uniquely identifiable ancestor
     (test id, id, or a unique landmark); if still ambiguous, ``.nth(i)`` and
     the result is marked ``fragile``.

Every strategy must resolve to EXACTLY ONE element AND that element must be the
chosen one (identity checked in the page with ``===``). The VLM never writes a
locator: it only picks a candidate, and this module builds the locator.

The result is a structure of calls, not text: the patcher turns it into LibCST
nodes built from ``repr()`` of each string, so page text can never inject code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from playwright.sync_api import ElementHandle, Locator, Page

Strategy = Literal["test_id", "role", "label", "scoped_role"]
FORM_ROLES = frozenset(
    {
        "textbox",
        "searchbox",
        "combobox",
        "listbox",
        "checkbox",
        "radio",
        "switch",
        "spinbutton",
        "slider",
    }
)
LANDMARK_ROLES = frozenset(
    {
        "form",
        "navigation",
        "main",
        "banner",
        "contentinfo",
        "complementary",
        "region",
        "dialog",
        "article",
    }
)

_ANCESTORS_JS = """
(el) => {
  const out = [];
  let node = el.parentElement;
  while (node && node !== document.documentElement && out.length < 12) {
    const explicit = (node.getAttribute("role") || "").trim().split(/\\s+/)[0] || null;
    const tag = node.tagName.toLowerCase();
    const implicit = {nav: "navigation", main: "main", form: "form", aside: "complementary",
                      article: "article", dialog: "dialog", header: "banner", footer: "contentinfo"}[tag] || null;
    out.push({ tag, id: node.id || null, testid: node.getAttribute("data-testid"),
               role: explicit || implicit });
    node = node.parentElement;
  }
  return out;
}
"""
_SAME_JS = "(el, target) => el === target"
_CSS_SAFE = re.compile(r"[A-Za-z0-9_-]")


def css_escape_id(value: str) -> str:
    """CSS identifier escape for an id selector (no reliance on page text being nice)."""
    out = []
    for i, ch in enumerate(value):
        if _CSS_SAFE.match(ch) and not (i == 0 and ch.isdigit()):
            out.append(ch)
        else:
            out.append(f"\\{ord(ch):x} ")
    return "#" + "".join(out)


@dataclass(frozen=True)
class LocatorCall:
    method: str
    args: tuple[Any, ...] = ()
    kwargs: tuple[tuple[str, Any], ...] = ()

    def code(self) -> str:
        parts = [repr(a) for a in self.args] + [f"{k}={v!r}" for k, v in self.kwargs]
        return f"{self.method}({', '.join(parts)})"


@dataclass(frozen=True)
class SynthesizedLocator:
    strategy: Strategy
    calls: tuple[LocatorCall, ...]
    fragile: bool = False

    def code(self, receiver: str = "page") -> str:
        return receiver + "".join(f".{c.code()}" for c in self.calls)

    def build(self, page: Page) -> Locator:
        obj: Any = page
        for call in self.calls:
            obj = getattr(obj, call.method)(*call.args, **dict(call.kwargs))
        if not isinstance(obj, Locator):
            raise TypeError("locator calls did not produce a Locator")
        return obj


def _call(method: str, *args: Any, **kwargs: Any) -> LocatorCall:
    return LocatorCall(method, tuple(args), tuple(kwargs.items()))


def _role_call(role: str, name: str) -> LocatorCall:
    return _call("get_by_role", role, name=name, exact=True) if name else _call("get_by_role", role)


def _resolves_to(page: Page, spec: SynthesizedLocator, target: ElementHandle) -> bool:
    """Exactly one match, and it is the chosen element."""
    try:
        loc = spec.build(page)
        if loc.count() != 1:
            return False
        same: bool = loc.evaluate(_SAME_JS, target)
        return same
    except Exception:  # noqa: BLE001 - an invalid strategy is simply skipped
        return False


def synthesize(page: Page, target: ElementHandle, raw: dict[str, Any]) -> SynthesizedLocator | None:
    """Build a locator for ``target``. ``raw`` is the element's extract.js row as a
    dict (NOT normalised: exact-match locators need the real casing).

    Returns ``None`` if no strategy uniquely identifies the element; the engine
    then fails closed.
    """
    attrs: dict[str, str] = raw.get("attrs") or {}
    role: str | None = raw.get("role")
    name: str = raw.get("name") or ""

    candidates: list[SynthesizedLocator] = []
    testid = attrs.get("data-testid")
    if testid:
        candidates.append(SynthesizedLocator("test_id", (_call("get_by_test_id", testid),)))
    if role and name:
        candidates.append(SynthesizedLocator("role", (_role_call(role, name),)))
    if name and (role in FORM_ROLES or raw.get("tag") in ("input", "select", "textarea")):
        candidates.append(SynthesizedLocator("label", (_call("get_by_label", name, exact=True),)))
    for spec in candidates:
        if _resolves_to(page, spec, target):
            return spec
    if role:
        return _scoped(page, target, role, name)
    return None


def _scope_calls(page: Page, target: ElementHandle) -> list[tuple[LocatorCall, ...]]:
    """Nearest-first scopes that match exactly one element in the page."""
    scopes: list[tuple[LocatorCall, ...]] = []
    try:
        ancestors: list[dict[str, Any]] = target.evaluate(_ANCESTORS_JS)
    except Exception:  # noqa: BLE001 - no scopes; caller falls back to nth()
        return scopes
    for anc in ancestors:
        options: list[LocatorCall] = []
        if anc.get("testid"):
            options.append(_call("get_by_test_id", anc["testid"]))
        if anc.get("id"):
            options.append(_call("locator", css_escape_id(anc["id"])))
        if anc.get("role") in LANDMARK_ROLES:
            options.append(_call("get_by_role", anc["role"]))
        for opt in options:
            try:
                if SynthesizedLocator("scoped_role", (opt,)).build(page).count() == 1:
                    scopes.append((opt,))
                    break
            except Exception:  # noqa: BLE001 - invalid scope candidate: try the next
                continue
    return scopes


def _scoped(page: Page, target: ElementHandle, role: str, name: str) -> SynthesizedLocator | None:
    inner = _role_call(role, name)
    for scope in _scope_calls(page, target):
        spec = SynthesizedLocator("scoped_role", (*scope, inner))
        if _resolves_to(page, spec, target):
            return spec
        # still ambiguous inside the scope: pick by position (fragile)
        found = _nth_within(page, SynthesizedLocator("scoped_role", (*scope, inner)), target)
        if found is not None:
            return found
    return _nth_within(page, SynthesizedLocator("scoped_role", (inner,)), target)


def _nth_within(
    page: Page, base: SynthesizedLocator, target: ElementHandle
) -> SynthesizedLocator | None:
    try:
        matches = base.build(page).element_handles()
    except Exception:  # noqa: BLE001
        return None
    for i, handle in enumerate(matches):
        try:
            if handle.evaluate(_SAME_JS, target):
                spec = SynthesizedLocator(
                    "scoped_role", (*base.calls, _call("nth", i)), fragile=True
                )
                return spec if _resolves_to(page, spec, target) else None
        except Exception:  # noqa: BLE001
            continue
    return None


__all__ = [
    "FORM_ROLES",
    "LocatorCall",
    "Strategy",
    "SynthesizedLocator",
    "css_escape_id",
    "synthesize",
]
