"""As configurações do aplicativo são carregadas a partir de variáveis de ambiente.

As configurações também podem ser definidas via arquivo .env.
"""

from __future__ import annotations

import warnings
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# core/settings.py


class Settings(BaseSettings):
    """Define e valida as configurações da aplicação a partir de
    variáveis de ambiente.

    Esta classe centraliza parâmetros de execução, integração com
    provedores de LLM, limites operacionais e configurações de mensageria,
    aplicando validações para garantir consistência dos valores carregados.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Provider credentials
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-1.5-pro"

    # LLM configuration
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # File constraints
    MAX_FILE_SIZE_MB: int = 10
    PDF_MAX_PAGES: int = Field(default=3, gt=0, le=10)
    MAX_IMAGE_SIDE_PX: int = Field(default=2048, gt=0)
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 2

    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "1.0.0"

    CONTEXT_TEXT_MAX_LENGTH: int = 1000
    ENABLE_CONFLICT_GUARDRAIL: bool = True
    CONFLICT_POLICY: str = "DIAGRAM_FIRST"
    INCLUDE_CONFLICT_METADATA: bool = True

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_INPUT_QUEUE: str = "analysis.requests"
    RABBITMQ_OUTPUT_QUEUE: str = "analysis.results"
    RABBITMQ_EXCHANGE: str = "analysis"
    RABBITMQ_PREFETCH_COUNT: int = 1
    RABBITMQ_RECONNECT_MAX_DELAY_SECONDS: int = 60
    RABBITMQ_WORKER_ENABLED: bool = False

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Valida o provedor de LLM e normaliza o valor para minúsculas.

        Args:
            v: Valor informado para o provedor de LLM.

        Returns:
            O nome do provedor em minúsculas.

        Raises:
            ValueError: Quando o provedor não é suportado.
        """
        normalized = v.lower()
        allowed = {"gemini", "openai"}
        if normalized not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}, got '{v}'")
        return normalized

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Valida o nível de log e retorna o valor em maiúsculas.

        Args:
            v: Nível de log informado.

        Returns:
            O nível de log normalizado em maiúsculas.

        Raises:
            ValueError: Quando o nível de log não pertence ao conjunto
            permitido.
        """
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()

    @model_validator(mode="after")
    def validate_api_keys(self) -> Settings:
        """Garante que ao menos uma chave de API esteja presente para uso dos
        provedores.

        Returns:
            A própria instância de configurações após validação.
        """
        provider = self.LLM_PROVIDER.upper()
        if not self.GEMINI_API_KEY and not self.OPENAI_API_KEY:
            warnings.warn(
                "Nenhuma chave de API definida. Configure GEMINI_API_KEY ou OPENAI_API_KEY.",
                UserWarning,
                stacklevel=2,
            )
        if provider not in ("GEMINI", "OPENAI"):
            raise ValueError(f"LLM_PROVIDER inválido: {provider}. Use GEMINI ou OPENAI.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Retorna uma instância única e cacheada de configurações da aplicação.

    Returns:
        Objeto `Settings` inicializado com variáveis de ambiente.
    """
    return Settings()


settings = get_settings()
