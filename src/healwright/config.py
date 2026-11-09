"""Runtime settings.

HealWright settings use the ``HEALWRIGHT_`` prefix; provider settings are read
without it. Values come from the environment, then a git-ignored ``.env``.
API keys are ``SecretStr`` so they never appear in a repr, a log or a run
folder. Model names are configured here and nowhere else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ProviderName = Literal["gemini", "groq", "mistral"]
KNOWN_PROVIDERS: frozenset[str] = frozenset({"gemini", "groq", "mistral"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HEALWRIGHT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds keys and Chaos Store variables
        frozen=True,
    )

    # --- HealWright (HEALWRIGHT_*) ---
    mode: Literal["off", "record", "heal"] = "heal"
    probe_timeout_ms: Annotated[int, Field(gt=0)] = 3000
    tau_conf: Annotated[float, Field(ge=0.0, le=1.0)] = 0.70
    delta_margin: Annotated[float, Field(ge=0.0, le=1.0)] = 0.06  # tuned on the dev split
    tier2_floor: Annotated[float, Field(ge=0.0, le=1.0)] = 0.35
    max_heals_per_test: Annotated[int, Field(ge=0)] = 3
    heal_deadline_s: Annotated[float, Field(gt=0)] = 30.0
    vlm_mode: Literal["live", "record", "replay"] = "record"
    vlm_run_cap: Annotated[int, Field(ge=0)] = 30
    # Retry policy for VLM calls (defaults: 2 retries, Retry-After <= 10 s).
    # The benchmark raises them (4 retries, Retry-After <= 60 s) so free-tier
    # rate limits cost waiting time instead of scenarios.
    vlm_max_retries: Annotated[int, Field(ge=0, le=6)] = 2
    vlm_retry_after_cap_s: Annotated[float, Field(gt=0, le=120)] = 10.0
    # Provider chain: Groq -> Mistral -> needs_human. Gemini is not free on the team's account:
    # its client stays, but it is not in the default chain.
    providers: Annotated[tuple[ProviderName, ...], NoDecode] = ("groq", "mistral")
    artifact_dir: Path = Path(".healwright")
    # Baselines are committed with the tests, so by default they live in the repo
    # (<rootdir>/.healwright/baselines) even when artifact_dir points at another drive.
    baseline_dir: Path | None = None
    # VLM reply cache (live/record/replay). Default <artifact_dir>/cache. The benchmark
    # points it at a persistent, committed folder so replay reproduces real replies.
    vlm_cache_dir: Path | None = None
    # ABLATION ONLY (benchmark systems healwright_noverify / greedy): skip the sandbox
    # verifier and the live re-check. Never disable in real use: it removes the
    # protection against look-alike heals.
    verify: bool = True
    debug: bool = False
    # API: when set, every /api request needs "Authorization: Bearer <token>",
    # and `healwright serve` may bind to a non-local address.
    api_token: SecretStr | None = None
    # Public-safe mode for a hosted demo: no triage or patch apply, no headed
    # watch mode, one demo at a time plus a per-visitor cooldown, demo temp files removed.
    # It also allows `healwright serve` to bind to a non-local address without a token,
    # because nothing that writes to the repository is reachable.
    public: bool = False
    demo_cooldown_s: Annotated[float, Field(ge=0, le=3600)] = 60.0
    # Internal Chaos Store for "Open the broken shop", proxied under /shop (public mode).
    shop_url: str | None = None
    # Extra CORS origins (comma-separated), e.g. the hosted showcase site.
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ()

    # --- Providers (no prefix: an explicit alias bypasses env_prefix) ---
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_MODEL")
    groq_api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model: str = Field(
        default="qwen/qwen3.8-27b",  # live-checked 2026-11-07; Llama 4 Scout gone (404)
        validation_alias="GROQ_MODEL",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(part.strip().rstrip("/") for part in value.split(",") if part.strip())
        return value

    @field_validator("providers", mode="before")
    @classmethod
    def _split_providers(cls, value: object) -> object:
        if isinstance(value, str):
            names = [part.strip().lower() for part in value.split(",")]
            return tuple(name for name in names if name)
        return value

    mistral_api_key: SecretStr | None = Field(default=None, validation_alias="MISTRAL_API_KEY")
    mistral_model: str = Field(default="mistral-small-2603", validation_alias="MISTRAL_MODEL")

    @field_validator(
        "gemini_api_key", "groq_api_key", "mistral_api_key", "api_token", mode="before"
    )
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


def load_settings(**overrides: object) -> Settings:
    """Build settings from the environment and ``.env``; ``overrides`` win."""
    return Settings(**overrides)  # type: ignore[arg-type]


__all__ = ["KNOWN_PROVIDERS", "ProviderName", "Settings", "load_settings"]
