"""Domain exceptions for the AI Module.

These exceptions map directly to HTTP error responses via handlers
registered in main.py. Never expose internal details in the message
— the handlers serialize only the message field into the response body.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared error-code string constants
# Use these everywhere (HTTP handlers, queue worker) to prevent drift.
# ---------------------------------------------------------------------------

ERR_UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
ERR_INVALID_INPUT = "INVALID_INPUT"
ERR_AI_FAILURE = "AI_FAILURE"
ERR_AI_TIMEOUT = "AI_TIMEOUT"
ERR_INTERNAL_ERROR = "INTERNAL_ERROR"


def map_exception_to_error_code(exc: Exception) -> str:
    """Return the canonical error-code string for a given exception.

    Used by both the HTTP exception handlers in *main.py* and the queue
    worker in *consumer.py* so that the same exception always produces the
    same ``error_code`` regardless of which flow raised it.
    """
    from ai_module.core.exceptions import (
        AIFailureError,
        AITimeoutError,
        InvalidInputError,
        LLMCallError,
        LLMTimeoutError,
        UnsupportedFormatError,
    )

    if isinstance(exc, UnsupportedFormatError):
        return ERR_UNSUPPORTED_FORMAT
    if isinstance(exc, InvalidInputError):
        return ERR_INVALID_INPUT
    if isinstance(exc, (AITimeoutError, LLMTimeoutError)):
        return ERR_AI_TIMEOUT
    if isinstance(exc, (AIFailureError, LLMCallError)):
        return ERR_AI_FAILURE
    return ERR_INTERNAL_ERROR


class UnsupportedFormatError(Exception):
    """Lançada quando o tipo de arquivo enviado não é suportado. → HTTP 422"""

    def __init__(self, message: str = "File format not supported") -> None:
        self.message = message
        super().__init__(self.message)


class InvalidInputError(Exception):
    """Lançada quando o arquivo é inválido (muito grande, corrompido, etc.). → HTTP 422"""

    def __init__(self, message: str = "Invalid input file") -> None:
        self.message = message
        super().__init__(self.message)


class AIFailureError(Exception):
    """Lançada quando o pipeline de IA falha após todas as tentativas. → HTTP 500"""

    def __init__(self, message: str = "AI analysis failed") -> None:
        self.message = message
        super().__init__(self.message)


class LLMTimeoutError(Exception):
    """Lançada pelos adaptadores quando a chamada ao LLM excede o timeout configurado."""

    def __init__(self, message: str = "LLM call timed out") -> None:
        self.message = message
        super().__init__(self.message)


class LLMCallError(Exception):
    """Lançada pelos adaptadores quando o SDK do LLM retorna um erro."""

    def __init__(self, message: str = "LLM call failed") -> None:
        self.message = message
        super().__init__(self.message)


class AITimeoutError(Exception):
    """Raised when LLM times out after all retries. → HTTP 504"""

    def __init__(self, message: str = "LLM timeout") -> None:
        self.message = message
        super().__init__(self.message)


def classify_validation_error(error: str) -> str:
    """Mapeia uma mensagem de erro de validação para uma instrução de correção direcionada.

    Converte mensagens de erro técnicas de validação em instruções legíveis e
    acionáveis que o LLM pode usar para se auto-corrigir na próxima tentativa.

    Parameters
    ----------
    error : str
        String de erro de validação retornada por ``validate_and_normalize``.

    Returns
    -------
    str
        Instrução de correção legível para incorporar no próximo prompt do LLM,
        permitindo que o modelo corrija o problema específico.
    """
    if "JSON_PARSE_ERROR" in error:
        return (
            "Your response was not valid JSON. "
            "Return ONLY the raw JSON object, no markdown, no extra text."
        )
    if "components" in error:
        return (
            "The 'components' field is missing or empty. "
            "You MUST identify at least one component visible in the diagram."
        )
    if "summary" in error:
        return (
            "The 'summary' field is missing or exceeds 500 characters. "
            "Provide a concise summary of at most 500 characters."
        )
    if "severity" in error:
        return "Use only 'high', 'medium', or 'low' for risk severity."
    if "priority" in error:
        return "Use only 'high', 'medium', or 'low' for recommendation priority."
    if "SCHEMA_ERROR" in error:
        return (
            f"Schema validation failed: {error}. "
            "Fix only the invalid fields and return the complete JSON."
        )
    return f"Fix the invalid response. Error: {error}"
