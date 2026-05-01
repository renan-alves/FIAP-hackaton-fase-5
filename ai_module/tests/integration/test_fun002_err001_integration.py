"""Integration tests for FUN-002 with ERR-001: structured validation errors.

This test module verifies that FUN-002 (required inputs) integrates correctly
with ERR-001 (structured validation error requirements).

Related Requirements:
- FUN-002: The system MUST accept file and analysis_id as required inputs
- ERR-001: Invalid inputs MUST return structured validation errors

Test Coverage:
- Structured error for missing file (T023)
- Structured error for missing analysis_id (T024)
- Error response structure details (T025)
- Multiple validation errors (T026)
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import status
from fastapi.testclient import TestClient


def test_missing_file_returns_structured_error_per_err001(
    client: TestClient, mock_adapter: Any
) -> None:
    """T023: Test that missing file returns structured validation error per ERR-001.
    
    ERR-001 requires that validation errors are returned in a structured format
    with field names, error types, and descriptive messages.
    
    Expected behavior:
    - Status code: 422 Unprocessable Entity
    - Error response has 'detail' array
    - Each error has: type, loc, msg fields
    - Error indicates 'file' field is missing
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        response = client.post(
            "/analyze",
            data={"analysis_id": "test-missing-file"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Verify 422 status code
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Verify structured error response per ERR-001
    body = response.json()
    assert "detail" in body, "Error response should have 'detail' field"
    assert isinstance(body["detail"], list), "detail should be a list of errors"
    
    # Find error for 'file' field
    file_errors = [err for err in body["detail"] if "file" in str(err.get("loc", []))]
    assert len(file_errors) > 0, "Should have validation error for 'file' field"
    
    # Verify error structure per ERR-001
    file_error = file_errors[0]
    assert "type" in file_error, "Error should have 'type' field"
    assert "loc" in file_error, "Error should have 'loc' field indicating location"
    assert "msg" in file_error, "Error should have 'msg' field with description"
    
    # Verify error type indicates missing field
    assert file_error["type"] == "missing", "Error type should be 'missing'"
    
    # Verify location points to 'file' field
    assert "file" in file_error["loc"], "Error location should include 'file'"


def test_missing_analysis_id_returns_structured_error_per_err001(
    client: TestClient, png_bytes: bytes, mock_adapter: Any
) -> None:
    """T024: Test that missing analysis_id returns structured validation error.
    
    ERR-001 requires structured validation errors for all invalid inputs.
    
    Expected behavior:
    - Status code: 422 Unprocessable Entity
    - Error response has structured format
    - Error indicates 'analysis_id' field is missing
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
            # No 'data' parameter means no analysis_id
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Verify 422 status code
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Verify structured error response per ERR-001
    body = response.json()
    assert "detail" in body
    assert isinstance(body["detail"], list)
    
    # Find error for 'analysis_id' field
    analysis_id_errors = [
        err for err in body["detail"] if "analysis_id" in str(err.get("loc", []))
    ]
    assert len(analysis_id_errors) > 0, "Should have validation error for 'analysis_id'"
    
    # Verify error structure
    analysis_id_error = analysis_id_errors[0]
    assert "type" in analysis_id_error
    assert "loc" in analysis_id_error
    assert "msg" in analysis_id_error
    
    # Verify error type
    assert analysis_id_error["type"] == "missing"
    
    # Verify location
    assert "analysis_id" in analysis_id_error["loc"]


def test_error_response_includes_field_name_type_and_message(
    client: TestClient, mock_adapter: Any
) -> None:
    """T025: Test that error response includes field name, error type, and message.
    
    ERR-001 requires that each validation error includes:
    - Field location (loc)
    - Error type (type)
    - Human-readable message (msg)
    
    Expected behavior:
    - All three components are present
    - Information is actionable for debugging
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        # Send request with missing required parameters
        response = client.post("/analyze")
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Verify 422 status code
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Verify error structure
    body = response.json()
    assert "detail" in body
    errors = body["detail"]
    
    # Verify each error has required fields
    for error in errors:
        # ERR-001 requirement: field location
        assert "loc" in error, "Error should have 'loc' field"
        assert isinstance(error["loc"], list), "loc should be a list"
        assert len(error["loc"]) >= 2, "loc should have at least 2 elements"
        
        # ERR-001 requirement: error type
        assert "type" in error, "Error should have 'type' field"
        assert isinstance(error["type"], str), "type should be a string"
        assert len(error["type"]) > 0, "type should not be empty"
        
        # ERR-001 requirement: human-readable message
        assert "msg" in error, "Error should have 'msg' field"
        assert isinstance(error["msg"], str), "msg should be a string"
        assert len(error["msg"]) > 0, "msg should not be empty"
        
        # Additional useful fields (optional but good practice)
        # 'input' field shows what was received (if available)
        # This helps with debugging


def test_multiple_validation_errors_returned_together(
    client: TestClient, mock_adapter: Any
) -> None:
    """T026: Test that multiple validation errors are returned together.
    
    When multiple required parameters are missing, all errors should be
    returned in a single response (not just the first error).
    
    Expected behavior:
    - Status code: 422
    - Multiple errors in 'detail' array
    - Each error corresponds to a different field
    - Client receives complete validation feedback
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        # Send request with no parameters
        response = client.post("/analyze")
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Verify 422 status code
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Verify multiple errors are returned
    body = response.json()
    assert "detail" in body
    errors = body["detail"]
    
    # Should have at least 2 errors (file and analysis_id)
    assert len(errors) >= 2, "Should return errors for both missing parameters"
    
    # Extract field names from errors
    error_fields = set()
    for error in errors:
        if "loc" in error and len(error["loc"]) > 0:
            field_name = error["loc"][-1]  # Last element is the field name
            error_fields.add(field_name)
    
    # Verify both required parameters have errors
    assert "file" in error_fields, "Should have error for missing 'file'"
    assert "analysis_id" in error_fields, "Should have error for missing 'analysis_id'"


def test_error_response_format_is_consistent_across_validation_types(
    client: TestClient, png_bytes: bytes, mock_adapter: Any
) -> None:
    """Test that error response format is consistent across different validation types.
    
    ERR-001 requires consistent error structure regardless of validation type.
    
    Expected behavior:
    - Same error structure for missing fields, invalid types, etc.
    - Consistent field names across all errors
    - Predictable error format for API consumers
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    error_responses = []

    try:
        # Test 1: Missing file
        response1 = client.post(
            "/analyze",
            data={"analysis_id": "test-1"},
        )
        error_responses.append(response1.json())
        
        # Test 2: Missing analysis_id
        response2 = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
        )
        error_responses.append(response2.json())
        
        # Test 3: Both missing
        response3 = client.post("/analyze")
        error_responses.append(response3.json())
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Verify all responses have consistent structure
    for error_response in error_responses:
        assert "detail" in error_response, "All errors should have 'detail' field"
        assert isinstance(error_response["detail"], list), "detail should be a list"
        
        # Verify each error in detail has consistent structure
        for error in error_response["detail"]:
            assert "type" in error
            assert "loc" in error
            assert "msg" in error
            assert isinstance(error["loc"], list)
            assert isinstance(error["type"], str)
            assert isinstance(error["msg"], str)


def test_error_message_is_actionable_and_clear(
    client: TestClient, mock_adapter: Any
) -> None:
    """Test that error messages are actionable and clear.
    
    ERR-001 requires that error messages help developers understand
    what went wrong and how to fix it.
    
    Expected behavior:
    - Error messages are descriptive
    - Messages indicate what field is missing/invalid
    - Messages suggest how to fix the issue (if applicable)
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        response = client.post("/analyze")
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    body = response.json()
    errors = body["detail"]
    
    for error in errors:
        msg = error.get("msg", "")
        
        # Message should be non-empty
        assert len(msg) > 0, "Error message should not be empty"
        
        # Message should be descriptive (not just error codes)
        # FastAPI default: "Field required" is acceptable
        # Better: "The 'file' field is required"
        assert any(
            keyword in msg.lower()
            for keyword in ["required", "missing", "field", "invalid"]
        ), f"Error message should be descriptive: {msg}"


def test_error_response_for_invalid_content_type(
    client: TestClient, mock_adapter: Any
) -> None:
    """Test that error response is structured for invalid content type.
    
    This tests boundary condition where request doesn't have proper
    multipart/form-data content type.
    
    Expected behavior:
    - Appropriate error response
    - Structured error format maintained
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        # Send JSON instead of multipart/form-data
        response = client.post(
            "/analyze",
            json={"file": "not-a-file", "analysis_id": "test-id"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Should return error (422 or 400)
    assert response.status_code in [
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ]
    
    # Should have structured error
    body = response.json()
    assert "detail" in body
