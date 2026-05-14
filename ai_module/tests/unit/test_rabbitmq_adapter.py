"""Unit tests for RabbitMQAdapter.

All aio_pika calls are mocked — no RabbitMQ server required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_module.adapters.rabbitmq_adapter import RabbitMQAdapter, _safe_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_connection(*, is_closed: bool = False) -> MagicMock:
    """Return a mock that looks like an aio_pika robust connection."""
    conn = AsyncMock()
    conn.is_closed = is_closed
    channel = AsyncMock()
    channel.set_qos = AsyncMock()
    conn.channel.return_value = channel
    return conn


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_successful_connection(self) -> None:
        """connect() stores the connection returned by connect_robust."""
        mock_conn = _make_mock_connection()

        with patch(
            "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ) as mock_connect:
            adapter = RabbitMQAdapter()
            await adapter.connect()

        mock_connect.assert_awaited_once()
        assert adapter._connection is mock_conn

    @pytest.mark.asyncio
    async def test_connect_sets_is_connected_true(self) -> None:
        """is_connected returns True after a successful connect()."""
        mock_conn = _make_mock_connection(is_closed=False)

        with patch(
            "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()

        assert adapter.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_retries_on_failure_then_succeeds(self) -> None:
        """connect() retries after a failure and succeeds on a later attempt."""
        mock_conn = _make_mock_connection()

        call_count = 0

        async def flaky_connect(**_kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("connection refused")
            return mock_conn

        with (
            patch(
                "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
                side_effect=flaky_connect,
            ),
            patch("ai_module.adapters.rabbitmq_adapter.asyncio.sleep", new_callable=AsyncMock),
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()

        assert call_count == 3
        assert adapter._connection is mock_conn

    @pytest.mark.asyncio
    async def test_connect_applies_exponential_backoff(self) -> None:
        """Retry delays double each attempt up to the configured maximum."""
        mock_conn = _make_mock_connection()
        sleep_calls: list[float] = []

        async def flaky_connect(**_kwargs: object) -> object:
            if len(sleep_calls) < 3:
                raise OSError("connection refused")
            return mock_conn

        async def record_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with (
            patch(
                "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
                side_effect=flaky_connect,
            ),
            patch(
                "ai_module.adapters.rabbitmq_adapter.asyncio.sleep",
                side_effect=record_sleep,
            ),
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()

        # Delays should double: 1, 2, 4 …
        assert sleep_calls == [1.0, 2.0, 4.0]

    @pytest.mark.asyncio
    async def test_connect_respects_max_delay(self) -> None:
        """Retry delay is capped at RABBITMQ_RECONNECT_MAX_DELAY_SECONDS."""
        mock_conn = _make_mock_connection()
        sleep_calls: list[float] = []
        attempts = 0

        async def flaky_connect(**_kwargs: object) -> object:
            nonlocal attempts
            attempts += 1
            if attempts < 10:
                raise OSError("connection refused")
            return mock_conn

        async def record_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with (
            patch(
                "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
                side_effect=flaky_connect,
            ),
            patch(
                "ai_module.adapters.rabbitmq_adapter.asyncio.sleep",
                side_effect=record_sleep,
            ),
            patch(
                "ai_module.adapters.rabbitmq_adapter.settings.RABBITMQ_RECONNECT_MAX_DELAY_SECONDS",
                5,
            ),
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()

        # After enough doublings, all subsequent delays must be ≤ 5
        assert all(d <= 5.0 for d in sleep_calls)


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_closes_connection(self) -> None:
        """disconnect() calls close() on the connection."""
        mock_conn = _make_mock_connection()

        with patch(
            "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()
            await adapter.disconnect()

        mock_conn.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_connection_reference(self) -> None:
        """disconnect() sets the internal connection reference to None."""
        mock_conn = _make_mock_connection()

        with patch(
            "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()
            await adapter.disconnect()

        assert adapter._connection is None

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected_is_safe(self) -> None:
        """disconnect() is a no-op when never connected."""
        adapter = RabbitMQAdapter()
        # Should not raise
        await adapter.disconnect()
        assert adapter._connection is None

    @pytest.mark.asyncio
    async def test_disconnect_suppresses_close_errors(self) -> None:
        """disconnect() does not propagate errors raised by close()."""
        mock_conn = _make_mock_connection()
        mock_conn.close.side_effect = RuntimeError("already closed")

        with patch(
            "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()
            # Should not raise
            await adapter.disconnect()

        assert adapter._connection is None

    @pytest.mark.asyncio
    async def test_is_connected_false_after_disconnect(self) -> None:
        """is_connected returns False after disconnect()."""
        mock_conn = _make_mock_connection(is_closed=False)

        with patch(
            "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()

        await adapter.disconnect()
        assert adapter.is_connected is False


# ---------------------------------------------------------------------------
# get_channel()
# ---------------------------------------------------------------------------


class TestGetChannel:
    @pytest.mark.asyncio
    async def test_get_channel_returns_channel(self) -> None:
        """get_channel() returns the channel from the connection."""
        mock_conn = _make_mock_connection()
        expected_channel = mock_conn.channel.return_value

        with patch(
            "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
            new_callable=AsyncMock,
            return_value=mock_conn,
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()
            channel = await adapter.get_channel()

        assert channel is expected_channel

    @pytest.mark.asyncio
    async def test_get_channel_sets_qos(self) -> None:
        """get_channel() configures the prefetch count via set_qos."""
        mock_conn = _make_mock_connection()
        mock_channel = mock_conn.channel.return_value

        with (
            patch(
                "ai_module.adapters.rabbitmq_adapter.aio_pika.connect_robust",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch(
                "ai_module.adapters.rabbitmq_adapter.settings.RABBITMQ_PREFETCH_COUNT",
                3,
            ),
        ):
            adapter = RabbitMQAdapter()
            await adapter.connect()
            await adapter.get_channel()

        mock_channel.set_qos.assert_awaited_once_with(prefetch_count=3)

    @pytest.mark.asyncio
    async def test_get_channel_raises_when_not_connected(self) -> None:
        """get_channel() raises RuntimeError if connect() was not called."""
        adapter = RabbitMQAdapter()
        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.get_channel()


# ---------------------------------------------------------------------------
# is_connected property
# ---------------------------------------------------------------------------


class TestIsConnected:
    def test_is_connected_false_initially(self) -> None:
        adapter = RabbitMQAdapter()
        assert adapter.is_connected is False

    def test_is_connected_false_when_connection_closed(self) -> None:
        adapter = RabbitMQAdapter()
        mock_conn = MagicMock()
        mock_conn.is_closed = True
        adapter._connection = mock_conn  # type: ignore[assignment]
        assert adapter.is_connected is False

    def test_is_connected_true_when_connection_open(self) -> None:
        adapter = RabbitMQAdapter()
        mock_conn = MagicMock()
        mock_conn.is_closed = False
        adapter._connection = mock_conn  # type: ignore[assignment]
        assert adapter.is_connected is True


# ---------------------------------------------------------------------------
# _safe_url helper
# ---------------------------------------------------------------------------


class TestSafeUrl:
    def test_strips_credentials(self) -> None:
        url = "amqp://user:password@rabbitmq:5672/vhost"
        result = _safe_url(url)
        assert "user" not in result
        assert "password" not in result

    def test_plain_url_without_credentials(self) -> None:
        url = "amqp://rabbitmq:5672/"
        result = _safe_url(url)
        assert result  # non-empty
        assert "rabbitmq" in result

    def test_returns_fallback_on_parse_error(self) -> None:
        result = _safe_url("not-a-valid-url")
        assert result  # returns something non-empty
