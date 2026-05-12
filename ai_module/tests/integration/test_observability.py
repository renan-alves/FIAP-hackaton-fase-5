"""Integration tests for health and metrics observability endpoints."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ai_module.adapters.factory import get_llm_adapter
from ai_module.core.metrics import metrics
from ai_module.core.state import set_service_health
from ai_module.main import app


def test_health_healthy_response_schema(client: TestClient) -> None:
    set_service_health(True)

    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "healthy"
    assert "llm_provider" in body
    assert isinstance(body["llm_provider"], str)
    assert len(body["llm_provider"]) > 0


def test_health_degraded_response_schema(client: TestClient) -> None:
    set_service_health(False)

    try:
        response = client.get("/health")
    finally:
        set_service_health(True)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()
    # Body must be top-level — not nested under "detail"
    assert "detail" not in body
    assert body["status"] == "degraded"
    assert "llm_provider" in body
    assert isinstance(body["llm_provider"], str)


def test_health_degraded_body_is_top_level_not_detail_wrapped(client: TestClient) -> None:
    """AC-009: Degraded health response MUST use top-level JSON, never HTTPException detail."""
    set_service_health(False)
    try:
        response = client.get("/health")
    finally:
        set_service_health(True)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()
    assert "detail" not in body, "Body must not be wrapped under 'detail' key"
    assert body.get("status") == "degraded"
    assert "version" in body
    assert "queue_connected" in body


def test_health_degraded_when_rabbitmq_startup_fails(client: TestClient) -> None:
    """AC-009: RabbitMQ startup failure must mark service as degraded (503)."""
    from ai_module.core.state import set_queue_health, set_service_health

    # Simulate: RabbitMQ connect failed → both queue and service marked unhealthy
    set_queue_health(False)
    set_service_health(False)
    try:
        response = client.get("/health")
    finally:
        set_service_health(True)
        set_queue_health(False)  # restore to default disabled state

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["status"] == "degraded"
    assert body["queue_connected"] is False


def test_health_recovers_after_degraded(client: TestClient) -> None:
    set_service_health(False)
    degraded_response = client.get("/health")
    assert degraded_response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    set_service_health(True)
    healthy_response = client.get("/health")
    assert healthy_response.status_code == status.HTTP_200_OK


def test_metrics_response_content_type_is_plain_text(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    assert "text/plain" in response.headers["content-type"]


def test_metrics_contains_all_required_prometheus_keys(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert "ai_requests_total" in text
    assert "ai_processing_time_ms_avg" in text
    assert "ai_llm_retries_total" in text
    assert "ai_llm_provider_active" in text


def test_metrics_contains_help_and_type_annotations(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert "# HELP" in text
    assert "# TYPE" in text


def test_metrics_reflect_successful_analyze_request(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    before = metrics.requests_success

    client.post(
        "/analyze",
        data={"analysis_id": "obs-test-01"},
        files={"file": ("diag.png", png_bytes, "image/png")},
    )

    assert metrics.requests_success == before + 1


def test_metrics_reflect_failed_analyze_request(
    client: TestClient,
    corrupted_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    before = metrics.requests_error

    client.post(
        "/analyze",
        data={"analysis_id": "obs-test-02"},
        files={"file": ("bad.png", corrupted_bytes, "image/png")},
    )

    assert metrics.requests_error == before + 1


def test_health_contains_queue_connected_field(client: TestClient) -> None:
    set_service_health(True)

    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "queue_connected" in body
    assert isinstance(body["queue_connected"], bool)


def test_metrics_contains_publish_counters(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert "queue_publish_failures_total" in text
    assert "queue_messages_published_total" in text


def test_metrics_contain_labeled_publish_results(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert 'queue_results_published_total{status="success"}' in text
    assert 'queue_results_published_total{status="error"}' in text


async def test_publisher_logs_result_published_on_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai_module.models.queue import QueueAnalysisResponse
    from ai_module.worker.publisher import RabbitMQResultPublisher

    mock_adapter = MagicMock()
    mock_adapter.is_connected = True

    mock_channel = AsyncMock()
    mock_channel.default_exchange.publish = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    from ai_module.models.report import Component, ComponentType, Report, ReportMetadata

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    response = QueueAnalysisResponse(
        analysis_id="log-test-01",
        report=Report(
            summary="ok",
            components=[Component(name="svc", type=ComponentType.SERVICE, description="test")],
        ),
        metadata=ReportMetadata(
            model_used="test",
            processing_time_ms=1,
            input_type="image",
        ),
    )

    pub_logger = logging.getLogger("ai_module.worker.publisher")
    original_propagate = pub_logger.propagate
    pub_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="ai_module.worker.publisher"):
            await publisher.publish_success(response)
    finally:
        pub_logger.propagate = original_propagate

    log_extras = [r.__dict__ for r in caplog.records]
    events = [e.get("event") for e in log_extras]
    assert "result_published" in events

    success_record = next(
        r for r in caplog.records if r.__dict__.get("event") == "result_published"
    )
    assert success_record.__dict__.get("status") == "success"
    assert "queue_name" in success_record.__dict__


async def test_publisher_logs_publish_failed_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai_module.models.queue import QueueAnalysisResponse
    from ai_module.models.report import Component, ComponentType, Report, ReportMetadata
    from ai_module.worker.publisher import RabbitMQResultPublisher

    mock_adapter = MagicMock()
    mock_adapter.is_connected = False
    mock_adapter.get_channel = AsyncMock(side_effect=ConnectionError("broker down"))

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    response = QueueAnalysisResponse(
        analysis_id="log-test-02",
        report=Report(
            summary="ok",
            components=[Component(name="svc", type=ComponentType.SERVICE, description="test")],
        ),
        metadata=ReportMetadata(
            model_used="test",
            processing_time_ms=1,
            input_type="image",
        ),
    )

    pub_logger = logging.getLogger("ai_module.worker.publisher")
    original_propagate = pub_logger.propagate
    pub_logger.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger="ai_module.worker.publisher"):
            with pytest.raises(ConnectionError):
                await publisher.publish_success(response)
    finally:
        pub_logger.propagate = original_propagate

    log_extras = [r.__dict__ for r in caplog.records]
    events = [e.get("event") for e in log_extras]
    assert "publish_attempt_failed" in events

    failed_record = next(
        r for r in caplog.records if r.__dict__.get("event") == "publish_attempt_failed"
    )
    assert "error_type" in failed_record.__dict__
    assert "queue_name" in failed_record.__dict__
