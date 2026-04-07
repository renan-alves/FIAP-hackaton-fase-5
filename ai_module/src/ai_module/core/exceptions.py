"""Domain exceptions for the AI Module.

These exceptions map directly to HTTP error responses via handlers
registered in main.py. Never expose internal details in the message
— the handlers serialize only the message field into the response body.
"""

from __future__ import annotations


class UnsupportedFormatError(Exception):
    """Raised when the uploaded file type is not supported. → HTTP 422"""

    def __init__(self, message: str = "File format not supported") -> None:
        self.message = message
        super().__init__(self.message)


class InvalidInputError(Exception):
    """Raised when the file is invalid (too large, corrupted, etc.). → HTTP 422"""

    def __init__(self, message: str = "Invalid input file") -> None:
        self.message = message
        super().__init__(self.message)


class AIFailureError(Exception):
    """Raised when the AI pipeline fails after all retries. → HTTP 500"""

    def __init__(self, message: str = "AI analysis failed") -> None:
        self.message = message
        super().__init__(self.message)


class LLMTimeoutError(Exception):
    """Raised by adapters when the LLM call exceeds the configured timeout."""

    def __init__(self, message: str = "LLM call timed out") -> None:
        self.message = message
        super().__init__(self.message)


class LLMCallError(Exception):
    """Raised by adapters when the LLM SDK returns an error."""

    def __init__(self, message: str = "LLM call failed") -> None:
        self.message = message
        super().__init__(self.message)