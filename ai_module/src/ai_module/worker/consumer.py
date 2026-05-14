"""Message consumer for the RabbitMQ analysis request queue.

Reads serialised :class:`~ai_module.models.queue.QueueAnalysisRequest` messages,
runs them through the analysis pipeline, and publishes a success or error
response via the injected :class:`ResultPublisher`.

Message acknowledgement strategy
----------------------------------
* **Validation error** (malformed JSON, schema mismatch, bad base-64):
  NACK without requeue → message flows to the DLQ.  Avoids poison-pill loops.
* **Pipeline error** (AI failure, timeout, unsupported format):
  publish :class:`~ai_module.models.queue.QueueErrorResponse`, then ACK.
  The error is surfaced to the caller via the output queue; re-delivery
  would only produce the same failure.
* **Success**: publish :class:`~ai_module.models.queue.QueueAnalysisResponse`,
  then ACK.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import ValidationError

from ai_module.adapters.factory import get_llm_adapter
from ai_module.adapters.rabbitmq_adapter import RabbitMQAdapter
from ai_module.core.exceptions import (
    ERR_AI_FAILURE,
    ERR_AI_TIMEOUT,
    ERR_INTERNAL_ERROR,
    ERR_INVALID_INPUT,
    ERR_UNSUPPORTED_FORMAT,
    AIFailureError,
    AITimeoutError,
    InvalidInputError,
    LLMCallError,
    LLMTimeoutError,
    UnsupportedFormatError,
)
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics
from ai_module.core.pipeline import run_pipeline
from ai_module.core.settings import settings
from ai_module.models.queue import (
    QueueAnalysisRequest,
    QueueAnalysisResponse,
    QueueErrorResponse,
)

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue

logger = get_logger(__name__, level=settings.LOG_LEVEL)


@runtime_checkable
class ResultPublisher(Protocol):
    """Interface for publishing analysis results to the output queue."""

    async def publish_success(self, response: QueueAnalysisResponse) -> None: ...

    async def publish_error(self, error: QueueErrorResponse) -> None: ...


class MessageConsumer:
    """Consumes analysis request messages from the RabbitMQ input queue.

    Parameters
    ----------
    adapter:
        Connected :class:`~ai_module.adapters.rabbitmq_adapter.RabbitMQAdapter`
        used to obtain a channel.
    publisher:
        An object implementing :class:`ResultPublisher` that routes results to
        the output queue.

    Usage::

        consumer = MessageConsumer(adapter=rabbitmq_adapter, publisher=publisher)
        await consumer.start()
        # ... running in background via asyncio lifespan
        await consumer.stop()
    """

    def __init__(self, adapter: RabbitMQAdapter, publisher: ResultPublisher) -> None:
        self._adapter = adapter
        self._publisher = publisher
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._consumer_tag: str | None = None

    async def start(self) -> None:
        """Declare the exchange, bind the input queue, and begin consuming messages."""
        import aio_pika

        self._channel = await self._adapter.get_channel()
        # Declare the direct exchange so the topology matches the publisher.
        exchange = await self._channel.declare_exchange(
            settings.RABBITMQ_EXCHANGE,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        self._queue = await self._channel.declare_queue(
            settings.RABBITMQ_INPUT_QUEUE,
            durable=True,
        )
        # Bind the queue to the exchange using the queue name as routing key.
        await self._queue.bind(exchange, routing_key=settings.RABBITMQ_INPUT_QUEUE)
        self._consumer_tag = await self._queue.consume(self._handle_message)
        logger.info(
            "Consumer started",
            extra={
                "event": "consumer_started",
                "exchange": settings.RABBITMQ_EXCHANGE,
                "queue": settings.RABBITMQ_INPUT_QUEUE,
            },
        )

    async def stop(self) -> None:
        """Cancel the consumer and release channel resources."""
        if self._queue is not None and self._consumer_tag is not None:
            try:
                await self._queue.cancel(self._consumer_tag)
            except Exception:
                pass
        self._consumer_tag = None
        self._queue = None
        self._channel = None
        logger.info(
            "Consumer stopped",
            extra={"event": "consumer_stopped"},
        )

    async def _handle_message(self, message: AbstractIncomingMessage) -> None:
        """Process one message from the input queue.

        All ack/nack decisions are explicit — no context-manager magic — so the
        control flow is easy to follow and test.
        """
        analysis_id = "unknown"

        # ------------------------------------------------------------------ #
        # Step 1 — decode and parse JSON body                                  #
        # ------------------------------------------------------------------ #
        try:
            body = json.loads(message.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(
                "Malformed JSON in message body",
                extra={"event": "message_malformed_json", "error": str(exc)},
            )
            metrics.validation_errors += 1
            await message.nack(requeue=False)
            return

        # ------------------------------------------------------------------ #
        # Step 2 — validate message schema                                     #
        # ------------------------------------------------------------------ #
        try:
            request = QueueAnalysisRequest.model_validate(body)
        except ValidationError as exc:
            logger.warning(
                "Message schema validation failed",
                extra={
                    "event": "message_schema_invalid",
                    "errors": exc.error_count(),
                },
            )
            metrics.validation_errors += 1
            await message.nack(requeue=False)
            return

        analysis_id = request.analysis_id
        logger.info(
            "Message received",
            extra={
                "event": "message_received",
                "analysis_id": analysis_id,
                "file_name": request.file_name,
            },
        )

        # ------------------------------------------------------------------ #
        # Step 3 — decode base-64 file bytes                                   #
        # ------------------------------------------------------------------ #
        try:
            file_bytes = request.decode_file_bytes()
        except ValueError as exc:
            logger.warning(
                "Base64 decode failed",
                extra={
                    "event": "message_decode_error",
                    "analysis_id": analysis_id,
                    "error": str(exc),
                },
            )
            metrics.validation_errors += 1
            await message.nack(requeue=False)
            return

        metrics.messages_consumed += 1

        # ------------------------------------------------------------------ #
        # Step 4 — run analysis pipeline                                       #
        # ------------------------------------------------------------------ #
        logger.info(
            "Pipeline starting",
            extra={"event": "pipeline_start", "analysis_id": analysis_id},
        )
        try:
            llm_adapter = get_llm_adapter()
            result = await run_pipeline(
                file_bytes=file_bytes,
                filename=request.file_name,
                analysis_id=analysis_id,
                adapter=llm_adapter,
                context_text=request.context_text,
            )
        except (InvalidInputError, UnsupportedFormatError) as exc:
            _error_code = (
                ERR_INVALID_INPUT if isinstance(exc, InvalidInputError) else ERR_UNSUPPORTED_FORMAT
            )
            logger.warning(
                "Pipeline rejected input",
                extra={"event": "pipeline_error", "analysis_id": analysis_id, "error": str(exc)},
            )
            metrics.pipeline_errors += 1
            await self._publisher.publish_error(
                QueueErrorResponse(
                    analysis_id=analysis_id, error_code=_error_code, message=str(exc)
                )
            )
            await message.ack()
            return
        except (AITimeoutError, LLMTimeoutError) as exc:
            logger.error(
                "Pipeline timed out",
                extra={"event": "pipeline_error", "analysis_id": analysis_id, "error": str(exc)},
            )
            metrics.pipeline_errors += 1
            await self._publisher.publish_error(
                QueueErrorResponse(
                    analysis_id=analysis_id,
                    error_code=ERR_AI_TIMEOUT,
                    message=str(exc),
                )
            )
            await message.ack()
            return
        except (AIFailureError, LLMCallError) as exc:
            logger.error(
                "AI service failure",
                extra={"event": "pipeline_error", "analysis_id": analysis_id, "error": str(exc)},
            )
            metrics.pipeline_errors += 1
            await self._publisher.publish_error(
                QueueErrorResponse(
                    analysis_id=analysis_id, error_code=ERR_AI_FAILURE, message=str(exc)
                )
            )
            await message.ack()
            return
        except Exception as exc:
            logger.error(
                "Pipeline execution failed",
                extra={
                    "event": "pipeline_error",
                    "analysis_id": analysis_id,
                    "error": str(exc),
                },
            )
            metrics.pipeline_errors += 1
            error_response = QueueErrorResponse(
                analysis_id=analysis_id,
                status="error",
                error_code=ERR_INTERNAL_ERROR,
                message=str(exc),
            )
            await self._publisher.publish_error(error_response)
            await message.ack()
            return

        # ------------------------------------------------------------------ #
        # Step 5 — publish success result and ACK                              #
        # ------------------------------------------------------------------ #
        response = QueueAnalysisResponse(
            analysis_id=analysis_id,
            status="success",
            report=result.report,
            metadata=result.metadata,
        )
        await self._publisher.publish_success(response)
        await message.ack()
        logger.info(
            "Message processed successfully",
            extra={"event": "message_processed", "analysis_id": analysis_id},
        )
