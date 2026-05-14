"""Contract tests for queue message schemas (FUN-009).

Verifies that :class:`~ai_module.models.queue.QueueAnalysisRequest`,
:class:`~ai_module.models.queue.QueueAnalysisResponse`, and
:class:`~ai_module.models.queue.QueueErrorResponse` conform exactly to the
spec section 4.2 queue contract.
"""

from __future__ import annotations

import base64
import uuid

import pytest
from pydantic import ValidationError

from ai_module.models.queue import (
    QueueAnalysisRequest,
    QueueAnalysisResponse,
    QueueErrorResponse,
)
from ai_module.models.report import Component, Report, ReportMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_b64() -> str:
    return base64.b64encode(b"fake-bytes").decode()


def _valid_report() -> Report:
    return Report(
        summary="Architecture summary",
        components=[Component(name="Service A", type="service", description="Core service")],
    )


def _valid_metadata() -> ReportMetadata:
    return ReportMetadata(
        model_used="gpt-4o",
        processing_time_ms=100,
        input_type="image",
    )


# ---------------------------------------------------------------------------
# QueueAnalysisRequest
# ---------------------------------------------------------------------------


class TestQueueAnalysisRequestContract:
    def test_valid_minimal_request(self) -> None:
        req = QueueAnalysisRequest(
            analysis_id=str(uuid.uuid4()),
            file_bytes_b64=_valid_b64(),
            file_name="diagram.png",
        )
        assert req.context_text is None

    def test_valid_request_with_context_text(self) -> None:
        req = QueueAnalysisRequest(
            analysis_id=str(uuid.uuid4()),
            file_bytes_b64=_valid_b64(),
            file_name="diagram.png",
            context_text="Additional context about the diagram",
        )
        assert req.context_text == "Additional context about the diagram"

    def test_analysis_id_is_required(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            QueueAnalysisRequest(
                file_bytes_b64=_valid_b64(),
                file_name="diagram.png",
            )
        errors = exc_info.value.errors()
        fields = [e["loc"][0] for e in errors]
        assert "analysis_id" in fields

    def test_file_bytes_b64_is_required(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            QueueAnalysisRequest(
                analysis_id=str(uuid.uuid4()),
                file_name="diagram.png",
            )
        errors = exc_info.value.errors()
        fields = [e["loc"][0] for e in errors]
        assert "file_bytes_b64" in fields

    def test_file_name_is_required(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            QueueAnalysisRequest(
                analysis_id=str(uuid.uuid4()),
                file_bytes_b64=_valid_b64(),
            )
        errors = exc_info.value.errors()
        fields = [e["loc"][0] for e in errors]
        assert "file_name" in fields

    def test_analysis_id_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            QueueAnalysisRequest(
                analysis_id="",
                file_bytes_b64=_valid_b64(),
                file_name="diagram.png",
            )

    def test_context_text_defaults_to_none(self) -> None:
        req = QueueAnalysisRequest(
            analysis_id=str(uuid.uuid4()),
            file_bytes_b64=_valid_b64(),
            file_name="diagram.png",
        )
        assert req.context_text is None

    def test_model_serialises_to_dict(self) -> None:
        req = QueueAnalysisRequest(
            analysis_id="abc-123",
            file_bytes_b64=_valid_b64(),
            file_name="arch.png",
        )
        data = req.model_dump()
        assert data["analysis_id"] == "abc-123"
        assert "file_bytes_b64" in data
        assert "file_name" in data
        assert "context_text" in data


# ---------------------------------------------------------------------------
# QueueAnalysisResponse
# ---------------------------------------------------------------------------


class TestQueueAnalysisResponseContract:
    def test_valid_success_response(self) -> None:
        resp = QueueAnalysisResponse(
            analysis_id=str(uuid.uuid4()),
            report=_valid_report(),
            metadata=_valid_metadata(),
        )
        assert resp.status == "success"

    def test_status_defaults_to_success(self) -> None:
        resp = QueueAnalysisResponse(
            analysis_id="id-1",
            report=_valid_report(),
            metadata=_valid_metadata(),
        )
        assert resp.status == "success"

    def test_analysis_id_is_required(self) -> None:
        with pytest.raises(ValidationError):
            QueueAnalysisResponse(
                report=_valid_report(),
                metadata=_valid_metadata(),
            )

    def test_report_is_required(self) -> None:
        with pytest.raises(ValidationError):
            QueueAnalysisResponse(
                analysis_id="id-1",
                metadata=_valid_metadata(),
            )

    def test_metadata_is_required(self) -> None:
        with pytest.raises(ValidationError):
            QueueAnalysisResponse(
                analysis_id="id-1",
                report=_valid_report(),
            )

    def test_model_serialises_to_dict(self) -> None:
        resp = QueueAnalysisResponse(
            analysis_id="id-1",
            report=_valid_report(),
            metadata=_valid_metadata(),
        )
        data = resp.model_dump()
        assert data["status"] == "success"
        assert "report" in data
        assert "metadata" in data


# ---------------------------------------------------------------------------
# QueueErrorResponse
# ---------------------------------------------------------------------------


class TestQueueErrorResponseContract:
    def test_valid_error_response(self) -> None:
        err = QueueErrorResponse(
            analysis_id="id-1",
            error_code="INVALID_INPUT",
            message="File format not supported",
        )
        assert err.status == "error"

    def test_status_defaults_to_error(self) -> None:
        err = QueueErrorResponse(
            analysis_id="id-1",
            error_code="TIMEOUT",
            message="Pipeline timed out",
        )
        assert err.status == "error"

    def test_analysis_id_is_required(self) -> None:
        with pytest.raises(ValidationError):
            QueueErrorResponse(
                error_code="TIMEOUT",
                error_message="timed out",
            )

    def test_error_code_is_required(self) -> None:
        with pytest.raises(ValidationError):
            QueueErrorResponse(
                analysis_id="id-1",
                error_message="timed out",
            )

    def test_error_message_is_required(self) -> None:
        with pytest.raises(ValidationError):
            QueueErrorResponse(
                analysis_id="id-1",
                error_code="TIMEOUT",
            )

    def test_model_serialises_to_dict(self) -> None:
        err = QueueErrorResponse(
            analysis_id="id-1",
            error_code="AI_FAILURE",
            message="Model returned invalid output",
        )
        data = err.model_dump()
        assert data["status"] == "error"
        assert data["error_code"] == "AI_FAILURE"
        assert "message" in data
