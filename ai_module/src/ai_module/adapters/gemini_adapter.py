"""Adapter for the Google Gemini generative AI API."""

from __future__ import annotations

import asyncio

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

from ai_module.adapters.base import LLMAdapter
from ai_module.core.exceptions import LLMCallError, LLMTimeoutError
from ai_module.core.settings import settings


class GeminiAdapter(LLMAdapter):
    """Gemini implementation of the LLM adapter contract."""

    def __init__(
        self,
        api_key: str = settings.GEMINI_API_KEY,
        model: str = settings.LLM_MODEL,
    ) -> None:
        genai.configure(api_key=api_key)
        self._model_name = model

    async def analyze(self, image_bytes: bytes, prompt: str, system_prompt: str) -> str:
        """Calls Gemini with the rendered image and prompt text."""
        try:
            llm = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system_prompt,
            )
            image_part = {"mime_type": "image/png", "data": image_bytes}

            response: GenerateContentResponse = await asyncio.wait_for(
                llm.generate_content_async([image_part, prompt]),
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            content = response.text
            if not content:
                raise LLMCallError("Gemini returned an empty response.")
            return content

        except asyncio.TimeoutError as e:
            raise LLMTimeoutError(
                f"Timeout after {settings.LLM_TIMEOUT_SECONDS}s calling Gemini."
            ) from e
        except (LLMTimeoutError, LLMCallError):
            raise
        except Exception as e:
            raise LLMCallError(f"Error calling Gemini: {e}") from e