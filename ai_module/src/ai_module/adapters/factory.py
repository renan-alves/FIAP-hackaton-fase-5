"""Factory for selecting the configured LLM adapter."""

from __future__ import annotations

from ai_module.adapters.base import LLMAdapter
from ai_module.adapters.gemini_adapter import GeminiAdapter
from ai_module.adapters.openai_adapter import OpenAIAdapter
from ai_module.core.settings import settings


def get_llm_adapter() -> LLMAdapter:
    """Returns the adapter based on the configured provider."""
    provider = settings.LLM_PROVIDER.upper()

    if provider == "GEMINI":
        return GeminiAdapter(api_key=settings.GEMINI_API_KEY, model=settings.LLM_MODEL)
    if provider == "OPENAI":
        return OpenAIAdapter(api_key=settings.OPENAI_API_KEY, model=settings.LLM_MODEL)

    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER!r}")
