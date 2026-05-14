"""Integration tests verifying the shared RabbitMQAdapter instance (FUN-010).

These tests confirm that a single :class:`~ai_module.adapters.rabbitmq_adapter.RabbitMQAdapter`
instance is shared between the consumer and the publisher — which is the
architecture mandated by ``main.py`` lifespan:

    adapter = RabbitMQAdapter()
    publisher = RabbitMQResultPublisher(adapter)
    consumer  = MessageConsumer(adapter=adapter, publisher=publisher)

Sharing one adapter avoids redundant connection overhead and ensures both
components use the same underlying aio-pika ``Connection``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from ai_module.adapters.rabbitmq_adapter import RabbitMQAdapter
from ai_module.worker.consumer import MessageConsumer
from ai_module.worker.publisher import RabbitMQResultPublisher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter_and_components(
) -> tuple[RabbitMQAdapter, MessageConsumer, RabbitMQResultPublisher]:
    """Build consumer and publisher backed by the *same* adapter mock."""
    adapter = MagicMock(spec=RabbitMQAdapter)

    mock_publish = AsyncMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = mock_publish
    mock_channel = MagicMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    queue = AsyncMock()
    queue.consume = AsyncMock(return_value="consumer-tag")
    mock_channel.declare_queue = AsyncMock(return_value=queue)

    adapter.get_channel = AsyncMock(return_value=mock_channel)

    publisher = RabbitMQResultPublisher(adapter=adapter)

    mock_pub = MagicMock()
    mock_pub.publish_success = AsyncMock()
    mock_pub.publish_error = AsyncMock()

    consumer = MessageConsumer(adapter=adapter, publisher=mock_pub)

    return adapter, consumer, publisher


# ---------------------------------------------------------------------------
# Tests — same adapter instance
# ---------------------------------------------------------------------------


class TestSharedAdapterIdentity:
    """Verify consumer and publisher reference the same adapter object."""

    def test_consumer_and_publisher_share_same_adapter_instance(self):
        adapter = MagicMock(spec=RabbitMQAdapter)

        publisher = RabbitMQResultPublisher(adapter=adapter)
        mock_pub = MagicMock()
        consumer = MessageConsumer(adapter=adapter, publisher=mock_pub)

        assert consumer._adapter is adapter
        assert publisher._adapter is adapter

    def test_consumer_and_publisher_share_same_adapter_by_id(self):
        adapter = MagicMock(spec=RabbitMQAdapter)

        publisher = RabbitMQResultPublisher(adapter=adapter)
        mock_pub = MagicMock()
        consumer = MessageConsumer(adapter=adapter, publisher=mock_pub)

        assert id(consumer._adapter) == id(publisher._adapter)

    def test_different_adapters_are_not_the_same(self):
        adapter1 = MagicMock(spec=RabbitMQAdapter)
        adapter2 = MagicMock(spec=RabbitMQAdapter)

        publisher = RabbitMQResultPublisher(adapter=adapter1)
        mock_pub = MagicMock()
        consumer = MessageConsumer(adapter=adapter2, publisher=mock_pub)

        assert consumer._adapter is not publisher._adapter


# ---------------------------------------------------------------------------
# Tests — publisher calls adapter.get_channel
# ---------------------------------------------------------------------------


class TestPublisherUsesAdapterGetChannel:
    """Publisher must call adapter.get_channel() on each publish attempt."""

    async def test_publisher_calls_adapter_get_channel_on_success_publish(self):
        adapter, _, publisher = _make_adapter_and_components()

        from ai_module.models.queue import QueueAnalysisResponse
        from ai_module.models.report import Component, Report, ReportMetadata

        response = QueueAnalysisResponse(
            analysis_id=str(uuid.uuid4()),
            status="success",
            report=Report(
                summary="Architecture overview",
                components=[Component(name="API", type="gateway", description="Entry")],
                risks=[],
                recommendations=[],
            ),
            metadata=ReportMetadata(
                model_used="gpt-4o",
                processing_time_ms=100,
                input_type="image",
            ),
        )

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = "analysis.results"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_success(response)

        adapter.get_channel.assert_called()

    async def test_publisher_calls_adapter_get_channel_on_error_publish(self):
        adapter, _, publisher = _make_adapter_and_components()

        from ai_module.models.queue import QueueErrorResponse

        error = QueueErrorResponse(
            analysis_id=str(uuid.uuid4()),
            status="error",
            error_code="AI_FAILURE",
            message="Analysis failed",
        )

        with patch("ai_module.worker.publisher.settings") as mock_settings:
            mock_settings.RABBITMQ_OUTPUT_QUEUE = "analysis.results"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await publisher.publish_error(error)

        adapter.get_channel.assert_called()


# ---------------------------------------------------------------------------
# Tests — consumer uses adapter on start
# ---------------------------------------------------------------------------


class TestConsumerUsesAdapterOnStart:
    """Consumer must call adapter.get_channel() to declare and consume the queue."""

    async def test_consumer_start_calls_adapter_get_channel(self):
        adapter = MagicMock(spec=RabbitMQAdapter)

        mock_channel = AsyncMock()
        queue = AsyncMock()
        queue.consume = AsyncMock(return_value="consumer-tag")
        mock_channel.declare_queue = AsyncMock(return_value=queue)
        adapter.get_channel = AsyncMock(return_value=mock_channel)

        mock_pub = MagicMock()
        mock_pub.publish_success = AsyncMock()
        mock_pub.publish_error = AsyncMock()

        consumer = MessageConsumer(adapter=adapter, publisher=mock_pub)

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()

        adapter.get_channel.assert_called()

    async def test_consumer_stop_cancels_consumer_tag(self):
        adapter = MagicMock(spec=RabbitMQAdapter)

        mock_channel = AsyncMock()
        queue = AsyncMock()
        queue.consume = AsyncMock(return_value="consumer-tag")
        mock_channel.declare_queue = AsyncMock(return_value=queue)
        adapter.get_channel = AsyncMock(return_value=mock_channel)

        mock_pub = MagicMock()
        mock_pub.publish_success = AsyncMock()
        mock_pub.publish_error = AsyncMock()

        consumer = MessageConsumer(adapter=adapter, publisher=mock_pub)

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()

        await consumer.stop()
