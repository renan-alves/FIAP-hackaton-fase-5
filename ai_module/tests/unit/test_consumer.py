"""Unit tests for MessageConsumer.

All external dependencies (aio-pika, run_pipeline, get_llm_adapter, publisher)
are mocked — no RabbitMQ server or LLM credentials required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_module.core.metrics import metrics
from ai_module.models.queue import QueueErrorResponse
from ai_module.models.report import (
    AnalyzeResponse,
    Component,
    ComponentType,
    Report,
    ReportMetadata,
)
from ai_module.worker.consumer import MessageConsumer, ResultPublisher

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_B64 = "ZmFrZS1maWxlLWJ5dGVz"  # base64("fake-file-bytes")

_VALID_PAYLOAD: dict = {
    "analysis_id": "abc-123",
    "file_bytes_b64": _VALID_B64,
    "file_name": "diagram.png",
    "context_text": None,
}


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_message(body: bytes) -> MagicMock:
    """Return a mock IncomingMessage with the given raw body."""
    message = MagicMock()
    message.body = body
    message.ack = AsyncMock()
    message.nack = AsyncMock()
    return message


def _make_valid_message() -> MagicMock:
    return _make_message(json.dumps(_VALID_PAYLOAD).encode())


def _make_analyze_response(analysis_id: str = "abc-123") -> AnalyzeResponse:
    return AnalyzeResponse(
        analysis_id=analysis_id,
        status="success",
        report=Report(
            summary="Architecture summary for testing",
            components=[
                Component(
                    name="ServiceA",
                    type=ComponentType.SERVICE,
                    description="A microservice",
                )
            ],
        ),
        metadata=ReportMetadata(
            model_used="test-model",
            processing_time_ms=100,
            input_type="image",
        ),
    )


def _make_mock_publisher() -> MagicMock:
    publisher = MagicMock()
    publisher.publish_success = AsyncMock()
    publisher.publish_error = AsyncMock()
    return publisher


def _make_mock_adapter() -> MagicMock:
    """Return a mock RabbitMQAdapter with channel, exchange, and queue pre-configured."""
    adapter = MagicMock()
    channel = AsyncMock()
    queue = AsyncMock()
    queue.consume = AsyncMock(return_value="test-consumer-tag")
    queue.bind = AsyncMock()
    exchange = AsyncMock()
    channel.declare_queue = AsyncMock(return_value=queue)
    channel.declare_exchange = AsyncMock(return_value=exchange)
    adapter.get_channel = AsyncMock(return_value=channel)
    return adapter, channel, queue


# ---------------------------------------------------------------------------
# ResultPublisher protocol check
# ---------------------------------------------------------------------------


class TestResultPublisherProtocol:
    def test_publisher_satisfies_protocol(self) -> None:
        """MagicMock with required methods satisfies ResultPublisher Protocol."""
        publisher = _make_mock_publisher()
        assert isinstance(publisher, ResultPublisher)


# ---------------------------------------------------------------------------
# MessageConsumer.start()
# ---------------------------------------------------------------------------


class TestMessageConsumerStart:
    @pytest.mark.asyncio
    async def test_start_declares_durable_queue(self) -> None:
        """start() declares the configured input queue as durable."""
        adapter, channel, queue = _make_mock_adapter()
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()

        channel.declare_queue.assert_awaited_once_with(
            "analysis.requests", durable=True
        )

    @pytest.mark.asyncio
    async def test_start_declares_direct_exchange(self) -> None:
        """start() declares a durable direct exchange — matches topology spec (T014)."""
        import aio_pika

        adapter, channel, queue = _make_mock_adapter()
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()

        channel.declare_exchange.assert_awaited_once_with(
            "analysis",
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

    @pytest.mark.asyncio
    async def test_start_binds_queue_to_exchange(self) -> None:
        """start() binds the input queue to the exchange using the queue name as routing key."""
        adapter, channel, queue = _make_mock_adapter()
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()

        queue.bind.assert_awaited_once_with(
            channel.declare_exchange.return_value,
            routing_key="analysis.requests",
        )

    @pytest.mark.asyncio
    async def test_start_registers_callback(self) -> None:
        """start() registers _handle_message as the consumer callback."""
        adapter, channel, queue = _make_mock_adapter()
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()

        queue.consume.assert_awaited_once_with(consumer._handle_message)

    @pytest.mark.asyncio
    async def test_start_stores_consumer_tag(self) -> None:
        """start() stores the consumer tag returned by queue.consume()."""
        adapter, _, queue = _make_mock_adapter()
        queue.consume.return_value = "my-ctag"
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()

        assert consumer._consumer_tag == "my-ctag"


# ---------------------------------------------------------------------------
# MessageConsumer.stop()
# ---------------------------------------------------------------------------


class TestMessageConsumerStop:
    @pytest.mark.asyncio
    async def test_stop_cancels_consumer(self) -> None:
        """stop() cancels the registered consumer via queue.cancel()."""
        adapter, _, queue = _make_mock_adapter()
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()
            await consumer.stop()

        queue.cancel.assert_awaited_once_with("test-consumer-tag")

    @pytest.mark.asyncio
    async def test_stop_clears_state(self) -> None:
        """stop() sets internal state to None."""
        adapter, _, _ = _make_mock_adapter()
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()
            await consumer.stop()

        assert consumer._consumer_tag is None
        assert consumer._queue is None
        assert consumer._channel is None

    @pytest.mark.asyncio
    async def test_stop_without_start_does_not_raise(self) -> None:
        """stop() is safe to call before start()."""
        adapter, _, _ = _make_mock_adapter()
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())
        await consumer.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_stop_tolerates_cancel_error(self) -> None:
        """stop() swallows exceptions from queue.cancel() and clears state."""
        adapter, _, queue = _make_mock_adapter()
        queue.cancel = AsyncMock(side_effect=RuntimeError("broker gone"))
        consumer = MessageConsumer(adapter=adapter, publisher=_make_mock_publisher())

        with patch("ai_module.worker.consumer.settings") as mock_settings:
            mock_settings.RABBITMQ_INPUT_QUEUE = "analysis.requests"
            mock_settings.RABBITMQ_EXCHANGE = "analysis"
            mock_settings.LOG_LEVEL = "INFO"
            await consumer.start()
            await consumer.stop()  # should not raise

        assert consumer._consumer_tag is None


# ---------------------------------------------------------------------------
# Happy path: valid message → pipeline succeeds
# ---------------------------------------------------------------------------


class TestHandleMessageSuccess:
    @pytest.mark.asyncio
    async def test_valid_message_calls_run_pipeline(self) -> None:
        """A valid message results in run_pipeline being called with decoded fields."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()
        mock_result = _make_analyze_response("abc-123")

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_pipeline,
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        mock_pipeline.assert_awaited_once()
        call_kwargs = mock_pipeline.call_args.kwargs
        assert call_kwargs["analysis_id"] == "abc-123"
        assert call_kwargs["filename"] == "diagram.png"
        assert call_kwargs["file_bytes"] == b"fake-file-bytes"

    @pytest.mark.asyncio
    async def test_valid_message_publishes_success_response(self) -> None:
        """A successful pipeline run publishes a QueueAnalysisResponse."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()
        mock_result = _make_analyze_response("abc-123")

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        publisher.publish_success.assert_awaited_once()
        published = publisher.publish_success.call_args.args[0]
        assert published.analysis_id == "abc-123"
        assert published.status == "success"
        assert published.report == mock_result.report

    @pytest.mark.asyncio
    async def test_valid_message_acks(self) -> None:
        """A successful pipeline run ACKs the message."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                return_value=_make_analyze_response(),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        message.ack.assert_awaited_once()
        message.nack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_valid_message_increments_messages_consumed(self) -> None:
        """A successfully parsed message increments metrics.messages_consumed."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()
        original_count = metrics.messages_consumed

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                return_value=_make_analyze_response(),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        assert metrics.messages_consumed == original_count + 1


# ---------------------------------------------------------------------------
# Malformed JSON
# ---------------------------------------------------------------------------


class TestHandleMessageMalformedJson:
    @pytest.mark.asyncio
    async def test_invalid_json_nacks(self) -> None:
        """A message with invalid JSON is NACKed without requeue."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_message(b"not valid json {{{")

        await consumer._handle_message(message)

        message.nack.assert_awaited_once_with(requeue=False)
        message.ack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_json_does_not_call_pipeline(self) -> None:
        """A malformed message must not reach the pipeline."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_message(b"not valid json {{{")

        with patch(
            "ai_module.worker.consumer.run_pipeline", new_callable=AsyncMock
        ) as mock_pipeline:
            await consumer._handle_message(message)

        mock_pipeline.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_json_increments_validation_errors(self) -> None:
        """Malformed JSON increments metrics.validation_errors."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_message(b"not valid json {{{")
        before = metrics.validation_errors

        await consumer._handle_message(message)

        assert metrics.validation_errors == before + 1

    @pytest.mark.asyncio
    async def test_invalid_utf8_nacks(self) -> None:
        """A message with non-UTF-8 bytes is also NACKed."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_message(bytes([0xFF, 0xFE, 0x00]))

        await consumer._handle_message(message)

        message.nack.assert_awaited_once_with(requeue=False)


# ---------------------------------------------------------------------------
# Schema validation failure
# ---------------------------------------------------------------------------


class TestHandleMessageSchemaInvalid:
    @pytest.mark.asyncio
    async def test_missing_required_field_nacks(self) -> None:
        """A JSON payload missing required fields is NACKed."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        incomplete = {"analysis_id": "x"}  # missing file_bytes_b64 and file_name
        message = _make_message(json.dumps(incomplete).encode())

        await consumer._handle_message(message)

        message.nack.assert_awaited_once_with(requeue=False)
        message.ack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_schema_error_increments_validation_errors(self) -> None:
        """Schema validation failure increments metrics.validation_errors."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        incomplete = {"analysis_id": "x"}
        message = _make_message(json.dumps(incomplete).encode())
        before = metrics.validation_errors

        await consumer._handle_message(message)

        assert metrics.validation_errors == before + 1


# ---------------------------------------------------------------------------
# Base64 decode failure
# ---------------------------------------------------------------------------


class TestHandleMessageBase64Error:
    @pytest.mark.asyncio
    async def test_invalid_base64_nacks(self) -> None:
        """A message with invalid base-64 bytes is NACKed."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        bad_b64_payload = {
            "analysis_id": "abc-123",
            "file_bytes_b64": "!!!not-base64!!!",
            "file_name": "diagram.png",
        }
        message = _make_message(json.dumps(bad_b64_payload).encode())

        await consumer._handle_message(message)

        message.nack.assert_awaited_once_with(requeue=False)
        message.ack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_base64_increments_validation_errors(self) -> None:
        """Invalid base-64 increments metrics.validation_errors."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        bad_b64_payload = {
            "analysis_id": "abc-123",
            "file_bytes_b64": "!!!not-base64!!!",
            "file_name": "diagram.png",
        }
        message = _make_message(json.dumps(bad_b64_payload).encode())
        before = metrics.validation_errors

        await consumer._handle_message(message)

        assert metrics.validation_errors == before + 1

    @pytest.mark.asyncio
    async def test_invalid_base64_does_not_call_pipeline(self) -> None:
        """Invalid base-64 must not reach the pipeline."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        bad_b64_payload = {
            "analysis_id": "abc-123",
            "file_bytes_b64": "!!!not-base64!!!",
            "file_name": "diagram.png",
        }
        message = _make_message(json.dumps(bad_b64_payload).encode())

        with patch(
            "ai_module.worker.consumer.run_pipeline", new_callable=AsyncMock
        ) as mock_pipeline:
            await consumer._handle_message(message)

        mock_pipeline.assert_not_awaited()


# ---------------------------------------------------------------------------
# Pipeline error
# ---------------------------------------------------------------------------


class TestHandleMessagePipelineError:
    @pytest.mark.asyncio
    async def test_pipeline_exception_publishes_error_response(self) -> None:
        """A pipeline exception publishes a QueueErrorResponse with PIPELINE_ERROR."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                side_effect=RuntimeError("AI service unavailable"),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        publisher.publish_error.assert_awaited_once()
        error: QueueErrorResponse = publisher.publish_error.call_args.args[0]
        assert error.analysis_id == "abc-123"
        assert error.status == "error"
        assert error.error_code == "INTERNAL_ERROR"
        assert "AI service unavailable" in error.message

    @pytest.mark.asyncio
    async def test_pipeline_exception_acks_message(self) -> None:
        """A pipeline error ACKs the message — avoids infinite redelivery."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        message.ack.assert_awaited_once()
        message.nack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_exception_increments_pipeline_errors(self) -> None:
        """A pipeline exception increments metrics.pipeline_errors."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()
        before = metrics.pipeline_errors

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        assert metrics.pipeline_errors == before + 1

    @pytest.mark.asyncio
    async def test_pipeline_exception_does_not_call_publish_success(self) -> None:
        """A pipeline exception must not publish a success response."""
        publisher = _make_mock_publisher()
        consumer = MessageConsumer(
            adapter=_make_mock_adapter()[0], publisher=publisher
        )
        message = _make_valid_message()

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()),
        ):
            await consumer._handle_message(message)

        publisher.publish_success.assert_not_awaited()
