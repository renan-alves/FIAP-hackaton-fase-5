"""Integration tests for API routes — Phase 2, tasks 2.4.2–2.4.6."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ai_module.adapters.factory import get_llm_adapter
from ai_module.core.exceptions import AIFailureError
from ai_module.main import app


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_contains_llm_provider(client: TestClient) -> None:
    response = client.get("/health")

    assert "llm_provider" in response.json()


def test_analyze_without_analysis_id_returns_422(client: TestClient) -> None:
    response = client.post(
        "/analyze",
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )

    assert response.status_code == 422


def test_analyze_without_file_returns_422(client: TestClient) -> None:
    response = client.post("/analyze", data={"analysis_id": "test-id"})

    assert response.status_code == 422


def test_analyze_openapi_does_not_expose_llm_provider_as_input(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == status.HTTP_200_OK

    schema = response.json()
    operation = schema["paths"]["/analyze"]["post"]
    schema_content = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    request_body_schema_ref = schema_content["$ref"]
    request_body_schema_name = request_body_schema_ref.split("/")[-1]
    request_body_schema = schema["components"]["schemas"][request_body_schema_name]

    assert "llm_provider" not in request_body_schema.get("properties", {})
    assert "context_text" in request_body_schema.get("properties", {})


def test_analyze_png_returns_success_response(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "analysis-png"},
        files={"file": ("img.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["analysis_id"] == "analysis-png"
    assert body["status"] == "success"
    assert body["metadata"]["input_type"] == "image"


def test_analyze_real_diagram_png_returns_unsupported_format_error(
    client: TestClient,
    real_diagram_png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "analysis-real-diagram"},
        files={"file": ("diagrama_caso_usuario.png", real_diagram_png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["analysis_id"] == "analysis-real-diagram"
    assert body["status"] == "error"
    assert body["error_code"] == "UNSUPPORTED_FORMAT"
    assert mock_adapter.analyze.await_count == 0


def test_analyze_pdf_returns_success_response(
    client: TestClient,
    pdf_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "analysis-pdf"},
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["analysis_id"] == "analysis-pdf"
    assert body["metadata"]["input_type"] == "pdf"


def test_analyze_txt_returns_unsupported_format_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_adapter = SimpleNamespace(analyze=AsyncMock())
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "analysis-txt"},
        files={"file": ("arquivo.txt", b"texto qualquer", "text/plain")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["status"] == "error"
    assert body["error_code"] == "UNSUPPORTED_FORMAT"
    assert mock_adapter.analyze.await_count == 0


def test_analyze_corrupted_png_returns_invalid_input_error(
    client: TestClient,
    corrupted_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_adapter = SimpleNamespace(analyze=AsyncMock())
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "analysis-invalid"},
        files={"file": ("img.png", corrupted_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["analysis_id"] == "analysis-invalid"
    assert body["error_code"] == "INVALID_INPUT"
    assert mock_adapter.analyze.await_count == 0


def test_analyze_returns_ai_failure_error(
    client: TestClient,
    png_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing_adapter = SimpleNamespace(
        analyze=AsyncMock(side_effect=AIFailureError("Falha após todas as tentativas"))
    )
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: failing_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "analysis-failure"},
        files={"file": ("img.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    body = response.json()
    assert body["analysis_id"] == "analysis-failure"
    assert body["error_code"] == "AI_FAILURE"


def test_analyze_context_text_over_1000_returns_422(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "analysis-context-limit", "context_text": "x" * 1001},
        files={"file": ("img.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_analyze_non_uuid_analysis_id_is_accepted(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per GUD-006: analysis_id is a plain string — any format must be accepted."""
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    for analysis_id in ("plain-string-id", "12345", "order-abc-XYZ"):
        response = client.post(
            "/analyze",
            data={"analysis_id": analysis_id},
            files={"file": ("img.png", png_bytes, "image/png")},
        )

        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200 for analysis_id={analysis_id!r}, got {response.status_code}"
        )
        assert response.json()["analysis_id"] == analysis_id
