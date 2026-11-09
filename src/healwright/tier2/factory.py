"""Build the Tier-2 picker from settings (no provider -> no Tier 2).

A provider joins the chain only if its key is set. In ``replay`` mode a
key-less provider is represented by a stub that can serve cached replies but
refuses to make calls, so the demo and CI work offline with zero keys.
"""

from __future__ import annotations

from pathlib import Path

from healwright.config import Settings
from healwright.errors import ProviderAuthError
from healwright.tier2.cache import ResponseCache
from healwright.tier2.picker import VlmPicker
from healwright.tier2.providers.base import Provider
from healwright.tier2.router import Router


class ReplayOnlyProvider:
    """Has a name and model (for cache keys) but never calls out."""

    def __init__(self, name: str, model: str) -> None:
        self.name = name
        self.model = model

    def complete(self, prompt: str, image_jpeg: bytes) -> str:
        raise ProviderAuthError(f"{self.name}: no API key configured (replay only)")


def build_providers(settings: Settings) -> list[Provider]:
    providers: list[Provider] = []
    keys = {
        "gemini": (settings.gemini_api_key, settings.gemini_model),
        "groq": (settings.groq_api_key, settings.groq_model),
        "mistral": (settings.mistral_api_key, settings.mistral_model),
    }
    for name in settings.providers:
        key, model = keys[name]
        if key is None:
            if settings.vlm_mode == "replay":
                providers.append(ReplayOnlyProvider(name, model))
            continue
        if name == "gemini":
            from healwright.tier2.providers.gemini import GeminiProvider

            providers.append(GeminiProvider(key.get_secret_value(), model))
        elif name == "groq":
            from healwright.tier2.providers.openai_compat import GroqProvider

            providers.append(GroqProvider(key.get_secret_value(), model))
        else:
            from healwright.tier2.providers.openai_compat import MistralProvider

            providers.append(MistralProvider(key.get_secret_value(), model))
    return providers


def build_picker(settings: Settings, cache_dir: Path) -> VlmPicker | None:
    providers = build_providers(settings)
    if not providers or settings.vlm_run_cap == 0:
        return None
    router = Router(
        providers,
        ResponseCache(cache_dir, settings.vlm_mode),
        settings.vlm_run_cap,
        max_retries=settings.vlm_max_retries,
        retry_after_cap=settings.vlm_retry_after_cap_s,
    )
    return VlmPicker(router)


__all__ = ["ReplayOnlyProvider", "build_picker", "build_providers"]
