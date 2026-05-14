"""Worker-specific exceptions for the RabbitMQ publisher (FUN-010).

Hierarchy
---------
PublishError                  Base for all publish failures (ERR-005)
├─ PublishConnectionError     RabbitMQ connection unavailable
└─ MessageSerializationError  Failed to serialise result to JSON
"""

from __future__ import annotations


class PublishError(Exception):
    """Raised when a result message cannot be published to the output queue."""


class PublishConnectionError(PublishError):
    """Raised when the RabbitMQ connection is unavailable during publish."""


class MessageSerializationError(PublishError):
    """Raised when the result payload cannot be serialised to JSON."""
