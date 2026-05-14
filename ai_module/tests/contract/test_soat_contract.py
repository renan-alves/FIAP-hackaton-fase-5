"""Contract tests between AI Module and SOAT orchestrator.

Validates the HTTP contract per spec v2.1.
Must pass before coordinated deployment (GUD-007).

Run with:
    uv run pytest tests/contract/ -v
"""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ai_module.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestAnalyzeSuccessContract:
    """Spec §3.1 — Success response structure per v2.1."""

    def test_success_response_has_required_top_level_fields(
        self, client: TestClient, mock_adapter: object
    ) -> None:
        """analysis_id, status, report, metadata must all be present."""
        from ai_module.adapters.factory import get_llm_adapter

        app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter
        try:
            resp = client.post(
                "/analyze",
                files={"file": ("diagram.png", _minimal_png(), "image/png")},
                data={"analysis_id": "contract-test-001"},
            )
        finally:
            app.dependency_overrides.pop(get_llm_adapter, None)

        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        assert "analysis_id" in body
        assert "status" in body
        assert "report" in body
        assert "metadata" in body

    def test_report_nested_structure(self, client: TestClient, mock_adapter: object) -> None:
        """report must contain summary, components, risks, recommendations."""
        from ai_module.adapters.factory import get_llm_adapter

        app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter
        try:
            resp = client.post(
                "/analyze",
                files={"file": ("diagram.png", _minimal_png(), "image/png")},
                data={"analysis_id": "contract-test-002"},
            )
        finally:
            app.dependency_overrides.pop(get_llm_adapter, None)

        report = resp.json()["report"]
        assert "summary" in report
        assert "components" in report
        assert "risks" in report
        assert "recommendations" in report

    def test_metadata_contains_required_fields(
        self, client: TestClient, mock_adapter: object
    ) -> None:
        """metadata must include model_used, processing_time_ms, input_type,
        downsampling_applied."""
        from ai_module.adapters.factory import get_llm_adapter

        app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter
        try:
            resp = client.post(
                "/analyze",
                files={"file": ("diagram.png", _minimal_png(), "image/png")},
                data={"analysis_id": "contract-test-003"},
            )
        finally:
            app.dependency_overrides.pop(get_llm_adapter, None)

        metadata = resp.json()["metadata"]
        assert "model_used" in metadata
        assert "processing_time_ms" in metadata
        assert "input_type" in metadata
        assert "downsampling_applied" in metadata

    def test_analysis_id_echoed_back(self, client: TestClient, mock_adapter: object) -> None:
        """analysis_id in response must match the value sent (GUD-006: any string format)."""
        from ai_module.adapters.factory import get_llm_adapter

        sent_id = "soat-plain-string-id-xyz"
        app.dependency_overrides[get_llm_adapter] = lambda: mock_adapter
        try:
            resp = client.post(
                "/analyze",
                files={"file": ("diagram.png", _minimal_png(), "image/png")},
                data={"analysis_id": sent_id},
            )
        finally:
            app.dependency_overrides.pop(get_llm_adapter, None)

        assert resp.json()["analysis_id"] == sent_id


