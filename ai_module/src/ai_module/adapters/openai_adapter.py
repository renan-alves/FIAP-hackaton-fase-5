"""Adapter for OpenAI chat completions with image input."""

from __future__ import annotations

import asyncio
import base64

from openai import AsyncOpenAI

from ai_module.adapters.base import LLMAdapter
from ai_module.core.exceptions import LLMCallError, LLMTimeoutError
from ai_module.core.settings import settings


class OpenAIAdapter(LLMAdapter):
    """OpenAI implementation of the LLM adapter contract."""

    def __init__(
        self,
        api_key: str = settings.OPENAI_API_KEY,
        model: str = settings.LLM_MODEL,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def analyze(self, image_bytes: bytes, prompt: str, system_prompt: str) -> str:
        """Calls OpenAI with the rendered image and prompt text."""
        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:image/png;base64,{image_b64}"

            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": data_url}},
                                {"type": "text", "text": prompt},
                            ],
                        },
                    ],
                ),
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )

            content = response.choices[0].message.content
            if content is None:
                raise LLMCallError("OpenAI returned an empty response.")
            if isinstance(content, list):
                content = "".join(
                    item.text for item in content if hasattr(item, "text") and item.text
                )
            if not content:
                raise LLMCallError("OpenAI returned an empty response.")
            return content

        except asyncio.TimeoutError as e:
            raise LLMTimeoutError(
                f"Timeout after {settings.LLM_TIMEOUT_SECONDS}s calling OpenAI."
            ) from e
        except (LLMTimeoutError, LLMCallError):
            raise
        except Exception as e:
            raise LLMCallError(f"Error calling OpenAI: {e}") from e
