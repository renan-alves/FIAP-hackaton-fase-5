"""Contract tests for FUN-010 result message schemas.

Validates that :class:`~ai_module.models.queue.QueueAnalysisResponse` and
:class:`~ai_module.models.queue.QueueErrorResponse` serialise to JSON
structures that conform to the contracts defined in
``specs/FUN-010-contracts/success-result.json`` and
``specs/FUN-010-contracts/error-result.json``.

Validation strategy
-------------------
Tests check the serialised JSON dict against the key constraints declared in
the JSON Schema files (required fields, const values, type constraints) without
requiring an external ``jsonschema`` dependency.
"""

from __future__ import annotations

import json
import pathlib
import uuid

import pytest

from ai_module.models.queue import QueueAnalysisResponse, QueueErrorResponse
from ai_module.models.report import Component, Report, ReportMetadata

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CONTRACTS_DIR = (
    pathlib.Path(__file__).parents[3] / "specs" / "FUN-010-contracts"
)
_SUCCESS_SCHEMA_PATH = _CONTRACTS_DIR / "success-result.json"
_ERROR_SCHEMA_PATH = _CONTRACTS_DIR / "error-result.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANALYSIS_ID = str(uuid.uuid4())


def _make_success_response() -> QueueAnalysisResponse:
    return QueueAnalysisResponse(
        analysis_id=_ANALYSIS_ID,
        status="success",
        report=Report(
            summary="High-level architecture overview with microservices pattern.",
            components=[
                Component(name="API Gateway", type="gateway", description="Entry point"),
                Component(name="Auth Service", type="service", description="Handles auth"),
            ],
        ),
        metadata=ReportMetadata(
            model_used="gpt-4o",
            processing_time_ms=350,
            input_type="image",
        ),
    )


def _make_error_response() -> QueueErrorResponse:
    return QueueErrorResponse(
        analysis_id=_ANALYSIS_ID,
        status="error",
        error_code="AI_FAILURE",
        message="AI analysis failed after 3 attempts",
    )


