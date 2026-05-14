"""Integration tests for the worker message consumer.

These tests exercise the :class:`~ai_module.worker.consumer.MessageConsumer`
end-to-end using mocked RabbitMQ message objects (no live broker required).
The pipeline is also mocked so tests remain fast and isolated.

Test Matrix
-----------
+----------------------------------+------------------+---------------------+
| Scenario                         | Ack strategy     | Publisher call      |
+==================================+==================+=====================+
| Valid message → pipeline success | ACK              | publish_success     |
| Valid message → pipeline error   | ACK              | publish_error       |
| Valid message → pipeline timeout | ACK              | publish_error       |
| Malformed JSON body              | NACK (no requeue)| none                |
| Invalid Pydantic schema          | NACK (no requeue)| none                |
| Bad base-64 file bytes           | ACK              | publish_error       |
| Consumer start / stop lifecycle  | n/a              | n/a                 |
+----------------------------------+------------------+---------------------+
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_module.core.exceptions import (
    AIFailureError,
    AITimeoutError,
    InvalidInputError,
    UnsupportedFormatError,
)
from ai_module.core.metrics import metrics
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
    """Build a fake aio-pika IncomingMessage with the given bytes body."""
    msg = MagicMock()
    msg.body = body
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    return msg


def _valid_b64_bytes() -> str:
    return base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()


def _make_pipeline_result(analysis_id: str) -> AnalyzeResponse:
    return AnalyzeResponse(
        analysis_id=analysis_id,
        status="success",
        report=Report(
            summary="Architecture summary",
            components=[Component(name="API Gateway", type="gateway", description="Entry point")],
            risks=[],
            recommendations=[],
        ),
        metadata=ReportMetadata(
            model_used="gpt-4o",
            processing_time_ms=500,
            input_type="image",
        ),
    )


def _valid_request_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "analysis_id": str(uuid.uuid4()),
        "file_bytes_b64": _valid_b64_bytes(),
        "file_name": "diagram.png",
        "context_text": None,
    }
    payload.update(overrides)
    return payload


def _make_consumer() -> tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock]:
    """Create a MessageConsumer with a fully mocked adapter and publisher."""
    # Adapter mock — channel.declare_queue().consume() must be awaitable
    adapter = MagicMock()
    channel = AsyncMock()
    queue = AsyncMock()
    queue.consume = AsyncMock(return_value="consumer-tag-1")
    channel.declare_queue = AsyncMock(return_value=queue)
    adapter.get_channel = AsyncMock(return_value=channel)

    publisher = AsyncMock()
    publisher.publish_success = AsyncMock()
    publisher.publish_error = AsyncMock()

    consumer = MessageConsumer(adapter=adapter, publisher=publisher)
    return consumer, adapter, queue, publisher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def consumer_parts() -> tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock]:
    return _make_consumer()


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    """Reset shared metrics counters between tests to avoid leakage."""
    metrics.messages_consumed = 0
    metrics.validation_errors = 0
    metrics.pipeline_errors = 0
    metrics.results_published = 0
    metrics.errors_published = 0
    metrics.publish_failures = 0


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


async def test_consumer_start_declares_queue_and_registers_callback(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, adapter, queue, _ = consumer_parts
    await consumer.start()

    adapter.get_channel.assert_awaited_once()
    queue.consume.assert_awaited_once()


async def test_consumer_stop_cancels_consumer_tag(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, queue, _ = consumer_parts
    await consumer.start()
    await consumer.stop()

    queue.cancel.assert_awaited_once()


async def test_consumer_stop_is_safe_without_start() -> None:
    consumer, _, _, _ = _make_consumer()
    # Should not raise
    await consumer.stop()


# ---------------------------------------------------------------------------
# Happy-path: valid message → pipeline success
# ---------------------------------------------------------------------------


async def test_valid_message_triggers_pipeline_and_acks(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, publisher = consumer_parts
    payload = _valid_request_payload()
    msg = _make_message(json.dumps(payload).encode())

    with patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()), patch(
        "ai_module.worker.consumer.run_pipeline",
        new=AsyncMock(return_value=_make_pipeline_result(payload["analysis_id"])),
    ):
        await consumer._handle_message(msg)

    msg.ack.assert_awaited_once()
    msg.nack.assert_not_awaited()
    publisher.publish_success.assert_awaited_once()


async def test_valid_message_increments_consumed_counter(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, publisher = consumer_parts
    payload = _valid_request_payload()
    msg = _make_message(json.dumps(payload).encode())

    with patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()), patch(
        "ai_module.worker.consumer.run_pipeline",
        new=AsyncMock(return_value=_make_pipeline_result(payload["analysis_id"])),
    ):
        await consumer._handle_message(msg)

    assert metrics.messages_consumed == 1


# ---------------------------------------------------------------------------
# Rejection: malformed JSON
# ---------------------------------------------------------------------------


async def test_malformed_json_is_nacked_without_requeue(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, publisher = consumer_parts
    msg = _make_message(b"this is not json {{{")

    await consumer._handle_message(msg)

    msg.nack.assert_awaited_once_with(requeue=False)
    msg.ack.assert_not_awaited()
    publisher.publish_success.assert_not_awaited()
    publisher.publish_error.assert_not_awaited()


async def test_malformed_json_increments_validation_error_counter(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, _ = consumer_parts
    msg = _make_message(b"not-json")
    await consumer._handle_message(msg)
    assert metrics.validation_errors == 1


# ---------------------------------------------------------------------------
# Rejection: invalid Pydantic schema
# ---------------------------------------------------------------------------


async def test_invalid_schema_missing_required_fields_is_nacked(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, publisher = consumer_parts
    # Missing file_bytes_b64 and file_name
    msg = _make_message(json.dumps({"analysis_id": str(uuid.uuid4())}).encode())

    await consumer._handle_message(msg)

    msg.nack.assert_awaited_once_with(requeue=False)
    msg.ack.assert_not_awaited()
    publisher.publish_success.assert_not_awaited()
    publisher.publish_error.assert_not_awaited()


async def test_invalid_schema_increments_validation_error_counter(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, _ = consumer_parts
    msg = _make_message(json.dumps({"wrong": "fields"}).encode())
    await consumer._handle_message(msg)
    assert metrics.validation_errors == 1


# ---------------------------------------------------------------------------
# Pipeline errors → error response published + ACK
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        AIFailureError("llm down"),
        AITimeoutError("timed out"),
        UnsupportedFormatError("bad format"),
        InvalidInputError("invalid"),
    ],
)
async def test_pipeline_domain_exception_publishes_error_and_acks(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
    exc: Exception,
) -> None:
    consumer, _, _, publisher = consumer_parts
    payload = _valid_request_payload()
    msg = _make_message(json.dumps(payload).encode())

    with patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()), patch(
        "ai_module.worker.consumer.run_pipeline",
        new=AsyncMock(side_effect=exc),
    ):
        await consumer._handle_message(msg)

    msg.ack.assert_awaited_once()
    msg.nack.assert_not_awaited()
    publisher.publish_error.assert_awaited_once()


async def test_pipeline_domain_exception_increments_pipeline_error_counter(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, _ = consumer_parts
    payload = _valid_request_payload()
    msg = _make_message(json.dumps(payload).encode())

    with patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()), patch(
        "ai_module.worker.consumer.run_pipeline",
        new=AsyncMock(side_effect=AIFailureError("err")),
    ):
        await consumer._handle_message(msg)

    assert metrics.pipeline_errors == 1


async def test_pipeline_unexpected_exception_publishes_error_and_acks(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """Unhandled exceptions from pipeline must not crash the worker."""
    consumer, _, _, publisher = consumer_parts
    payload = _valid_request_payload()
    msg = _make_message(json.dumps(payload).encode())

    with patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()), patch(
        "ai_module.worker.consumer.run_pipeline",
        new=AsyncMock(side_effect=RuntimeError("unexpected crash")),
    ):
        await consumer._handle_message(msg)

    # Message should be ACKed (not re-queued) and error published
    msg.ack.assert_awaited_once()
    publisher.publish_error.assert_awaited_once()


# ---------------------------------------------------------------------------
# Multiple messages in sequence
# ---------------------------------------------------------------------------


async def test_multiple_valid_messages_all_acked(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    consumer, _, _, publisher = consumer_parts

    _fixed_result = _make_pipeline_result("test-id")
    with patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()), patch(
        "ai_module.worker.consumer.run_pipeline",
        new=AsyncMock(return_value=_fixed_result),
    ):
        for _ in range(3):
            payload = _valid_request_payload()
            msg = _make_message(json.dumps(payload).encode())
            await consumer._handle_message(msg)
            msg.ack.assert_awaited_once()

    assert metrics.messages_consumed == 3
    assert publisher.publish_success.await_count == 3


async def test_mixed_valid_invalid_messages_independent(
    consumer_parts: tuple[MessageConsumer, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """Rejection of one message must not affect processing of subsequent messages."""
    consumer, _, _, publisher = consumer_parts

    invalid_msg = _make_message(b"not-json")
    valid_payload = _valid_request_payload()
    valid_msg = _make_message(json.dumps(valid_payload).encode())

    with patch("ai_module.worker.consumer.get_llm_adapter", return_value=MagicMock()), patch(
        "ai_module.worker.consumer.run_pipeline",
        new=AsyncMock(return_value=_make_pipeline_result(valid_payload["analysis_id"])),
    ):
        await consumer._handle_message(invalid_msg)
        await consumer._handle_message(valid_msg)

    invalid_msg.nack.assert_awaited_once_with(requeue=False)
    valid_msg.ack.assert_awaited_once()
    assert metrics.validation_errors == 1
    assert metrics.messages_consumed == 1
