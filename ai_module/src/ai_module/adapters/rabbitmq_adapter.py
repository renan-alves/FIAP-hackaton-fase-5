"""RabbitMQ connection adapter with resilient connect/disconnect lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import aio_pika
from aio_pika.abc import AbstractRobustConnection

from ai_module.core.logger import get_logger
from ai_module.core.settings import settings

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel

logger = get_logger(__name__, level=settings.LOG_LEVEL)


class RabbitMQAdapter:
    """Manages the RabbitMQ connection lifecycle.

    Wraps ``aio_pika.connect_robust`` to provide a single, shared connection
    that reconnects automatically on network failures.  Channels are created
    on demand and configured with the application QoS prefetch count.

    Usage::

        adapter = RabbitMQAdapter()
        await adapter.connect()
        channel = await adapter.get_channel()
        ...
        await adapter.disconnect()
    """

    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish a robust connection to RabbitMQ.

        Uses ``aio_pika.connect_robust`` which handles reconnection
        transparently.  Retries with exponential back-off (capped at
        ``settings.RABBITMQ_RECONNECT_MAX_DELAY_SECONDS``) until a
        connection is established.

        Raises:
            Exception: Re-raises the last connection error after all
                retry attempts are exhausted.
        """
        delay = 1.0
        attempt = 0

        while True:
            attempt += 1
            try:
                self._connection = await aio_pika.connect_robust(
                    url=settings.RABBITMQ_URL,
                    reconnect_interval=delay,
                )
                logger.info(
                    "RabbitMQ connected",
                    extra={
                        "event": "rabbitmq_connected",
                        "attempt": attempt,
                        "url": _safe_url(settings.RABBITMQ_URL),
                    },
                )
                return
            except Exception as exc:
                logger.warning(
                    "RabbitMQ connection failed, retrying",
                    extra={
                        "event": "rabbitmq_connect_retry",
                        "attempt": attempt,
                        "delay_seconds": delay,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, settings.RABBITMQ_RECONNECT_MAX_DELAY_SECONDS)

    async def disconnect(self) -> None:
        """Close the RabbitMQ connection gracefully.

        Safe to call even when not connected.
        """
        if self._connection is None:
            return

        with contextlib.suppress(Exception):
            await self._connection.close()

        self._connection = None
        logger.info(
            "RabbitMQ disconnected",
            extra={"event": "rabbitmq_disconnected"},
        )

    async def get_channel(self) -> AbstractChannel:
        """Return a new channel from the current connection.

        The channel is configured with the QoS prefetch count from
        ``settings.RABBITMQ_PREFETCH_COUNT`` to enforce back-pressure.

        Raises:
            RuntimeError: When called before :meth:`connect`.
        """
        if self._connection is None:
            raise RuntimeError(
                "RabbitMQAdapter is not connected. Call connect() first."
            )

        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=settings.RABBITMQ_PREFETCH_COUNT)
        logger.debug(
            "RabbitMQ channel opened",
            extra={
                "event": "rabbitmq_channel_opened",
                "prefetch_count": settings.RABBITMQ_PREFETCH_COUNT,
            },
        )
        return channel

    # ------------------------------------------------------------------
    # Properties (for observability / health checks)
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return ``True`` when a live connection exists."""
        return self._connection is not None and not self._connection.is_closed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_url(url: str) -> str:
    """Strip credentials from an AMQP URL before logging."""
    try:
        from yarl import URL  # aio-pika ships yarl as a dependency

        parsed = URL(url)
        return str(parsed.with_user(None).with_password(None))
    except Exception:
        return "<amqp url>"
