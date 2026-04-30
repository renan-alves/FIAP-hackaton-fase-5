from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient

from ai_module.core.metrics import metrics
from ai_module.core.state import set_service_health


def test_health_returns_503_when_service_is_degraded(client: TestClient) -> None:
    set_service_health(False)

    try:
        response = client.get("/health")
    finally:
        set_service_health(True)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["detail"]["status"] == "degraded"
    assert "llm_provider" in body["detail"]


def test_health_returns_200_when_service_is_healthy(client: TestClient) -> None:
    set_service_health(True)

    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "healthy"
    assert "llm_provider" in body


def test_metrics_endpoint_returns_expected_prometheus_lines(client: TestClient) -> None:
    original = (
        metrics.requests_success,
        metrics.requests_error,
        metrics.processing_time_ms_total,
        metrics.llm_retries_total,
    )
    metrics.requests_success = 7
    metrics.requests_error = 3
    metrics.processing_time_ms_total = 1234
    metrics.llm_retries_total = 2

    try:
        response = client.get("/metrics")
    finally:
        (
            metrics.requests_success,
            metrics.requests_error,
            metrics.processing_time_ms_total,
            metrics.llm_retries_total,
        ) = original

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert "# HELP ai_requests_total" in text
    assert 'ai_requests_total{status="success"} 7' in text
    assert 'ai_requests_total{status="error"} 3' in text
    assert "ai_processing_time_ms_avg 123" in text
    assert "ai_llm_retries_total 2" in text
    assert "ai_llm_provider_active" in text


def test_analyze_returns_504_when_llm_times_out(client: TestClient, png_bytes: bytes) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.core.exceptions import LLMTimeoutError
    from ai_module.main import app

    mock_adapter = SimpleNamespace(analyze=AsyncMock(side_effect=LLMTimeoutError("timeout")))
    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter
    try:
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
            data={"analysis_id": "test-timeout-id"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    assert response.status_code == 504
    body = response.json()
    assert body["status"] == "error"
    assert body["error_code"] == "AI_TIMEOUT"


def test_analyze_response_does_not_contain_raw_llm_string(
    client: TestClient, png_bytes: bytes, valid_report_json: str
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    RAW_SENTINEL = "RAW_MOCK_LLM_RESPONSE_THAT_SHOULD_NEVER_APPEAR_IN_OUTPUT"
    mock_adapter = SimpleNamespace(analyze=AsyncMock(return_value=valid_report_json))
    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter
    try:
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
            data={"analysis_id": "test-sentinel-id"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    assert response.status_code == 200
    assert RAW_SENTINEL not in response.text


def test_analyze_with_conflicting_context_returns_diagram_first_metadata(
    client: TestClient,
    png_bytes: bytes,
    valid_report_json: str,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    mock_adapter = SimpleNamespace(analyze=AsyncMock(return_value=valid_report_json))
    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter
    try:
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
            data={
                "analysis_id": "test-context-conflict-id",
                "context_text": "mainframe legado processo batch noturno fila cassandra externo",
            },
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["context_text_provided"] is True
    assert body["metadata"]["conflict_detected"] is True
    assert body["metadata"]["conflict_decision"] == "DIAGRAM_FIRST"
    assert body["metadata"]["conflict_policy"] == "DIAGRAM_FIRST"
