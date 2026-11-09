"""LIVE provider smoke tests (marker `live`): real calls, real keys from .env. Never in PR CI.

Run on purpose only:  uv run pytest -m live tests/live -q
Each test makes at most one call per provider (the fallback test: one failing Groq call
with a bogus model + one Mistral call). The image is a real Set-of-Mark screenshot of the
dev-02 scenario (synthetic Chaos Store page), built with the production annotate().
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from healwright.config import Settings, load_settings
from healwright.errors import ProviderAuthError, ProviderError
from healwright.models import ElementFingerprint
from healwright.tier2.cache import ResponseCache
from healwright.tier2.prompt import MarkRow, build_prompt, parse_reply
from healwright.tier2.providers.openai_compat import (
    GroqProvider,
    MistralProvider,
    OpenAICompatProvider,
)
from healwright.tier2.router import Router

pytestmark = pytest.mark.live

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live"
MODELS_URL = {
    "groq": "https://api.groq.com/openai/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
}


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


@pytest.fixture(scope="module")
def case() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "dev-02-case.json").read_text(encoding="utf-8"))
    rows = [
        MarkRow(m["id"], m["role"], m["name"], m["text"], m["offscreen"]) for m in data["marks"]
    ]
    data["prompt"] = build_prompt(
        ElementFingerprint.model_validate(data["target"]), data["action"], rows
    )
    data["image"] = (FIXTURES / "som-dev-02.jpg").read_bytes()
    data["ids"] = {m["id"] for m in data["marks"]}
    return data


def _key(settings: Settings, name: str) -> str:
    secret = getattr(settings, f"{name}_api_key")
    if secret is None:
        pytest.skip(f"{name.upper()}_API_KEY is not set")
    value: str = secret.get_secret_value()
    return value


@pytest.mark.parametrize("name", ["groq", "mistral"])
def test_configured_model_is_listed(settings: Settings, name: str) -> None:
    key = _key(settings, name)
    res = httpx.get(MODELS_URL[name], headers={"Authorization": f"Bearer {key}"}, timeout=20)
    assert res.status_code == 200, res.status_code
    models = {m["id"]: m for m in res.json()["data"]}
    model = getattr(settings, f"{name}_model")
    assert model in models, f"{model} not offered by {name}"
    if name == "mistral":
        assert models[model]["capabilities"]["vision"] is True


def _provider(settings: Settings, name: str, model: str | None = None) -> OpenAICompatProvider:
    key = _key(settings, name)
    cls = GroqProvider if name == "groq" else MistralProvider
    return cls(key, model or getattr(settings, f"{name}_model"))


@pytest.mark.parametrize("name", ["groq", "mistral"])
def test_one_live_call_parses_into_tier2_reply(
    settings: Settings, case: dict[str, Any], name: str
) -> None:
    provider = _provider(settings, name)
    try:
        raw = provider.complete(case["prompt"], case["image"])
    except ProviderAuthError as exc:
        if "quota is 0" in str(exc):
            pytest.skip(f"{name}: account quota is 0 requests/minute (activate the plan)")
        raise
    reply = parse_reply(raw, case["ids"])
    assert reply.mark_id == case["expected_mark_id"], reply  # "confirm order", not "cancel order"
    assert 0.0 <= reply.confidence <= 1.0


def test_real_fallback_groq_fails_mistral_answers(
    settings: Settings, case: dict[str, Any], tmp_path: Path
) -> None:
    mistral = _provider(settings, "mistral")
    broken_groq = _provider(settings, "groq", model="healwright/no-such-model")
    router = Router([broken_groq, mistral], ResponseCache(tmp_path / "cache", "record"), 5)
    try:
        result = router.ask(case["prompt"], case["image"], case["ids"], case["marks_table"])
    except ProviderError as exc:
        # the quota header only appears on chat responses, so it can only be seen after a call
        if "quota is 0" in str(exc):
            pytest.skip("mistral: account quota is 0 requests/minute (activate the plan)")
        raise
    assert result.provider == "mistral"
    assert result.reply.mark_id == case["expected_mark_id"]
