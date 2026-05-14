"""Unit tests for queue message models.

This module tests the QueueAnalysisRequest model including:
- Field validation (non-empty strings, base64 encoding, length constraints)
- Base64 decoding functionality
- Pydantic validation error handling
"""

import base64

import pytest
from pydantic import ValidationError

from ai_module.models.queue import (
    QueueAnalysisRequest,
    QueueAnalysisResponse,
    QueueErrorResponse,
)
from ai_module.models.report import Component, Report, ReportMetadata

# ---------------------------------------------------------------------------
# Valid Request Tests
# ---------------------------------------------------------------------------


def test_queue_request_with_valid_fields() -> None:
    """Test creating a valid queue request with all fields."""
    file_data = b"fake image data for testing"
    encoded = base64.b64encode(file_data).decode("utf-8")

    request = QueueAnalysisRequest(
        analysis_id="test-analysis-123",
        file_bytes_b64=encoded,
        file_name="architecture.png",
        context_text="This is a test context",
    )

    assert request.analysis_id == "test-analysis-123"
    assert request.file_bytes_b64 == encoded
    assert request.file_name == "architecture.png"
    assert request.context_text == "This is a test context"


def test_queue_request_without_context() -> None:
    """Test creating a valid queue request without optional context_text."""
    file_data = b"test data"
    encoded = base64.b64encode(file_data).decode("utf-8")

    request = QueueAnalysisRequest(
        analysis_id="test-123",
        file_bytes_b64=encoded,
        file_name="diagram.pdf",
    )

    assert request.analysis_id == "test-123"
    assert request.file_name == "diagram.pdf"
    assert request.context_text is None


def test_queue_request_strips_whitespace() -> None:
    """Test that whitespace is stripped from string fields."""
    file_data = b"data"
    encoded = base64.b64encode(file_data).decode("utf-8")

    request = QueueAnalysisRequest(
        analysis_id="  test-123  ",
        file_bytes_b64=encoded,
        file_name="  diagram.png  ",
        context_text="  context with spaces  ",
    )

    assert request.analysis_id == "test-123"
    assert request.file_name == "diagram.png"
    assert request.context_text == "context with spaces"


# ---------------------------------------------------------------------------
# Base64 Decoding Tests
# ---------------------------------------------------------------------------


def test_decode_file_bytes_returns_original() -> None:
    """Test that decode_file_bytes returns the original bytes."""
    original_data = b"this is the original file content"
    encoded = base64.b64encode(original_data).decode("utf-8")

    request = QueueAnalysisRequest(
        analysis_id="test",
        file_bytes_b64=encoded,
        file_name="test.txt",
    )

    decoded = request.decode_file_bytes()
    assert decoded == original_data


def test_decode_file_bytes_with_binary_data() -> None:
    """Test decoding with actual binary data (e.g., image-like bytes)."""
    binary_data = bytes(range(256))  # All possible byte values
    encoded = base64.b64encode(binary_data).decode("utf-8")

    request = QueueAnalysisRequest(
        analysis_id="binary-test",
        file_bytes_b64=encoded,
        file_name="binary.bin",
    )

    decoded = request.decode_file_bytes()
    assert decoded == binary_data


# ---------------------------------------------------------------------------
# Validation Error Tests
# ---------------------------------------------------------------------------


def test_empty_analysis_id_raises_error() -> None:
    """Test that empty analysis_id raises ValidationError."""
    encoded = base64.b64encode(b"data").decode("utf-8")

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="",
            file_bytes_b64=encoded,
            file_name="test.png",
        )

    errors = exc_info.value.errors()
    # StringConstraints(min_length=1) catches empty strings
    assert any(
        "analysis_id" in str(err["loc"])
        and ("min_length" in err["msg"].lower() or "at least 1" in err["msg"].lower())
        for err in errors
    )


def test_whitespace_only_analysis_id_raises_error() -> None:
    """Test that whitespace-only analysis_id raises error after stripping."""
    encoded = base64.b64encode(b"data").decode("utf-8")

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="   ",
            file_bytes_b64=encoded,
            file_name="test.png",
        )

    errors = exc_info.value.errors()
    # After stripping, becomes empty string which fails min_length=1
    assert any(
        "analysis_id" in str(err["loc"])
        and ("min_length" in err["msg"].lower() or "at least 1" in err["msg"].lower())
        for err in errors
    )


