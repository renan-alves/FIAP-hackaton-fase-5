"""Unit tests for LLM adapters — Phase 4, tasks 4.5.1–4.5.10."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_module.adapters.base import LLMAdapter
from ai_module.adapters.factory import get_llm_adapter
from ai_module.adapters.gemini_adapter import GeminiAdapter
from ai_module.adapters.openai_adapter import OpenAIAdapter
from ai_module.core.exceptions import LLMCallError, LLMTimeoutError
from ai_module.core.settings import settings

_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_PROMPT = "analyze this"
_SYSTEM = "you are an assistant"
_RESPONSE_TEXT = '{"summary": "ok"}'


# ---------------------------------------------------------------------------
# 4.5.2 – 4.5.4  Factory
# ---------------------------------------------------------------------------


def test_factory_gemini_returns_gemini_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    adapter = get_llm_adapter()
    assert isinstance(adapter, GeminiAdapter)


def test_factory_openai_returns_openai_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    adapter = get_llm_adapter()
    assert isinstance(adapter, OpenAIAdapter)


def test_factory_invalid_provider_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "invalid")
    with pytest.raises(ValueError, match="invalid"):
        get_llm_adapter()


# ---------------------------------------------------------------------------
# 4.5.5 / 4.5.7 / 4.5.9  GeminiAdapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_adapter_returns_response_text(png_bytes: bytes) -> None:
    mock_response = MagicMock()
    mock_response.text = _RESPONSE_TEXT

    with patch("ai_module.adapters.gemini_adapter.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        adapter = GeminiAdapter(api_key="fake-key", model="gemini-pro-vision")
        result = await adapter.analyze(png_bytes, _PROMPT, _SYSTEM)

    assert result == _RESPONSE_TEXT


@pytest.mark.asyncio
async def test_gemini_adapter_timeout_raises_llm_timeout_error(png_bytes: bytes) -> None:
    with patch("ai_module.adapters.gemini_adapter.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_genai.GenerativeModel.return_value = mock_model

        adapter = GeminiAdapter(api_key="fake-key", model="gemini-pro-vision")
        with pytest.raises(LLMTimeoutError):
            await adapter.analyze(png_bytes, _PROMPT, _SYSTEM)


@pytest.mark.asyncio
async def test_gemini_adapter_sdk_error_raises_llm_call_error(png_bytes: bytes) -> None:
    with patch("ai_module.adapters.gemini_adapter.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(side_effect=Exception("sdk error"))
        mock_genai.GenerativeModel.return_value = mock_model

        adapter = GeminiAdapter(api_key="fake-key", model="gemini-pro-vision")
        with pytest.raises(LLMCallError, match="sdk error"):
            await adapter.analyze(png_bytes, _PROMPT, _SYSTEM)


# ---------------------------------------------------------------------------
# 4.5.6 / 4.5.8 / 4.5.10  OpenAIAdapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_adapter_returns_response_text(png_bytes: bytes) -> None:
    mock_message = MagicMock()
    mock_message.content = _RESPONSE_TEXT
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch("ai_module.adapters.openai_adapter.AsyncOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        adapter = OpenAIAdapter(api_key="fake-key", model="gpt-4o")
        result = await adapter.analyze(png_bytes, _PROMPT, _SYSTEM)

    assert result == _RESPONSE_TEXT


@pytest.mark.asyncio
async def test_openai_adapter_timeout_raises_llm_timeout_error(png_bytes: bytes) -> None:
    with patch("ai_module.adapters.openai_adapter.AsyncOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_cls.return_value = mock_client

        adapter = OpenAIAdapter(api_key="fake-key", model="gpt-4o")
        with pytest.raises(LLMTimeoutError):
            await adapter.analyze(png_bytes, _PROMPT, _SYSTEM)


@pytest.mark.asyncio
async def test_openai_adapter_sdk_error_raises_llm_call_error(png_bytes: bytes) -> None:
    with patch("ai_module.adapters.openai_adapter.AsyncOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("api down"))
        mock_cls.return_value = mock_client

        adapter = OpenAIAdapter(api_key="fake-key", model="gpt-4o")
        with pytest.raises(LLMCallError, match="api down"):
            await adapter.analyze(png_bytes, _PROMPT, _SYSTEM)
