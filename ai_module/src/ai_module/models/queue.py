"""Queue message models for RabbitMQ async workflow.

This module defines Pydantic models for messages consumed from and published to
RabbitMQ queues. These models enforce strict validation and provide serialization
for async analysis workflows.

Per FUN-009, the request model includes base64-encoded file bytes to enable
serialization through message brokers that do not support binary payloads.
"""

from __future__ import annotations

import base64
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from ai_module.models.report import Report, ReportMetadata

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
ContextText = Annotated[str, StringConstraints(max_length=1000)]


# ---------------------------------------------------------------------------
# Request Model
# ---------------------------------------------------------------------------


class QueueAnalysisRequest(BaseModel):
    """Message schema for analysis requests consumed from RabbitMQ.

    This model represents the payload structure consumed from the
    `analysis.requests` queue. File bytes are base64-encoded for
    message broker compatibility.

    Attributes
    ----------
    analysis_id : str
        Unique identifier for the analysis request (provided by orchestrator).
        Must be non-empty. Format validation delegated to SOAT (GUD-006).
    file_bytes_b64 : str
        Base64-encoded file content. Must be valid base64 string.
    file_name : str
        Original filename with extension (e.g., "architecture.png").
        Must be non-empty.
    context_text : str | None
        Optional context text to guide analysis. Maximum 1000 characters.
        Defaults to None if not provided.

    Methods
    -------
    decode_file_bytes() -> bytes
        Decodes the base64-encoded file bytes and returns raw bytes.
        Raises ValueError if base64 decoding fails (should not happen
        after validation).

    Examples
    --------
    >>> import base64
    >>> file_data = b"fake image data"
    >>> encoded = base64.b64encode(file_data).decode("utf-8")
    >>> request = QueueAnalysisRequest(
    ...     analysis_id="abc123",
    ...     file_bytes_b64=encoded,
    ...     file_name="diagram.png"
    ... )
    >>> assert request.decode_file_bytes() == file_data
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    analysis_id: NonEmptyStr = Field(
        ...,
        description="Unique analysis identifier",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    file_bytes_b64: str = Field(
        ...,
        description="Base64-encoded file bytes",
        examples=["aGVsbG8gd29ybGQ="],
    )

    file_name: NonEmptyStr = Field(
        ...,
        description="Original filename with extension",
        examples=["architecture.png", "diagram.pdf"],
    )

    context_text: ContextText | None = Field(
        default=None,
        description="Optional context to guide analysis (max 1000 chars)",
        examples=["This is an e-commerce microservices architecture"],
    )

    @field_validator("analysis_id", mode="after")
    @classmethod
    def validate_analysis_id_not_empty(cls, v: str) -> str:
        """Ensure analysis_id is not empty after stripping whitespace."""
        if not v:
            raise ValueError("analysis_id must be non-empty")
        return v

    @field_validator("file_bytes_b64", mode="after")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        """Validate that file_bytes_b64 is a valid base64 string.

        This validator attempts to decode the base64 string to ensure it is valid.
        Invalid base64 encoding will raise a ValidationError.

        Raises
        ------
        ValueError
            If the string is not valid base64 encoding.
        """
        try:
            base64.b64decode(v, validate=True)
        except Exception as e:
            raise ValueError(f"file_bytes_b64 must be valid base64: {e}") from e
        return v

    @field_validator("file_name", mode="after")
    @classmethod
    def validate_filename_not_empty(cls, v: str) -> str:
        """Ensure file_name is not empty after stripping whitespace."""
        if not v:
            raise ValueError("file_name must be non-empty")
        return v

    @field_validator("context_text", mode="after")
    @classmethod
    def validate_context_text_length(cls, v: str | None) -> str | None:
        """Ensure context_text does not exceed 1000 characters if provided."""
        if v is not None and len(v) > 1000:
            raise ValueError("context_text must not exceed 1000 characters")
        return v

    def decode_file_bytes(self) -> bytes:
        """Decode the base64-encoded file bytes.

        Returns
        -------
        bytes
            The decoded file content as raw bytes.

        Raises
        ------
        ValueError
            If base64 decoding fails (should not happen after validation).

        Examples
        --------
        >>> import base64
        >>> encoded = base64.b64encode(b"test data").decode("utf-8")
        >>> request = QueueAnalysisRequest(
        ...     analysis_id="test",
        ...     file_bytes_b64=encoded,
        ...     file_name="test.txt"
        ... )
        >>> assert request.decode_file_bytes() == b"test data"
        """
        try:
            return base64.b64decode(self.file_bytes_b64, validate=True)
        except Exception as e:
            raise ValueError(f"Failed to decode file_bytes_b64: {e}") from e


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class QueueAnalysisResponse(BaseModel):
    """Message schema for successful analysis results published to RabbitMQ.

    This model represents the payload structure published to the
    `analysis.results` queue when analysis completes successfully.
    It mirrors the structure of `AnalyzeResponse` from the HTTP API.

    Attributes
    ----------
    analysis_id : str
        Unique identifier for the analysis request (matches request).
        Must be non-empty.
    status : Literal["success"]
        Fixed value "success" indicating successful analysis.
    report : Report
        Structured analysis report containing summary, components, risks,
        and recommendations.
    metadata : ReportMetadata
        Metadata about the analysis execution (model version, processing time).

    Examples
    --------
    >>> from ai_module.models.report import Report, ReportMetadata
    >>> response = QueueAnalysisResponse(
    ...     analysis_id="abc123",
    ...     status="success",
    ...     report=Report(
    ...         summary="Architecture summary",
    ...         architecture_components=[],
    ...         security_risks=[],
    ...         scalability_recommendations=[]
    ...     ),
    ...     metadata=ReportMetadata(
    ...         model_version="gpt-4o",
    ...         processing_time_seconds=2.5
    ...     )
    ... )
    >>> assert response.status == "success"
    >>> assert response.analysis_id == "abc123"
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    analysis_id: NonEmptyStr = Field(
        ...,
        description="Unique analysis identifier (matches request)",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    status: Literal["success"] = Field(
        default="success",
        description="Fixed status indicating successful analysis",
    )

    report: Report = Field(
        ...,
        description="Structured analysis report with findings",
    )

    metadata: ReportMetadata = Field(
        ...,
        description="Analysis execution metadata",
    )

    @field_validator("analysis_id", mode="after")
    @classmethod
    def validate_analysis_id_not_empty(cls, v: str) -> str:
        """Ensure analysis_id is not empty after stripping whitespace."""
        if not v:
            raise ValueError("analysis_id must be non-empty")
        return v


class QueueErrorResponse(BaseModel):
    """Message schema for error results published to RabbitMQ.

    This model represents the payload structure published to the
    `analysis.results` queue when analysis fails. It mirrors the
    structure of `ErrorResponse` from the HTTP API.

    Attributes
    ----------
    analysis_id : str
        Unique identifier for the analysis request (matches request).
        Must be non-empty.
    status : Literal["error"]
        Fixed value "error" indicating analysis failure.
    error_code : str
        Error classification code per spec (INVALID_INPUT, AI_FAILURE, etc.).
        Must be non-empty.
    message : str
        Human-readable error description. Must be non-empty.

    Error Codes (per spec v2.1)
    ---------------------------
    - INVALID_INPUT: Invalid request content, file, or field values
    - FILE_TYPE_NOT_SUPPORTED: File type validation failed
    - AI_FAILURE: LLM processing failed after retries
    - AI_TIMEOUT: Provider timeout occurred
    - SCHEMA_VALIDATION_FAILURE: LLM output failed schema validation

    Examples
    --------
    >>> error = QueueErrorResponse(
    ...     analysis_id="abc123",
    ...     status="error",
    ...     error_code="INVALID_INPUT",
    ...     message="File type not supported: .txt"
    ... )
    >>> assert error.status == "error"
    >>> assert error.error_code == "INVALID_INPUT"
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    analysis_id: NonEmptyStr = Field(
        ...,
        description="Unique analysis identifier (matches request)",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    status: Literal["error"] = Field(
        default="error",
        description="Fixed status indicating analysis failure",
    )

    error_code: NonEmptyStr = Field(
        ...,
        description="Error classification code per spec",
        examples=["INVALID_INPUT", "AI_FAILURE", "AI_TIMEOUT"],
    )

    message: NonEmptyStr = Field(
        ...,
        description="Human-readable error description",
        examples=["File type not supported: .txt"],
    )

    @field_validator("analysis_id", mode="after")
    @classmethod
    def validate_analysis_id_not_empty(cls, v: str) -> str:
        """Ensure analysis_id is not empty after stripping whitespace."""
        if not v:
            raise ValueError("analysis_id must be non-empty")
        return v

    @field_validator("error_code", mode="after")
    @classmethod
    def validate_error_code_not_empty(cls, v: str) -> str:
        """Ensure error_code is not empty after stripping whitespace."""
        if not v:
            raise ValueError("error_code must be non-empty")
        return v

    @field_validator("message", mode="after")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        """Ensure message is not empty after stripping whitespace."""
        if not v:
            raise ValueError("message must be non-empty")
        return v