def test_invalid_base64_raises_error() -> None:
    """Test that invalid base64 string raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="test",
            file_bytes_b64="this is not valid base64!!!",
            file_name="test.png",
        )

    errors = exc_info.value.errors()
    assert any(
        "file_bytes_b64" in str(err["loc"]) and "base64" in err["msg"].lower()
        for err in errors
    )


def test_empty_filename_raises_error() -> None:
    """Test that empty file_name raises ValidationError."""
    encoded = base64.b64encode(b"data").decode("utf-8")

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="test",
            file_bytes_b64=encoded,
            file_name="",
        )

    errors = exc_info.value.errors()
    # StringConstraints(min_length=1) catches empty strings
    assert any(
        "file_name" in str(err["loc"])
        and ("min_length" in err["msg"].lower() or "at least 1" in err["msg"].lower())
        for err in errors
    )


def test_whitespace_only_filename_raises_error() -> None:
    """Test that whitespace-only file_name raises error after stripping."""
    encoded = base64.b64encode(b"data").decode("utf-8")

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="test",
            file_bytes_b64=encoded,
            file_name="   ",
        )

    errors = exc_info.value.errors()
    # After stripping, becomes empty string which fails min_length=1
    assert any(
        "file_name" in str(err["loc"])
        and ("min_length" in err["msg"].lower() or "at least 1" in err["msg"].lower())
        for err in errors
    )


def test_context_text_exceeds_max_length_raises_error() -> None:
    """Test that context_text exceeding 1000 chars raises ValidationError."""
    encoded = base64.b64encode(b"data").decode("utf-8")
    long_context = "x" * 1001  # 1001 characters

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="test",
            file_bytes_b64=encoded,
            file_name="test.png",
            context_text=long_context,
        )

    errors = exc_info.value.errors()
    assert any(
        "context_text" in str(err["loc"])
        and ("1000" in err["msg"] or "max_length" in err["msg"].lower())
        for err in errors
    )


def test_context_text_exactly_1000_chars_is_valid() -> None:
    """Test that context_text with exactly 1000 chars is accepted."""
    encoded = base64.b64encode(b"data").decode("utf-8")
    max_context = "x" * 1000  # Exactly 1000 characters

    request = QueueAnalysisRequest(
        analysis_id="test",
        file_bytes_b64=encoded,
        file_name="test.png",
        context_text=max_context,
    )

    assert request.context_text is not None
    assert len(request.context_text) == 1000


def test_extra_fields_are_rejected() -> None:
    """Test that extra fields raise ValidationError (extra='forbid')."""
    encoded = base64.b64encode(b"data").decode("utf-8")

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="test",
            file_bytes_b64=encoded,
            file_name="test.png",
            extra_field="should not be allowed",  # type: ignore
        )

    errors = exc_info.value.errors()
    assert any("extra_field" in str(err["loc"]) for err in errors)


def test_missing_required_field_raises_error() -> None:
    """Test that missing required fields raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(  # type: ignore
            analysis_id="test",
            file_name="test.png",
            # Missing file_bytes_b64
        )

    errors = exc_info.value.errors()
    assert any("file_bytes_b64" in str(err["loc"]) for err in errors)


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


def test_base64_with_padding() -> None:
    """Test base64 strings with different padding scenarios."""
    # Base64 strings can have 0, 1, or 2 padding '=' characters
    test_cases = [
        b"a",  # Will have == padding
        b"ab",  # Will have = padding
        b"abc",  # No padding
    ]

    for data in test_cases:
        encoded = base64.b64encode(data).decode("utf-8")
        request = QueueAnalysisRequest(
            analysis_id="padding-test",
            file_bytes_b64=encoded,
            file_name="test.bin",
        )
        assert request.decode_file_bytes() == data