class TestAnalyzeErrorContract:
    """Spec §9 — Error response codes per v2.1."""

    def test_timeout_returns_504_with_ai_timeout_code(self, client: TestClient) -> None:
        """Timeout must return 504 with error_code='AI_TIMEOUT' (not AI_FAILURE)."""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from ai_module.adapters.factory import get_llm_adapter
        from ai_module.core.exceptions import LLMTimeoutError

        adapter = SimpleNamespace(analyze=AsyncMock(side_effect=LLMTimeoutError("timeout")))
        app.dependency_overrides[get_llm_adapter] = lambda: adapter
        try:
            resp = client.post(
                "/analyze",
                files={"file": ("diagram.png", _minimal_png(), "image/png")},
                data={"analysis_id": "contract-timeout-001"},
            )
        finally:
            app.dependency_overrides.pop(get_llm_adapter, None)

        assert resp.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        body = resp.json()
        assert body["status"] == "error"
        assert body["error_code"] == "AI_TIMEOUT"

    def test_ai_failure_returns_500_with_ai_failure_code(self, client: TestClient) -> None:
        """Unrecoverable LLM failure must return 500 with error_code='AI_FAILURE'."""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from ai_module.adapters.factory import get_llm_adapter
        from ai_module.core.exceptions import AIFailureError

        adapter = SimpleNamespace(
            analyze=AsyncMock(side_effect=AIFailureError("all retries exhausted"))
        )
        app.dependency_overrides[get_llm_adapter] = lambda: adapter
        try:
            resp = client.post(
                "/analyze",
                files={"file": ("diagram.png", _minimal_png(), "image/png")},
                data={"analysis_id": "contract-failure-001"},
            )
        finally:
            app.dependency_overrides.pop(get_llm_adapter, None)

        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        body = resp.json()
        assert body["status"] == "error"
        assert body["error_code"] == "AI_FAILURE"

    def test_unsupported_format_returns_422_with_unsupported_format_code(
        self, client: TestClient
    ) -> None:
        """Non-image/PDF file must return 422 with error_code='UNSUPPORTED_FORMAT'."""
        resp = client.post(
            "/analyze",
            files={"file": ("doc.txt", b"plain text content", "text/plain")},
            data={"analysis_id": "contract-format-001"},
        )

        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = resp.json()
        assert body["status"] == "error"
        assert body["error_code"] == "UNSUPPORTED_FORMAT"

    def test_error_response_always_echoes_analysis_id(self, client: TestClient) -> None:
        """All error responses must include the original analysis_id."""
        resp = client.post(
            "/analyze",
            files={"file": ("doc.txt", b"plain text", "text/plain")},
            data={"analysis_id": "contract-error-echo-001"},
        )

        assert resp.json()["analysis_id"] == "contract-error-echo-001"

    def test_unhandled_exception_returns_500_with_internal_error_code(
        self, client: TestClient
    ) -> None:
        """Unhandled/unexpected exceptions must return 500 with error_code='INTERNAL_ERROR'."""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from ai_module.adapters.factory import get_llm_adapter

        adapter = SimpleNamespace(analyze=AsyncMock(side_effect=RuntimeError("unexpected")))
        app.dependency_overrides[get_llm_adapter] = lambda: adapter
        try:
            resp = client.post(
                "/analyze",
                files={"file": ("diagram.png", _minimal_png(), "image/png")},
                data={"analysis_id": "contract-internal-001"},
            )
        finally:
            app.dependency_overrides.pop(get_llm_adapter, None)

        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        body = resp.json()
        assert body["status"] == "error"
        assert body["error_code"] == "INTERNAL_ERROR"
        assert body["analysis_id"] == "contract-internal-001"


class TestHealthContract:
    """Spec §3.3 — GET /health response contract."""

    def test_healthy_returns_200_with_top_level_fields(self, client: TestClient) -> None:
        """Healthy service returns 200 with top-level status/version/llm_provider fields."""
        import ai_module.core.state as _state

        original = _state._service_healthy
        _state._service_healthy = True
        try:
            resp = client.get("/health")
        finally:
            _state._service_healthy = original

        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        assert body["status"] == "healthy"
        assert "version" in body
        assert "llm_provider" in body
        assert "queue_connected" in body
        # Body must be top-level — no "detail" wrapper
        assert "detail" not in body

    def test_degraded_returns_503_with_top_level_fields(self, client: TestClient) -> None:
        """Degraded service returns 503 with top-level status (not nested under 'detail')."""
        import ai_module.core.state as _state

        original = _state._service_healthy
        _state._service_healthy = False
        try:
            resp = client.get("/health")
        finally:
            _state._service_healthy = original

        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        body = resp.json()
        assert body["status"] == "degraded"
        assert "version" in body
        assert "llm_provider" in body
        assert "queue_connected" in body
        # Body must be top-level — HTTPException wraps under "detail", JSONResponse does not
        assert "detail" not in body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_png() -> bytes:
    """Return a minimal valid PNG for contract tests (no PIL dependency)."""
    import io

    from PIL import Image

    img = Image.new("RGB", (10, 10), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
