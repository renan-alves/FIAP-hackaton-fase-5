"""Service health state shared between main.py and routes.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_module.adapters.rabbitmq_adapter import RabbitMQAdapter

_service_healthy: bool = False
_queue_connected: bool = False
_rabbitmq_adapter: RabbitMQAdapter | None = None


def set_service_health(value: bool) -> None:
    global _service_healthy
    _service_healthy = value


def set_queue_health(value: bool) -> None:
    global _queue_connected
    _queue_connected = value


def set_rabbitmq_adapter(adapter: RabbitMQAdapter | None) -> None:
    """Register the RabbitMQ adapter for live connection checks."""
    global _rabbitmq_adapter
    _rabbitmq_adapter = adapter


def get_queue_connected() -> bool:
    """Return live RabbitMQ connection state from the adapter if available."""
    if _rabbitmq_adapter is not None:
        return _rabbitmq_adapter.is_connected
    return _queue_connected
