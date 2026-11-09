"""Groq provider (kept as a module for existing imports; see openai_compat.py)."""

from healwright.tier2.providers.openai_compat import GROQ_URL, TIMEOUT, GroqProvider

__all__ = ["GROQ_URL", "TIMEOUT", "GroqProvider"]
