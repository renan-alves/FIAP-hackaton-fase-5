"""Unit tests for pipeline module — Phase 5, tasks 5.4.7–5.4.14."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_module.core.exceptions import AIFailureError, LLMTimeoutError
from ai_module.core.pipeline import run_pipeline
from ai_module.core.settings import settings


@pytest.mark.asyncio
async def test_run_pipeline_returns_analyze_response(
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
) -> None:
    response = await run_pipeline(png_bytes, "img.png", "analysis-123", mock_adapter)

    assert response.analysis_id == "analysis-123"
    assert response.status == "success"
    assert response.metadata.input_type == "image"
    assert response.report.components[0].name == "api-service"


@pytest.mark.asyncio
async def test_run_pipeline_raises_ai_failure_after_retries_on_llm_call_error(
    png_bytes: bytes,
    mock_adapter_always_fails: SimpleNamespace,
) -> None:
    with pytest.raises(AIFailureError):
        await run_pipeline(png_bytes, "img.png", "analysis-123", mock_adapter_always_fails)

    assert mock_adapter_always_fails.analyze.await_count == settings.LLM_MAX_RETRIES


@pytest.mark.asyncio
async def test_run_pipeline_raises_ai_failure_after_retries_on_invalid_json(
    png_bytes: bytes,
    mock_adapter_invalid_json: SimpleNamespace,
) -> None:
    with pytest.raises(AIFailureError):
        await run_pipeline(png_bytes, "img.png", "analysis-123", mock_adapter_invalid_json)


@pytest.mark.asyncio
async def test_run_pipeline_raises_ai_failure_after_retries_on_timeout(
    png_bytes: bytes,
) -> None:
    timeout_adapter = SimpleNamespace(analyze=AsyncMock(side_effect=LLMTimeoutError("timed out")))

    with pytest.raises(AIFailureError):
        await run_pipeline(png_bytes, "img.png", "analysis-123", timeout_adapter)

    assert timeout_adapter.analyze.await_count == settings.LLM_MAX_RETRIES