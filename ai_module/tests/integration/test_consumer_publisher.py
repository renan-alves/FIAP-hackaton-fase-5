"""Integration tests for the consumer → publisher orchestration (FUN-010).

Verifies the end-to-end message handling flow:
  consumer receives message → pipeline runs → publisher is called → ACK/NACK

No live RabbitMQ broker or AI model is required — both the pipeline and the
publisher are mocked.

Test matrix
-----------
+-------------------------------------------+----------+--------------------+
| Scenario                                  | ACK/NACK | Publisher call     |
+===========================================+==========+====================+
| Pipeline success                          | ACK      | publish_success(1) |
| Pipeline AIFailureError                   | ACK      | publish_error(1)   |
| Pipeline AITimeoutError                   | ACK      | publish_error(1)   |
| Pipeline InvalidInputError                | ACK      | publish_error(1)   |
| Pipeline UnsupportedFormatError           | ACK      | publish_error(1)   |
| Malformed JSON body                       | NACK     | neither            |
| Invalid Pydantic schema                   | NACK     | neither            |
+-------------------------------------------+----------+--------------------+
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from ai_module.core.exceptions import (
    AIFailureError,
    AITimeoutError,
    InvalidInputError,
    UnsupportedFormatError,
)
from ai_module.models.report import (
    AnalyzeResponse,
    Component,
    Report,
    ReportMetadata,
)
from ai_module.worker.consumer import MessageConsumer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(body: bytes) -> MagicMock:
    msg = MagicMock()
    msg.body = body
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    return msg


def _valid_b64() -> str:
    return base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()


def _valid_payload(**overrides) -> dict:
    payload = {
        "analysis_id": str(uuid.uuid4()),
        "file_bytes_b64": _valid_b64(),
        "file_name": "diagram.png",
        "context_text": None,
    }
    payload.update(overrides)
    return payload


def _make_pipeline_result(analysis_id: str) -> AnalyzeResponse:
    return AnalyzeResponse(
        analysis_id=analysis_id,
        status="success",
        report=Report(
            summary="Architecture overview with microservices",
            components=[Component(name="API", type="gateway", description="Entry point")],
            risks=[],
            recommendations=[],
        ),
        metadata=ReportMetadata(
            model_used="gpt-4o",
            processing_time_ms=200,
            input_type="image",
        ),
    )


def _make_consumer_with_publisher() -> tuple[MessageConsumer, AsyncMock, AsyncMock]:
    """Return (consumer, mock_publisher, mock_channel_queue)."""
    mock_publish_success = AsyncMock()
    mock_publish_error = AsyncMock()

    mock_publisher = MagicMock()
    mock_publisher.publish_success = mock_publish_success
    mock_publisher.publish_error = mock_publish_error

    adapter = MagicMock()
    channel = AsyncMock()
    queue = AsyncMock()
    queue.consume = AsyncMock(return_value="consumer-tag")
    channel.declare_queue = AsyncMock(return_value=queue)
    adapter.get_channel = AsyncMock(return_value=channel)

    consumer = MessageConsumer(adapter=adapter, publisher=mock_publisher)
    return consumer, mock_publisher, queue


# ---------------------------------------------------------------------------
# Tests — success path
# ---------------------------------------------------------------------------


class TestConsumerPublisherSuccess:
    """Pipeline success → publish_success called, message ACKed."""

    async def test_pipeline_success_calls_publish_success(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        payload = _valid_payload()
        msg = _make_message(json.dumps(payload).encode())
        pipeline_result = _make_pipeline_result(payload["analysis_id"])

        with (
            patch("ai_module.worker.consumer.run_pipeline", return_value=pipeline_result),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        publisher.publish_success.assert_called_once()
        msg.ack.assert_called_once()
        publisher.publish_error.assert_not_called()

    async def test_pipeline_success_passes_correct_analysis_id(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        analysis_id = str(uuid.uuid4())
        payload = _valid_payload(analysis_id=analysis_id)
        msg = _make_message(json.dumps(payload).encode())
        pipeline_result = _make_pipeline_result(analysis_id)

        with (
            patch("ai_module.worker.consumer.run_pipeline", return_value=pipeline_result),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        called_with = publisher.publish_success.call_args[0][0]
        assert called_with.analysis_id == analysis_id

    async def test_pipeline_success_no_nack(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        payload = _valid_payload()
        msg = _make_message(json.dumps(payload).encode())
        pipeline_result = _make_pipeline_result(payload["analysis_id"])

        with (
            patch("ai_module.worker.consumer.run_pipeline", return_value=pipeline_result),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        msg.nack.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — pipeline errors → publish_error, ACK
# ---------------------------------------------------------------------------


class TestConsumerPublisherPipelineErrors:
    """Pipeline errors → publish_error called, message ACKed."""

    async def test_ai_failure_calls_publish_error(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        payload = _valid_payload()
        msg = _make_message(json.dumps(payload).encode())

        with (
            patch("ai_module.worker.consumer.run_pipeline", side_effect=AIFailureError("LLM down")),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        publisher.publish_error.assert_called_once()
        msg.ack.assert_called_once()
        publisher.publish_success.assert_not_called()

    async def test_ai_timeout_calls_publish_error(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        payload = _valid_payload()
        msg = _make_message(json.dumps(payload).encode())

        with (
            patch("ai_module.worker.consumer.run_pipeline", side_effect=AITimeoutError("timeout")),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        publisher.publish_error.assert_called_once()
        msg.ack.assert_called_once()

    async def test_invalid_input_calls_publish_error_with_correct_code(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        payload = _valid_payload()
        msg = _make_message(json.dumps(payload).encode())

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                side_effect=InvalidInputError("bad input"),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        publisher.publish_error.assert_called_once()
        error_arg = publisher.publish_error.call_args[0][0]
        assert error_arg.error_code == "INVALID_INPUT"
        msg.ack.assert_called_once()

    async def test_unsupported_format_calls_publish_error_with_correct_code(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        payload = _valid_payload()
        msg = _make_message(json.dumps(payload).encode())

        with (
            patch(
                "ai_module.worker.consumer.run_pipeline",
                side_effect=UnsupportedFormatError("pdf not supported"),
            ),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        publisher.publish_error.assert_called_once()
        error_arg = publisher.publish_error.call_args[0][0]
        assert error_arg.error_code == "UNSUPPORTED_FORMAT"
        msg.ack.assert_called_once()

    async def test_pipeline_error_includes_analysis_id(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        analysis_id = str(uuid.uuid4())
        payload = _valid_payload(analysis_id=analysis_id)
        msg = _make_message(json.dumps(payload).encode())

        with (
            patch("ai_module.worker.consumer.run_pipeline", side_effect=AIFailureError("LLM down")),
            patch("ai_module.worker.consumer.get_llm_adapter"),
        ):
            await consumer._handle_message(msg)

        error_arg = publisher.publish_error.call_args[0][0]
        assert error_arg.analysis_id == analysis_id


# ---------------------------------------------------------------------------
# Tests — validation failures → NACK, publisher not called
# ---------------------------------------------------------------------------


class TestConsumerPublisherValidationFailures:
    """Malformed or schema-invalid messages → NACK, publisher not called."""

    async def test_malformed_json_does_not_call_publisher(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        msg = _make_message(b"not valid json {{{")

        await consumer._handle_message(msg)

        publisher.publish_success.assert_not_called()
        publisher.publish_error.assert_not_called()
        msg.nack.assert_called_once()

    async def test_malformed_json_nack_no_requeue(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        msg = _make_message(b"not valid json {{{")

        await consumer._handle_message(msg)

        _, kwargs = msg.nack.call_args
        assert kwargs.get("requeue") is False

    async def test_schema_validation_failure_does_not_call_publisher(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        # analysis_id is required; omit it to trigger Pydantic error
        incomplete_payload = {
            "file_bytes_b64": _valid_b64(),
            "file_name": "diagram.png",
        }
        msg = _make_message(json.dumps(incomplete_payload).encode())

        await consumer._handle_message(msg)

        publisher.publish_success.assert_not_called()
        publisher.publish_error.assert_not_called()
        msg.nack.assert_called_once()

    async def test_schema_validation_failure_nack_no_requeue(self):
        consumer, publisher, _ = _make_consumer_with_publisher()
        msg = _make_message(json.dumps({"file_name": "x.png"}).encode())

        await consumer._handle_message(msg)

        _, kwargs = msg.nack.call_args
        assert kwargs.get("requeue") is False
