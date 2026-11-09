"""Deterministic locator synthesis: test id, role + name, label, scoped role."""

from healwright.locators.synth import (
    LocatorCall,
    Strategy,
    SynthesizedLocator,
    css_escape_id,
    synthesize,
)

__all__ = ["LocatorCall", "Strategy", "SynthesizedLocator", "css_escape_id", "synthesize"]