def test_base64_with_newlines_is_invalid() -> None:
    """Test that base64 with newlines is rejected (strict validation)."""
    data = b"test data"
    encoded = base64.b64encode(data).decode("utf-8")
    encoded_with_newlines = encoded[:10] + "\n" + encoded[10:]

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisRequest(
            analysis_id="test",
            file_bytes_b64=encoded_with_newlines,
            file_name="test.png",
        )

    errors = exc_info.value.errors()
    assert any("file_bytes_b64" in str(err["loc"]) for err in errors)


def test_unicode_filename() -> None:
    """Test that Unicode characters in filename are preserved."""
    encoded = base64.b64encode(b"data").decode("utf-8")

    request = QueueAnalysisRequest(
        analysis_id="test",
        file_bytes_b64=encoded,
        file_name="arquitetura_diagrama_日本語.png",
    )

    assert request.file_name == "arquitetura_diagrama_日本語.png"


def test_uuid_like_analysis_id() -> None:
    """Test that UUID-like strings are accepted for analysis_id."""
    encoded = base64.b64encode(b"data").decode("utf-8")

    request = QueueAnalysisRequest(
        analysis_id="550e8400-e29b-41d4-a716-446655440000",
        file_bytes_b64=encoded,
        file_name="test.png",
    )

    assert request.analysis_id == "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# QueueAnalysisResponse Tests
# ---------------------------------------------------------------------------


def test_queue_success_response_with_valid_fields() -> None:
    """Test creating a valid success response with all required fields."""
    component = Component(
        name="API Gateway",
        type="service",
        description="Main API gateway",
    )
    report = Report(
        summary="Test architecture summary",
        components=[component],
    )
    metadata = ReportMetadata(
        model_used="gpt-4o",
        processing_time_ms=2500,
        input_type="image",
    )

    response = QueueAnalysisResponse(
        analysis_id="test-123",
        status="success",
        report=report,
        metadata=metadata,
    )

    assert response.analysis_id == "test-123"
    assert response.status == "success"
    assert response.report == report
    assert response.metadata == metadata


def test_queue_success_response_default_status() -> None:
    """Test that status defaults to 'success'."""
    component = Component(
        name="Database",
        type="database",
        description="Primary database",
    )
    report = Report(
        summary="Test summary",
        components=[component],
    )
    metadata = ReportMetadata(
        model_used="gpt-4o",
        processing_time_ms=1000,
        input_type="image",
    )

    response = QueueAnalysisResponse(
        analysis_id="test-456",
        report=report,
        metadata=metadata,
    )

    assert response.status == "success"


def test_queue_success_response_serialization() -> None:
    """Test that success response serializes to JSON correctly."""
    component = Component(
        name="API",
        type="service",
        description="REST API service",
    )
    report = Report(
        summary="Serialization test",
        components=[component],
    )
    metadata = ReportMetadata(
        model_used="gpt-4o-mini",
        processing_time_ms=1500,
        input_type="pdf",
    )

    response = QueueAnalysisResponse(
        analysis_id="ser-test",
        report=report,
        metadata=metadata,
    )

    json_data = response.model_dump(mode="json")

    assert json_data["analysis_id"] == "ser-test"
    assert json_data["status"] == "success"
    assert "report" in json_data
    assert "metadata" in json_data


def test_queue_success_response_empty_analysis_id_rejected() -> None:
    """Test that empty analysis_id is rejected."""
    component = Component(
        name="Service",
        type="service",
        description="Test service",
    )
    report = Report(
        summary="Test",
        components=[component],
    )
    metadata = ReportMetadata(
        model_used="gpt-4o",
        processing_time_ms=1000,
        input_type="image",
    )

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisResponse(
            analysis_id="   ",  # Whitespace only
            report=report,
            metadata=metadata,
        )

    errors = exc_info.value.errors()
    assert any("analysis_id" in str(err["loc"]) for err in errors)


def test_queue_success_response_missing_report_rejected() -> None:
    """Test that missing report field is rejected."""
    metadata = ReportMetadata(
        model_used="gpt-4o",
        processing_time_ms=1000,
        input_type="image",
    )

    with pytest.raises(ValidationError) as exc_info:
        QueueAnalysisResponse(  # type: ignore
            analysis_id="test",
            metadata=metadata,
            # Missing report
        )

    errors = exc_info.value.errors()
    assert any("report" in str(err["loc"]) for err in errors)


