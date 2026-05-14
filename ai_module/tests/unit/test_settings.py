"""Testes unitários para validações de configurações."""

from __future__ import annotations

import warnings

from ai_module.core.settings import Settings


def test_validate_api_keys_emite_alerta_quando_nenhuma_chave_existe() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        Settings(GEMINI_API_KEY="", OPENAI_API_KEY="", LLM_PROVIDER="gemini")

    assert captured is not None
    assert len(captured) == 1
    assert "Nenhuma chave de API" in str(captured[0].message)


def test_validate_api_keys_aceita_quando_ha_ao_menos_uma_chave() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        settings = Settings(GEMINI_API_KEY="", OPENAI_API_KEY="openai-key", LLM_PROVIDER="gemini")

    assert captured is not None
    assert settings.OPENAI_API_KEY == "openai-key"
    assert captured == []


# ==================== RabbitMQ Configuration Tests ====================


def test_rabbitmq_url_default_value() -> None:
    """Verify RABBITMQ_URL has correct default value."""
    settings = Settings(GEMINI_API_KEY="test", LLM_PROVIDER="gemini")
    assert settings.RABBITMQ_URL == "amqp://guest:guest@localhost:5672/"


def test_rabbitmq_url_can_be_overridden() -> None:
    """Verify RABBITMQ_URL can be set via environment variable."""
    settings = Settings(
        GEMINI_API_KEY="test",
        LLM_PROVIDER="gemini",
        RABBITMQ_URL="amqp://user:pass@rabbitmq.example.com:5672/vhost"
    )
    assert settings.RABBITMQ_URL == "amqp://user:pass@rabbitmq.example.com:5672/vhost"


def test_rabbitmq_queues_default_values() -> None:
    """Verify queue names have correct default values."""
    settings = Settings(GEMINI_API_KEY="test", LLM_PROVIDER="gemini")
    assert settings.RABBITMQ_INPUT_QUEUE == "analysis.requests"
    assert settings.RABBITMQ_OUTPUT_QUEUE == "analysis.results"
    assert settings.RABBITMQ_EXCHANGE == "analysis"


def test_rabbitmq_queues_can_be_overridden() -> None:
    """Verify queue names can be customized."""
    settings = Settings(
        GEMINI_API_KEY="test",
        LLM_PROVIDER="gemini",
        RABBITMQ_INPUT_QUEUE="custom.input",
        RABBITMQ_OUTPUT_QUEUE="custom.output",
        RABBITMQ_EXCHANGE="custom.exchange"
    )
    assert settings.RABBITMQ_INPUT_QUEUE == "custom.input"
    assert settings.RABBITMQ_OUTPUT_QUEUE == "custom.output"
    assert settings.RABBITMQ_EXCHANGE == "custom.exchange"


def test_rabbitmq_prefetch_count_default() -> None:
    """Verify prefetch count defaults to 1 (single message processing)."""
    settings = Settings(GEMINI_API_KEY="test", LLM_PROVIDER="gemini")
    assert settings.RABBITMQ_PREFETCH_COUNT == 1


def test_rabbitmq_prefetch_count_can_be_increased() -> None:
    """Verify prefetch count can be increased for higher throughput."""
    settings = Settings(
        GEMINI_API_KEY="test",
        LLM_PROVIDER="gemini",
        RABBITMQ_PREFETCH_COUNT=5
    )
    assert settings.RABBITMQ_PREFETCH_COUNT == 5


def test_rabbitmq_reconnect_delay_default() -> None:
    """Verify reconnect max delay defaults to 60 seconds."""
    settings = Settings(GEMINI_API_KEY="test", LLM_PROVIDER="gemini")
    assert settings.RABBITMQ_RECONNECT_MAX_DELAY_SECONDS == 60


def test_rabbitmq_reconnect_delay_can_be_customized() -> None:
    """Verify reconnect delay can be customized."""
    settings = Settings(
        GEMINI_API_KEY="test",
        LLM_PROVIDER="gemini",
        RABBITMQ_RECONNECT_MAX_DELAY_SECONDS=30
    )
    assert settings.RABBITMQ_RECONNECT_MAX_DELAY_SECONDS == 30


def test_all_rabbitmq_settings_together() -> None:
    """Verify all RabbitMQ settings work together."""
    settings = Settings(
        GEMINI_API_KEY="test",
        LLM_PROVIDER="gemini",
        RABBITMQ_URL="amqp://prod:pass@rabbitmq:5672/",
        RABBITMQ_INPUT_QUEUE="prod.requests",
        RABBITMQ_OUTPUT_QUEUE="prod.results",
        RABBITMQ_EXCHANGE="prod",
        RABBITMQ_PREFETCH_COUNT=3,
        RABBITMQ_RECONNECT_MAX_DELAY_SECONDS=120
    )
    
    assert settings.RABBITMQ_URL == "amqp://prod:pass@rabbitmq:5672/"
    assert settings.RABBITMQ_INPUT_QUEUE == "prod.requests"
    assert settings.RABBITMQ_OUTPUT_QUEUE == "prod.results"
    assert settings.RABBITMQ_EXCHANGE == "prod"
    assert settings.RABBITMQ_PREFETCH_COUNT == 3
    assert settings.RABBITMQ_RECONNECT_MAX_DELAY_SECONDS == 120

