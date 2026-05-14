"""Test aio-pika import and basic type checking."""
import pytest


def test_aiopika_import() -> None:
    """Verify aio-pika can be imported without errors."""
    import aio_pika  # noqa: F401
    
    # If import succeeds, test passes
    assert True


@pytest.mark.asyncio
async def test_aiopika_types() -> None:
    """Verify aio-pika types work with mypy strict mode."""
    from aio_pika.abc import AbstractRobustConnection
    
    # Type checking - this should pass mypy
    connection: AbstractRobustConnection | None = None
    
    # We don't actually connect in tests, just verify types
    assert connection is None