# ---------------------------------------------------------------------------
# QueueErrorResponse Tests
# ---------------------------------------------------------------------------


def test_queue_error_response_with_valid_fields() -> None:
    """Test creating a valid error response with all required fields."""
    error = QueueErrorResponse(
        analysis_id="error-123",
        status="error",
        error_code="INVALID_INPUT",
        message="File type not supported",
    )

    assert error.analysis_id == "error-123"
    assert error.status == "error"
    assert error.error_code == "INVALID_INPUT"
    assert error.message == "File type not supported"


def test_queue_error_response_default_status() -> None:
    """Test that status defaults to 'error'."""
    error = QueueErrorResponse(
        analysis_id="err-456",
        error_code="AI_FAILURE",
        message="LLM processing failed",
    )

    assert error.status == "error"


def test_queue_error_response_all_error_codes() -> None:
    """Test that all spec-defined error codes are accepted."""
    error_codes = [
        "INVALID_INPUT",
        "FILE_TYPE_NOT_SUPPORTED",
        "AI_FAILURE",
        "AI_TIMEOUT",
        "SCHEMA_VALIDATION_FAILURE",
    ]

    for code in error_codes:
        error = QueueErrorResponse(
            analysis_id=f"test-{code.lower()}",
            error_code=code,
            message=f"Test message for {code}",
        )
        assert error.error_code == code


def test_queue_error_response_serialization() -> None:
    """Test that error response serializes to JSON correctly."""
    error = QueueErrorResponse(
        analysis_id="json-test",
        error_code="AI_TIMEOUT",
        message="Provider timeout exceeded",
    )

    json_data = error.model_dump(mode="json")

    assert json_data["analysis_id"] == "json-test"
    assert json_data["status"] == "error"
    assert json_data["error_code"] == "AI_TIMEOUT"
    assert json_data["message"] == "Provider timeout exceeded"


def test_queue_error_response_empty_analysis_id_rejected() -> None:
    """Test that empty analysis_id is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        QueueErrorResponse(
            analysis_id="   ",  # Whitespace only
            error_code="INVALID_INPUT",
            message="Test error",
        )

    errors = exc_info.value.errors()
    assert any("analysis_id" in str(err["loc"]) for err in errors)


def test_queue_error_response_empty_error_code_rejected() -> None:
    """Test that empty error_code is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        QueueErrorResponse(
            analysis_id="test",
            error_code="   ",  # Whitespace only
            message="Test error",
        )

    errors = exc_info.value.errors()
    assert any("error_code" in str(err["loc"]) for err in errors)


def test_queue_error_response_empty_message_rejected() -> None:
    """Test that empty message is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        QueueErrorResponse(
            analysis_id="test",
            error_code="INVALID_INPUT",
            message="   ",  # Whitespace only
        )

    errors = exc_info.value.errors()
    assert any("message" in str(err["loc"]) for err in errors)


def test_queue_error_response_missing_required_fields() -> None:
    """Test that missing required fields are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        QueueErrorResponse(  # type: ignore
            analysis_id="test",
            # Missing error_code and message
        )

    errors = exc_info.value.errors()
    error_fields = [str(err["loc"]) for err in errors]
    assert any("error_code" in field for field in error_fields)
    assert any("message" in field for field in error_fields)


def test_queue_error_response_extra_fields_rejected() -> None:
    """Test that extra fields are rejected (extra='forbid')."""
    with pytest.raises(ValidationError) as exc_info:
        QueueErrorResponse(
            analysis_id="test",
            error_code="INVALID_INPUT",
            message="Test error",
            extra_field="not allowed",  # type: ignore
        )

    errors = exc_info.value.errors()
    assert any("extra_field" in str(err) for err in errors)


def test_queue_error_response_whitespace_stripping() -> None:
    """Test that whitespace is stripped from string fields."""
    error = QueueErrorResponse(
        analysis_id="  test-123  ",
        error_code="  AI_FAILURE  ",
        message="  Test message  ",
    )

    assert error.analysis_id == "test-123"
    assert error.error_code == "AI_FAILURE"
    assert error.message == "Test message"

