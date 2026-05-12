"""Result publisher — writes analysis outcomes to the RabbitMQ output queue.

Implements the :class:`~ai_module.worker.consumer.ResultPublisher` protocol so
that :class:`~ai_module.worker.consumer.MessageConsumer` can inject it without
coupling to a concrete class.

Retry strategy
--------------
Each publish is attempted up to ``_MAX_PUBLISH_ATTEMPTS`` times with
exponential back-off (1 s → 2 s between attempts).  If every attempt fails,
``metrics.publish_failures`` is incremented and the last exception is
re-raised so the caller can decide how to surface the error.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aio_pika
from aio_pika import DeliveryMode

from ai_module.adapters.rabbitmq_adapter import RabbitMQAdapter
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics
from ai_module.core.settings import settings
from ai_module.models.queue import QueueAnalysisResponse, QueueErrorResponse

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel

logger = get_logger(__name__, level=settings.LOG_LEVEL)

_MAX_PUBLISH_ATTEMPTS = 3


class RabbitMQResultPublisher:
    """Publishes analysis results to the RabbitMQ output queue.

    Args:
        adapter: Connected :class:`~ai_module.adapters.rabbitmq_adapter.RabbitMQAdapter`
            used to obtain a channel on demand.
    """

    def __init__(self, adapter: RabbitMQAdapter) -> None:
        self._adapter = adapter

    async def publish_success(self, response: QueueAnalysisResponse) -> None:
        """Publish a successful analysis result to the output queue.

        Serialises *response* to JSON, publishes it as a persistent message,
        and increments ``metrics.results_published`` on success.

        Args:
            response: Validated response model to serialise and publish.

        Raises:
            Exception: If all publish attempts fail.
        """
        await self._publish(
            body=response.model_dump_json().encode(),
            analysis_id=response.analysis_id,
            event_prefix="publish_success",
        )
        metrics.results_published += 1
        logger.info(
            "Success result published",
            extra={
                "event": "result_published",
                "analysis_id": response.analysis_id,
                "status": "success",
                "queue_name": settings.RABBITMQ_OUTPUT_QUEUE,
            },
        )

    async def publish_error(self, error: QueueErrorResponse) -> None:
        """Publish an error response to the output queue.

        Serialises *error* to JSON, publishes it as a persistent message,
        and increments ``metrics.errors_published`` on success.

        Args:
            error: Error response model to serialise and publish.

        Raises:
            Exception: If all publish attempts fail.
        """
        await self._publish(
            body=error.model_dump_json().encode(),
            analysis_id=error.analysis_id,
            event_prefix="publish_error",
        )
        metrics.errors_published += 1
        logger.info(
            "Error result published",
            extra={
                "event": "result_published",
                "analysis_id": error.analysis_id,
                "status": "error",
                "error_code": error.error_code,
                "queue_name": settings.RABBITMQ_OUTPUT_QUEUE,
            },
        )

    async def _publish(self, body: bytes, analysis_id: str, event_prefix: str) -> None:
        """Publish raw bytes to the output queue with retry logic.

        Declares the named direct exchange and routes via the output queue name
        as routing key. This matches the topology declared by the consumer.

        Args:
            body: UTF-8 encoded JSON message bytes.
            analysis_id: Included in structured log entries for traceability.
            event_prefix: Log event name prefix (e.g. ``"publish_success"``).

        Raises:
            Exception: The last publish exception after all retries are exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_PUBLISH_ATTEMPTS):
            try:
                channel: AbstractChannel = await self._adapter.get_channel()
                # Declare the named direct exchange — passive=False, durable=True.
                exchange = await channel.declare_exchange(
                    settings.RABBITMQ_EXCHANGE,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )
                message = aio_pika.Message(
                    body=body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                )
                await exchange.publish(
                    message,
                    routing_key=settings.RABBITMQ_OUTPUT_QUEUE,
                )
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Publish attempt failed",
                    extra={
                        "event": "publish_attempt_failed",
                        "analysis_id": analysis_id,
                        "attempt": attempt + 1,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "queue_name": settings.RABBITMQ_OUTPUT_QUEUE,
                    },
                )
                if attempt < _MAX_PUBLISH_ATTEMPTS - 1:
                    await asyncio.sleep(2**attempt)

        metrics.publish_failures += 1
        logger.error(
            "All publish attempts exhausted",
            extra={
                "event": "publish_failed",
                "analysis_id": analysis_id,
                "retry_count": _MAX_PUBLISH_ATTEMPTS,
                "error": str(last_exc),
                "error_type": type(last_exc).__name__ if last_exc else "Unknown",
                "queue_name": settings.RABBITMQ_OUTPUT_QUEUE,
                "connection_state": "connected" if self._adapter.is_connected else "disconnected",
            },
        )
        raise last_exc  # type: ignore[misc]
