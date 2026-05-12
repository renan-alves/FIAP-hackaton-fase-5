"""Unit tests for RabbitMQResultPublisher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_module.core.metrics import metrics
from ai_module.models.queue import QueueAnalysisResponse, QueueErrorResponse
from ai_module.models.report import Component, ComponentType, Report, ReportMetadata
from ai_module.worker.publisher import RabbitMQResultPublisher

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ANALYSIS_ID = "test-analysis-001"


def _make_report() -> Report:
    return Report(
        summary="Test architecture summary",
        components=[
            Component(
                name="API Gateway",
                type=ComponentType.GATEWAY,
                description="Main entry point",
            )
        ],
    )


def _make_metadata() -> ReportMetadata:
    return ReportMetadata(
        model_used="gpt-4o",
        processing_time_ms=1500,
        input_type="image",
    )


def _make_success_response() -> QueueAnalysisResponse:
    return QueueAnalysisResponse(
        analysis_id=_ANALYSIS_ID,
        status="success",
        report=_make_report(),
        metadata=_make_metadata(),
    )


def _make_error_response() -> QueueErrorResponse:
    return QueueErrorResponse(
        analysis_id=_ANALYSIS_ID,
        status="error",
        error_code="AI_FAILURE",
        message="LLM processing failed",
    )


def _make_publisher() -> tuple[RabbitMQResultPublisher, AsyncMock, AsyncMock]:
    """Return (publisher, mock_adapter, mock_exchange_publish)."""
    mock_publish = AsyncMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish

    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

    mock_adapter = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    return publisher, mock_adapter, mock_publish


# ---------------------------------------------------------------------------
# publish_success tests
# ---------------------------------------------------------------------------


async def test_publish_success_calls_exchange_publish():
    """publish_success should call channel.default_exchange.publish once."""
    publisher, _, mock_publish = _make_publisher()

    await publisher.publish_success(_make_success_response())

    mock_publish.assert_called_once()


async def test_publish_success_uses_correct_routing_key(monkeypatch):
    """publish_success should route to RABBITMQ_OUTPUT_QUEUE."""
    from ai_module.core import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "RABBITMQ_OUTPUT_QUEUE", "analysis.results")

    publisher, _, mock_publish = _make_publisher()
    await publisher.publish_success(_make_success_response())

    _, kwargs = mock_publish.call_args
    assert kwargs.get("routing_key") == "analysis.results"


async def test_publish_success_increments_results_published():
    """publish_success should increment metrics.results_published."""
    publisher, _, _ = _make_publisher()
    before = metrics.results_published

    await publisher.publish_success(_make_success_response())

    assert metrics.results_published == before + 1


async def test_publish_success_does_not_increment_errors_published():
    """publish_success must not touch metrics.errors_published."""
    publisher, _, _ = _make_publisher()
    before = metrics.errors_published

    await publisher.publish_success(_make_success_response())

    assert metrics.errors_published == before


async def test_publish_success_does_not_increment_publish_failures_on_success():
    """Successful publish must not increment metrics.publish_failures."""
    publisher, _, _ = _make_publisher()
    before = metrics.publish_failures

    await publisher.publish_success(_make_success_response())

    assert metrics.publish_failures == before


async def test_publish_success_sends_json_body():
    """The message body should be the JSON-encoded response."""
    publisher, _, mock_publish = _make_publisher()
    response = _make_success_response()

    await publisher.publish_success(response)

    (published_message,), _ = mock_publish.call_args
    assert published_message.body == response.model_dump_json().encode()


async def test_publish_success_sets_persistent_delivery_mode():
    """Messages must be durable (PERSISTENT delivery mode)."""
    from aio_pika import DeliveryMode

    publisher, _, mock_publish = _make_publisher()

    await publisher.publish_success(_make_success_response())

    (published_message,), _ = mock_publish.call_args
    assert published_message.delivery_mode == DeliveryMode.PERSISTENT


async def test_publish_success_sets_content_type():
    """Message content_type must be application/json."""
    publisher, _, mock_publish = _make_publisher()

    await publisher.publish_success(_make_success_response())

    (published_message,), _ = mock_publish.call_args
    assert published_message.content_type == "application/json"


# ---------------------------------------------------------------------------
# publish_error tests
# ---------------------------------------------------------------------------


async def test_publish_error_calls_exchange_publish():
    """publish_error should call channel.default_exchange.publish once."""
    publisher, _, mock_publish = _make_publisher()

    await publisher.publish_error(_make_error_response())

    mock_publish.assert_called_once()


async def test_publish_error_increments_errors_published():
    """publish_error should increment metrics.errors_published."""
    publisher, _, _ = _make_publisher()
    before = metrics.errors_published

    await publisher.publish_error(_make_error_response())

    assert metrics.errors_published == before + 1


async def test_publish_error_does_not_increment_results_published():
    """publish_error must not touch metrics.results_published."""
    publisher, _, _ = _make_publisher()
    before = metrics.results_published

    await publisher.publish_error(_make_error_response())

    assert metrics.results_published == before


async def test_publish_error_sends_json_body():
    """The message body should be the JSON-encoded error response."""
    publisher, _, mock_publish = _make_publisher()
    error = _make_error_response()

    await publisher.publish_error(error)

    (published_message,), _ = mock_publish.call_args
    assert published_message.body == error.model_dump_json().encode()


async def test_publish_error_sets_persistent_delivery_mode():
    """Error messages must also be durable."""
    from aio_pika import DeliveryMode

    publisher, _, mock_publish = _make_publisher()

    await publisher.publish_error(_make_error_response())

    (published_message,), _ = mock_publish.call_args
    assert published_message.delivery_mode == DeliveryMode.PERSISTENT


# ---------------------------------------------------------------------------
# Retry tests
# ---------------------------------------------------------------------------


async def test_publish_succeeds_on_second_attempt():
    """If the first publish raises, the second attempt should succeed."""

    mock_publish = AsyncMock(
        side_effect=[RuntimeError("transient failure"), None]
    )
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish

    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

    mock_adapter = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    before_failures = metrics.publish_failures
    before_published = metrics.results_published

    with patch("ai_module.worker.publisher.asyncio.sleep", new=AsyncMock()):
        await publisher.publish_success(_make_success_response())

    assert mock_publish.call_count == 2
    assert metrics.publish_failures == before_failures  # no failure counted on retry success
    assert metrics.results_published == before_published + 1


async def test_publish_all_attempts_fail_raises():
    """Exhausting all retry attempts should raise the last exception."""
    from ai_module.worker.publisher import _MAX_PUBLISH_ATTEMPTS

    mock_publish = AsyncMock(side_effect=RuntimeError("persistent failure"))
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish

    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

    mock_adapter = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)

    with patch("ai_module.worker.publisher.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(RuntimeError, match="persistent failure"):
            await publisher.publish_success(_make_success_response())

    assert mock_publish.call_count == _MAX_PUBLISH_ATTEMPTS


async def test_publish_all_attempts_fail_increments_publish_failures():
    """Exhausting all retries must increment metrics.publish_failures by 1."""
    mock_publish = AsyncMock(side_effect=RuntimeError("persistent failure"))
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish

    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

    mock_adapter = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    before = metrics.publish_failures

    with patch("ai_module.worker.publisher.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(RuntimeError):
            await publisher.publish_success(_make_success_response())

    assert metrics.publish_failures == before + 1


async def test_publish_all_attempts_fail_does_not_increment_results_published():
    """Failed publishes must not increment metrics.results_published."""
    mock_publish = AsyncMock(side_effect=RuntimeError("fail"))
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish

    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

    mock_adapter = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    before = metrics.results_published

    with patch("ai_module.worker.publisher.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(RuntimeError):
            await publisher.publish_success(_make_success_response())

    assert metrics.results_published == before


async def test_error_publish_all_attempts_fail_increments_publish_failures():
    """Exhausting all retries on publish_error must also increment publish_failures."""
    mock_publish = AsyncMock(side_effect=RuntimeError("fail"))
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish

    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

    mock_adapter = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    before_failures = metrics.publish_failures
    before_errors = metrics.errors_published

    with patch("ai_module.worker.publisher.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(RuntimeError):
            await publisher.publish_error(_make_error_response())

    assert metrics.publish_failures == before_failures + 1
    assert metrics.errors_published == before_errors  # not incremented on failure


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


async def test_satisfies_result_publisher_protocol():
    """RabbitMQResultPublisher must satisfy the ResultPublisher Protocol."""
    from ai_module.worker.consumer import ResultPublisher

    mock_adapter = AsyncMock()
    publisher = RabbitMQResultPublisher(adapter=mock_adapter)

    assert isinstance(publisher, ResultPublisher)


def test_exported_from_worker_package():
    """RabbitMQResultPublisher must be importable from the worker package."""
    from ai_module.worker import RabbitMQResultPublisher as PublisherFromPackage

    assert PublisherFromPackage is RabbitMQResultPublisher
