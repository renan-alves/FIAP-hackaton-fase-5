"""Integration tests for the RabbitMQ result publisher (FUN-010).

Exercises the full :class:`~ai_module.worker.publisher.RabbitMQResultPublisher`
flow using mocked aio-pika objects — no live broker required.

Coverage
--------
* Success publish — routing key, delivery mode, content_type, ACK-free fire-and-forget
* Error publish — same message-level guarantees
* Retry on transient failure — first attempt fails, second succeeds
* Exhaustion — all attempts fail, exception re-raised, publish_failures incremented
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_module.core.metrics import metrics
from ai_module.models.queue import QueueAnalysisResponse, QueueErrorResponse
from ai_module.models.report import Component, Report, ReportMetadata
from ai_module.worker.publisher import RabbitMQResultPublisher

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_ANALYSIS_ID = str(uuid.uuid4())
_OUTPUT_QUEUE = "analysis.results"
_EXCHANGE_NAME = "analysis"


def _make_publisher() -> tuple[RabbitMQResultPublisher, AsyncMock, AsyncMock]:
    """Return (publisher, mock_adapter, mock_exchange_publish).

    Mocks channel.declare_exchange() to return a mock exchange whose .publish
    is the returned AsyncMock — matching the topology used after T015.
    """
    mock_publish = AsyncMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish

    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

    mock_adapter = AsyncMock()
    mock_adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=mock_adapter)
    return publisher, mock_adapter, mock_publish


def _make_success_response(analysis_id: str = _ANALYSIS_ID) -> QueueAnalysisResponse:
    return QueueAnalysisResponse(
        analysis_id=analysis_id,
        status="success",
        report=Report(
            summary="High-level architecture with microservices",
            components=[Component(name="API", type="gateway", description="Entry point")],
            risks=[],
            recommendations=[],
        ),
        metadata=ReportMetadata(
            model_used="gpt-4o",
            processing_time_ms=150,
            input_type="image",
        ),
    )


def _make_error_response(
    analysis_id: str = _ANALYSIS_ID,
    error_code: str = "AI_FAILURE",
) -> QueueErrorResponse:
    return QueueErrorResponse(
        analysis_id=analysis_id,
        status="error",
        error_code=error_code,
        message="Analysis failed",
    )


# ---------------------------------------------------------------------------
# Tests — success publish full flow
# ---------------------------------------------------------------------------


class TestPublishSuccessFullFlow:
    """End-to-end success publish with mocked adapter."""

    async def test_publish_success_full_flow(self):
        publisher, _, mock_publish = _make_publisher()
        response = _make_success_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        mock_publish.assert_called_once()

    async def test_published_message_routing_key(self):
        publisher, mock_adapter, mock_publish = _make_publisher()
        response = _make_success_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        _, kwargs = mock_publish.call_args
        assert kwargs["routing_key"] == _OUTPUT_QUEUE

    async def test_declare_exchange_called_with_named_exchange(self):
        """Publisher must route via named exchange, not default exchange (T015)."""
        import aio_pika

        publisher, mock_adapter, _ = _make_publisher()
        mock_channel = (await mock_adapter.get_channel.return_value
                        if False else mock_adapter.get_channel.return_value)
        response = _make_success_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        mock_channel.declare_exchange.assert_called_once_with(
            _EXCHANGE_NAME,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

    async def test_published_message_is_persistent(self):
        from aio_pika import DeliveryMode

        publisher, _, mock_publish = _make_publisher()
        response = _make_success_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        positional_args, _ = mock_publish.call_args
        published_message = positional_args[0]
        assert published_message.delivery_mode == DeliveryMode.PERSISTENT

    async def test_published_message_has_json_content_type(self):
        publisher, _, mock_publish = _make_publisher()
        response = _make_success_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        positional_args, _ = mock_publish.call_args
        published_message = positional_args[0]
        assert published_message.content_type == "application/json"

    async def test_published_success_body_is_valid_json(self):
        publisher, _, mock_publish = _make_publisher()
        response = _make_success_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        positional_args, _ = mock_publish.call_args
        published_message = positional_args[0]
        parsed = json.loads(published_message.body)
        assert parsed["status"] == "success"
        assert parsed["analysis_id"] == _ANALYSIS_ID


# ---------------------------------------------------------------------------
# Tests — error publish full flow
# ---------------------------------------------------------------------------


class TestPublishErrorFullFlow:
    """End-to-end error publish with mocked adapter."""

    async def test_publish_error_full_flow(self):
        publisher, _, mock_publish = _make_publisher()
        error = _make_error_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_error(error)

        mock_publish.assert_called_once()

    async def test_publish_error_routing_key(self):
        publisher, _, mock_publish = _make_publisher()
        error = _make_error_response()

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_error(error)

        _, kwargs = mock_publish.call_args
        assert kwargs["routing_key"] == _OUTPUT_QUEUE

    async def test_publish_error_body_contains_error_code(self):
        publisher, _, mock_publish = _make_publisher()
        error = _make_error_response(error_code="AI_TIMEOUT")

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_error(error)

        positional_args, _ = mock_publish.call_args
        published_message = positional_args[0]
        parsed = json.loads(published_message.body)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == "AI_TIMEOUT"


# ---------------------------------------------------------------------------
# Tests — retry behaviour
# ---------------------------------------------------------------------------


class TestPublishRetryBehaviour:
    """Publisher retries on transient failures."""

    async def test_retry_on_transient_failure_succeeds_on_second_attempt(self):
        """First attempt raises, second succeeds — only one message published."""
        publisher, mock_adapter, mock_publish = _make_publisher()
        response = _make_success_response()

        # First call raises, second succeeds
        mock_publish.side_effect = [RuntimeError("connection reset"), None]

        with (
            patch("ai_module.worker.publisher.settings") as mock_settings,
            patch("ai_module.worker.publisher.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        assert mock_publish.call_count == 2

    async def test_all_attempts_fail_raises_exception(self):
        publisher, _, mock_publish = _make_publisher()
        response = _make_success_response()
        mock_publish.side_effect = RuntimeError("broker down")

        with (
            patch("ai_module.worker.publisher.settings") as mock_settings,
            patch("ai_module.worker.publisher.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            with pytest.raises(RuntimeError, match="broker down"):
                await publisher.publish_success(response)

    async def test_all_attempts_fail_increments_publish_failures(self):
        publisher, _, mock_publish = _make_publisher()
        response = _make_success_response()
        mock_publish.side_effect = RuntimeError("broker down")
        before = metrics.publish_failures

        with (
            patch("ai_module.worker.publisher.settings") as mock_settings,
            patch("ai_module.worker.publisher.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_settings.RABBITMQ_OUTPUT_QUEUE = _OUTPUT_QUEUE
            mock_settings.RABBITMQ_EXCHANGE = _EXCHANGE_NAME
            mock_settings.LOG_LEVEL = "INFO"
            with pytest.raises(RuntimeError):
                await publisher.publish_success(response)

        assert metrics.publish_failures == before + 1
