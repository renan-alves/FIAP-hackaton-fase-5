"""Base interface for LLM adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_module.core.exceptions import LLMCallError, LLMTimeoutError


class LLMAdapter(ABC):
    """Abstract base class for all LLM provider adapters."""

    @abstractmethod
    async def analyze(self, image_bytes: bytes, prompt: str, system_prompt: str) -> str:
        """Send an image and prompt to the LLM provider and return the raw response.

        Raises:
            LLMTimeoutError: if the call exceeds the configured timeout.
            LLMCallError: on SDK or provider failure.
        """
        ...
