"""Unit tests for pipeline module — Phase 5, tasks 5.4.7–5.4.14."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest  # type: ignore

from ai_module.core.exceptions import AIFailureError, AITimeoutError, LLMTimeoutError
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

    with pytest.raises(AITimeoutError):
        await run_pipeline(png_bytes, "img.png", "analysis-123", timeout_adapter)

    assert timeout_adapter.analyze.await_count == settings.LLM_MAX_RETRIES


@pytest.mark.asyncio
async def test_pipeline_logs_analysis_id_and_events(
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    pipeline_logger = logging.getLogger("ai_module.core.pipeline")
    pipeline_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="ai_module.core.pipeline"):
            await run_pipeline(png_bytes, "img.png", "test-log-id", mock_adapter)
    finally:
        pipeline_logger.removeHandler(caplog.handler)

    messages = [r.getMessage() for r in caplog.records]
    assert any("Analysis request received" in m for m in messages)
    assert any("Analysis completed successfully" in m for m in messages)
    ids_in_extra = [getattr(r, "analysis_id", None) for r in caplog.records]
    assert "test-log-id" in ids_in_extra


@pytest.mark.asyncio
async def test_run_pipeline_includes_context_metadata_without_conflict(
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
) -> None:
    context_text = "api-service autentica requisicoes no gateway"

    response = await run_pipeline(
        png_bytes,
        "img.png",
        "analysis-context-ok",
        mock_adapter,
        context_text=context_text,
    )

    assert response.metadata.context_text_provided is True
    assert response.metadata.context_text_length == len(context_text)
    assert response.metadata.conflict_detected is False
    assert response.metadata.conflict_decision == "NO_CONFLICT"
    assert response.metadata.conflict_policy == "DIAGRAM_FIRST"


@pytest.mark.asyncio
async def test_run_pipeline_includes_conflict_decision_for_context(
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
) -> None:
    conflicting_context = "mensagem legado folha batch monolito centralizado externo"

    response = await run_pipeline(
        png_bytes,
        "img.png",
        "analysis-context-conflict",
        mock_adapter,
        context_text=conflicting_context,
    )

    assert response.metadata.context_text_provided is True
    assert response.metadata.context_text_length == len(conflicting_context)
    assert response.metadata.conflict_detected is True
    assert response.metadata.conflict_decision == "DIAGRAM_FIRST"
    assert response.metadata.conflict_policy == "DIAGRAM_FIRST"
