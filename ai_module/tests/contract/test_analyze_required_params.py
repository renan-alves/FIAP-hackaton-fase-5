"""Contract tests for FUN-002: Required parameters in POST /analyze endpoint.

Contract tests ensure API stability and prevent breaking changes. These tests
document and verify the expected API contract for required parameters.

Related Requirements:
- FUN-002: The system MUST accept file and analysis_id as required inputs

Test Coverage:
- Content-Type requirements (T034)
- Required field verification (T035, T036)
- Response contract (T037)
- Error response contract (T038)

Contract Definition:
- Request: multipart/form-data with 'file' (UploadFile) and 'analysis_id' (Form string)
- Success Response (200): AnalyzeResponse with analysis_id, status, report, metadata
- Error Response (422): ValidationError with detail array
"""

from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.testclient import TestClient


def test_endpoint_accepts_multipart_form_data(
    client: TestClient, png_bytes: bytes, mock_adapter: Any
) -> None:
    """T034: Contract test - Endpoint accepts multipart/form-data content type.
    
    Contract Requirement:
    - POST /analyze MUST accept multipart/form-data
    - Content-Type: multipart/form-data; boundary=...
    
    Breaking Change Detection:
    - Changing to JSON-only would break this contract
    - Removing file upload support would break this contract
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        # TestClient automatically sets Content-Type to multipart/form-data
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
            data={"analysis_id": "contract-test-001"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Contract: multipart/form-data requests are accepted
    assert response.status_code == status.HTTP_200_OK
    
    # Verify response structure
    body = response.json()
    assert "status" in body
    assert body["status"] == "success"


def test_file_field_is_required_in_request(
    client: TestClient, mock_adapter: Any
) -> None:
    """T035: Contract test - 'file' field is required in request.
    
    Contract Requirement:
    - POST /analyze MUST require 'file' field
    - Missing 'file' MUST return 422 status code
    - Error response MUST indicate 'file' field is missing
    
    Breaking Change Detection:
    - Making 'file' optional would break this contract
    - Accepting requests without 'file' would break this contract
    - Changing error status code would break this contract
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        # Send request without 'file' field
        response = client.post(
            "/analyze",
            data={"analysis_id": "contract-test-002"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Contract: Missing 'file' returns 422
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Contract: Error response has 'detail' array
    body = response.json()
    assert "detail" in body
    assert isinstance(body["detail"], list)
    
    # Contract: Error indicates 'file' field is missing
    file_errors = [err for err in body["detail"] if "file" in str(err.get("loc", []))]
    assert len(file_errors) > 0, "Error must indicate 'file' field is missing"


def test_analysis_id_field_is_required_in_request(
    client: TestClient, png_bytes: bytes, mock_adapter: Any
) -> None:
    """T036: Contract test - 'analysis_id' field is required in request.
    
    Contract Requirement:
    - POST /analyze MUST require 'analysis_id' field
    - Missing 'analysis_id' MUST return 422 status code
    - Error response MUST indicate 'analysis_id' field is missing
    
    Breaking Change Detection:
    - Making 'analysis_id' optional would break this contract
    - Accepting requests without 'analysis_id' would break this contract
    - Changing error status code would break this contract
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        # Send request without 'analysis_id' field
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Contract: Missing 'analysis_id' returns 422
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Contract: Error response has 'detail' array
    body = response.json()
    assert "detail" in body
    assert isinstance(body["detail"], list)
    
    # Contract: Error indicates 'analysis_id' field is missing
    analysis_id_errors = [
        err for err in body["detail"] if "analysis_id" in str(err.get("loc", []))
    ]
    assert len(analysis_id_errors) > 0, "Error must indicate 'analysis_id' field is missing"


def test_response_includes_analysis_id_in_body(
    client: TestClient, png_bytes: bytes, mock_adapter: Any
) -> None:
    """T037: Contract test - Response includes analysis_id in body.
    
    Contract Requirement:
    - Successful response (200) MUST include 'analysis_id' at top level
    - analysis_id MUST match the input exactly
    - Type MUST be string
    
    Breaking Change Detection:
    - Removing 'analysis_id' from response would break this contract
    - Moving 'analysis_id' to different location would break this contract
    - Changing 'analysis_id' type would break this contract
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    test_analysis_id = "contract-test-003"
    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
            data={"analysis_id": test_analysis_id},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Contract: Successful response is 200 OK
    assert response.status_code == status.HTTP_200_OK
    
    # Contract: Response is valid JSON
    body = response.json()
    
    # Contract: Response includes 'analysis_id' at top level
    assert "analysis_id" in body, "Response must include 'analysis_id' field"
    
    # Contract: analysis_id is a string
    assert isinstance(body["analysis_id"], str), "'analysis_id' must be a string"
    
    # Contract: analysis_id matches input exactly
    assert body["analysis_id"] == test_analysis_id, "'analysis_id' must match input"


def test_422_response_has_consistent_structure(
    client: TestClient, mock_adapter: Any
) -> None:
    """T038: Contract test - 422 response has consistent structure.
    
    Contract Requirement:
    - 422 response MUST have 'detail' field
    - 'detail' MUST be an array of error objects
    - Each error object MUST have: 'type', 'loc', 'msg' fields
    - 'loc' MUST be an array indicating error location
    
    Breaking Change Detection:
    - Changing error response structure would break this contract
    - Removing required fields would break this contract
    - Changing field types would break this contract
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        # Send request with missing required parameters
        response = client.post("/analyze")
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Contract: Validation errors return 422
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Contract: Response is valid JSON
    body = response.json()
    
    # Contract: Response has 'detail' field
    assert "detail" in body, "422 response must have 'detail' field"
    
    # Contract: 'detail' is an array
    assert isinstance(body["detail"], list), "'detail' must be an array"
    
    # Contract: Each error has required fields
    for error in body["detail"]:
        assert isinstance(error, dict), "Each error must be an object"
        
        # Contract: Error has 'type' field (string)
        assert "type" in error, "Error must have 'type' field"
        assert isinstance(error["type"], str), "'type' must be a string"
        
        # Contract: Error has 'loc' field (array)
        assert "loc" in error, "Error must have 'loc' field"
        assert isinstance(error["loc"], list), "'loc' must be an array"
        
        # Contract: Error has 'msg' field (string)
        assert "msg" in error, "Error must have 'msg' field"
        assert isinstance(error["msg"], str), "'msg' must be a string"


def test_successful_response_structure_contract(
    client: TestClient, png_bytes: bytes, mock_adapter: Any
) -> None:
    """Contract test - Successful response structure per AnalyzeResponse model.
    
    Contract Requirement:
    - Response MUST have: analysis_id, status, report, metadata
    - status MUST be "success"
    - report MUST have: summary, components, risks, recommendations
    - metadata MUST have: model_used, processing_time_ms, input_type
    
    Breaking Change Detection:
    - Removing required fields would break this contract
    - Changing field names would break this contract
    - Changing field types would break this contract
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        response = client.post(
            "/analyze",
            files={"file": ("test.png", png_bytes, "image/png")},
            data={"analysis_id": "contract-test-004"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Contract: Successful response is 200 OK
    assert response.status_code == status.HTTP_200_OK
    
    body = response.json()
    
    # Contract: Top-level fields
    assert "analysis_id" in body, "Response must have 'analysis_id'"
    assert "status" in body, "Response must have 'status'"
    assert "report" in body, "Response must have 'report'"
    assert "metadata" in body, "Response must have 'metadata'"
    
    # Contract: status value
    assert body["status"] == "success", "status must be 'success'"
    
    # Contract: report structure
    report = body["report"]
    assert "summary" in report, "report must have 'summary'"
    assert "components" in report, "report must have 'components'"
    assert "risks" in report, "report must have 'risks'"
    assert "recommendations" in report, "report must have 'recommendations'"
    
    # Contract: report field types
    assert isinstance(report["summary"], str), "summary must be string"
    assert isinstance(report["components"], list), "components must be array"
    assert isinstance(report["risks"], list), "risks must be array"
    assert isinstance(report["recommendations"], list), "recommendations must be array"
    
    # Contract: metadata structure
    metadata = body["metadata"]
    assert "model_used" in metadata, "metadata must have 'model_used'"
    assert "processing_time_ms" in metadata, "metadata must have 'processing_time_ms'"
    assert "input_type" in metadata, "metadata must have 'input_type'"
    
    # Contract: metadata field types
    assert isinstance(metadata["model_used"], str), "model_used must be string"
    assert isinstance(metadata["processing_time_ms"], int), "processing_time_ms must be integer"
    assert isinstance(metadata["input_type"], str), "input_type must be string"


def test_both_required_parameters_missing_contract(
    client: TestClient, mock_adapter: Any
) -> None:
    """Contract test - Multiple missing required parameters return all errors.
    
    Contract Requirement:
    - When multiple required parameters are missing, ALL errors MUST be returned
    - Response MUST NOT fail fast (return only first error)
    - Each missing parameter MUST have its own error entry
    
    Breaking Change Detection:
    - Failing fast (single error) would break this contract
    - Omitting errors would break this contract
    """
    from ai_module.adapters.factory import get_llm_adapter
    from ai_module.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter

    try:
        response = client.post("/analyze")
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    # Contract: Missing parameters return 422
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    body = response.json()
    errors = body["detail"]
    
    # Contract: Multiple errors are returned (not fail-fast)
    assert len(errors) >= 2, "All missing parameters must be reported"
    
    # Contract: Errors for both parameters are present
    error_fields = set()
    for error in errors:
        if "loc" in error and len(error["loc"]) > 0:
            error_fields.add(error["loc"][-1])
    
    assert "file" in error_fields, "Error for 'file' must be present"
    assert "analysis_id" in error_fields, "Error for 'analysis_id' must be present"


def test_api_contract_documentation():
    """Contract documentation test - Documents the complete API contract.
    
    This test serves as executable documentation of the API contract.
    """
    # Contract Definition for POST /analyze
    contract = {
        "endpoint": "/analyze",
        "method": "POST",
        "content_type": "multipart/form-data",
        "required_parameters": {
            "file": {
                "type": "UploadFile",
                "description": "Diagram file to analyze (PNG, JPEG, or PDF)",
                "validation": "Required, no default value",
            },
            "analysis_id": {
                "type": "string",
                "description": "UUID-compatible identifier from orchestrator",
                "validation": "Required (Form(...)), non-empty string",
            },
        },
        "optional_parameters": {
            "context_text": {
                "type": "string | null",
                "description": "Additional context for analysis",
                "validation": "Optional, max length enforced",
            },
        },
        "success_response": {
            "status_code": 200,
            "structure": {
                "analysis_id": "string",
                "status": "'success'",
                "report": {
                    "summary": "string",
                    "components": "array",
                    "risks": "array",
                    "recommendations": "array",
                },
                "metadata": {
                    "model_used": "string",
                    "processing_time_ms": "integer",
                    "input_type": "'image' | 'pdf'",
                    # ... other metadata fields
                },
            },
        },
        "error_response": {
            "status_code": 422,
            "structure": {
                "detail": [
                    {
                        "type": "string",
                        "loc": ["array", "of", "strings"],
                        "msg": "string",
                    }
                ]
            },
        },
    }
    
    # This contract is enforced by all contract tests in this module
    assert contract["endpoint"] == "/analyze"
    assert contract["method"] == "POST"
