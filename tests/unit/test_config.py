"""Tests for healwright.config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from healwright.config import Settings

pytestmark = pytest.mark.unit

PROVIDER_VARS = ("GEMINI_API_KEY", "GEMINI_MODEL", "GROQ_API_KEY", "GROQ_MODEL")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """No HEALWRIGHT_* or provider variables, and no .env in the working directory."""
    for name in list(os.environ):
        if name.startswith("HEALWRIGHT_") or name in PROVIDER_VARS:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return monkeypatch


def test_defaults_with_no_env(clean_env: pytest.MonkeyPatch) -> None:
    s = Settings()
    assert s.mode == "heal"
    assert s.probe_timeout_ms == 3000
    assert s.tau_conf == 0.70
    assert s.delta_margin == 0.06
    assert s.tier2_floor == 0.35
    assert s.max_heals_per_test == 3
    assert s.heal_deadline_s == 30
    assert s.vlm_mode == "record"
    assert s.vlm_run_cap == 30
    assert s.providers == ("groq", "mistral")
    assert s.artifact_dir == Path(".healwright")
    assert s.debug is False
    assert s.gemini_api_key is None
    assert s.groq_api_key is None
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.groq_model == "qwen/qwen3.8-27b"


def test_verifier_is_on_by_default_and_only_an_explicit_false_disables_it(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """HEALWRIGHT_VERIFY defaults to ON; false is for the ablation only."""
    assert Settings().verify is True
    clean_env.setenv("HEALWRIGHT_VERIFY", "false")
    assert Settings().verify is False


def test_prefixed_env_overrides(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("HEALWRIGHT_MODE", "record")
    clean_env.setenv("HEALWRIGHT_TAU_CONF", "0.8")
    clean_env.setenv("HEALWRIGHT_VLM_RUN_CAP", "0")
    clean_env.setenv("HEALWRIGHT_PROVIDERS", " Groq , gemini ")
    clean_env.setenv("HEALWRIGHT_DEBUG", "true")
    s = Settings()
    assert (s.mode, s.tau_conf, s.vlm_run_cap, s.debug) == ("record", 0.8, 0, True)
    assert s.providers == ("groq", "gemini")


def test_provider_settings_have_no_prefix(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GEMINI_MODEL", "gemini-x")
    clean_env.setenv("HEALWRIGHT_GEMINI_MODEL", "ignored")
    clean_env.setenv("GROQ_API_KEY", "gsk_test_value")
    s = Settings()
    assert s.gemini_model == "gemini-x"
    assert s.groq_api_key is not None
    assert s.groq_api_key.get_secret_value() == "gsk_test_value"


def test_keys_never_appear_in_repr_or_dump(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GEMINI_API_KEY", "AIza-test-secret")
    s = Settings()
    assert "AIza-test-secret" not in repr(s)
    assert "AIza-test-secret" not in s.model_dump_json()


def test_blank_key_is_treated_as_missing(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GEMINI_API_KEY", "   ")
    assert Settings().gemini_api_key is None


def test_dotenv_is_read(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HEALWRIGHT_MODE=off\nCHAOS_CONTROL=1\n", encoding="utf-8")
    assert Settings().mode == "off"


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("HEALWRIGHT_MODE", "fix"),
        ("HEALWRIGHT_VLM_MODE", "offline"),
        ("HEALWRIGHT_PROVIDERS", "gemini,openrouter"),
        ("HEALWRIGHT_TAU_CONF", "1.5"),
        ("HEALWRIGHT_PROBE_TIMEOUT_MS", "0"),
        ("HEALWRIGHT_VLM_RUN_CAP", "-1"),
    ],
)
def test_invalid_values_rejected(clean_env: pytest.MonkeyPatch, var: str, value: str) -> None:
    clean_env.setenv(var, value)
    with pytest.raises(ValidationError):
        Settings()


def test_settings_are_immutable(clean_env: pytest.MonkeyPatch) -> None:
    s = Settings()
    with pytest.raises(ValidationError):
        s.mode = "off"  # type: ignore[misc]