# ---------------------------------------------------------------------------
# Fixture: load contract schema files
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def success_schema() -> dict:
    return json.loads(_SUCCESS_SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def error_schema() -> dict:
    return json.loads(_ERROR_SCHEMA_PATH.read_text())


# ---------------------------------------------------------------------------
# Helper: serialise to JSON dict
# ---------------------------------------------------------------------------


def _to_dict(model) -> dict:
    return json.loads(model.model_dump_json())


# ---------------------------------------------------------------------------
# Contract: success-result.json
# ---------------------------------------------------------------------------


class TestSuccessResultContract:
    """QueueAnalysisResponse must conform to success-result.json."""

    def test_schema_file_exists(self):
        """Contract schema file must exist in specs/FUN-010-contracts/."""
        assert _SUCCESS_SCHEMA_PATH.exists(), (
            f"Missing contract file: {_SUCCESS_SCHEMA_PATH}"
        )

    def test_required_top_level_fields(self, success_schema: dict):
        """Schema declares analysis_id, status, report, metadata as required."""
        required = set(success_schema["required"])
        assert required == {"analysis_id", "status", "report", "metadata"}

    def test_serialises_required_fields(self):
        """Success response includes all required top-level fields."""
        data = _to_dict(_make_success_response())
        assert "analysis_id" in data
        assert "status" in data
        assert "report" in data
        assert "metadata" in data

    def test_status_is_success(self):
        """status field must be the literal string 'success'."""
        data = _to_dict(_make_success_response())
        assert data["status"] == "success"

    def test_analysis_id_is_non_empty_string(self):
        """analysis_id must be a non-empty string."""
        data = _to_dict(_make_success_response())
        assert isinstance(data["analysis_id"], str)
        assert len(data["analysis_id"]) >= 1

    def test_report_required_fields(self):
        """report must contain summary and components."""
        data = _to_dict(_make_success_response())
        report = data["report"]
        assert "summary" in report
        assert "components" in report

    def test_report_summary_length(self):
        """summary must be at least 10 characters (schema minLength=10)."""
        data = _to_dict(_make_success_response())
        assert len(data["report"]["summary"]) >= 10

    def test_components_non_empty(self):
        """components array must have at least one item."""
        data = _to_dict(_make_success_response())
        assert len(data["report"]["components"]) >= 1

    def test_component_required_fields(self):
        """Each component must contain name, type, and description."""
        data = _to_dict(_make_success_response())
        for component in data["report"]["components"]:
            assert "name" in component
            assert "type" in component
            assert "description" in component

    def test_component_type_is_valid_enum(self):
        """Component type must be a valid ComponentType enum value."""
        valid_types = {"service", "database", "queue", "gateway", "cache", "external", "unknown"}
        data = _to_dict(_make_success_response())
        for component in data["report"]["components"]:
            assert component["type"] in valid_types

    def test_metadata_required_fields(self):
        """metadata must contain model_used, processing_time_ms, input_type."""
        data = _to_dict(_make_success_response())
        metadata = data["metadata"]
        assert "model_used" in metadata
        assert "processing_time_ms" in metadata
        assert "input_type" in metadata

    def test_metadata_processing_time_is_positive(self):
        """processing_time_ms must be a non-negative number."""
        data = _to_dict(_make_success_response())
        assert data["metadata"]["processing_time_ms"] >= 0

    def test_json_is_valid(self):
        """Serialised JSON must be parseable."""
        raw_json = _make_success_response().model_dump_json()
        parsed = json.loads(raw_json)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Contract: error-result.json
# ---------------------------------------------------------------------------


class TestErrorResultContract:
    """QueueErrorResponse must conform to error-result.json."""

    def test_schema_file_exists(self):
        """Contract schema file must exist in specs/FUN-010-contracts/."""
        assert _ERROR_SCHEMA_PATH.exists(), (
            f"Missing contract file: {_ERROR_SCHEMA_PATH}"
        )

    def test_required_top_level_fields(self, error_schema: dict):
        """Schema declares analysis_id, status, error_code, message as required."""
        required = set(error_schema["required"])
        assert required == {"analysis_id", "status", "error_code", "message"}

    def test_serialises_required_fields(self):
        """Error response includes all required top-level fields."""
        data = _to_dict(_make_error_response())
        assert "analysis_id" in data
        assert "status" in data
        assert "error_code" in data
        assert "message" in data

    def test_status_is_error(self):
        """status field must be the literal string 'error'."""
        data = _to_dict(_make_error_response())
        assert data["status"] == "error"

    def test_analysis_id_is_non_empty_string(self):
        """analysis_id must be a non-empty string."""
        data = _to_dict(_make_error_response())
        assert isinstance(data["analysis_id"], str)
        assert len(data["analysis_id"]) >= 1

    def test_error_code_is_non_empty_string(self):
        """error_code must be a non-empty string."""
        data = _to_dict(_make_error_response())
        assert isinstance(data["error_code"], str)
        assert len(data["error_code"]) >= 1

    def test_message_is_non_empty_string(self):
        """message must be a non-empty human-readable string."""
        data = _to_dict(_make_error_response())
        assert isinstance(data["message"], str)
        assert len(data["message"]) >= 1

    def test_known_error_codes_are_serialisable(self):
        """All known error codes must produce valid serialised responses."""
        known_codes = [
            "UNSUPPORTED_FORMAT",
            "INVALID_INPUT",
            "AI_FAILURE",
            "AI_TIMEOUT",
            "INTERNAL_ERROR",
        ]
        for code in known_codes:
            response = QueueErrorResponse(
                analysis_id=_ANALYSIS_ID,
                status="error",
                error_code=code,
                message=f"Error: {code}",
            )
            data = _to_dict(response)
            assert data["error_code"] == code
            assert data["status"] == "error"

    def test_json_is_valid(self):
        """Serialised JSON must be parseable."""
        raw_json = _make_error_response().model_dump_json()
        parsed = json.loads(raw_json)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Cross-contract: no field leakage
# ---------------------------------------------------------------------------


class TestContractIsolation:
    """Success and error contracts must not leak each other's fields."""

    def test_success_response_has_no_error_code(self):
        """Success response must not include error_code."""
        data = _to_dict(_make_success_response())
        assert "error_code" not in data
        assert "message" not in data

    def test_error_response_has_no_report(self):
        """Error response must not include report or metadata."""
        data = _to_dict(_make_error_response())
        assert "report" not in data
        assert "metadata" not in data
