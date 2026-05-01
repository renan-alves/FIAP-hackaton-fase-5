"""Integration tests for /analyze endpoint with PDF inputs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ai_module.adapters.factory import get_llm_adapter
from ai_module.main import app


def test_analyze_pdf_returns_success(
    client: TestClient,
    pdf_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "pdf-test-01"},
        files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["analysis_id"] == "pdf-test-01"
    assert body["status"] == "success"
    assert isinstance(body["report"]["summary"], str)
    assert len(body["report"]["summary"]) > 0


def test_analyze_pdf_metadata_input_type_is_pdf(
    client: TestClient,
    pdf_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "pdf-test-02"},
        files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["metadata"]["input_type"] == "pdf"


def test_analyze_pdf_response_contains_components(
    client: TestClient,
    pdf_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "pdf-test-03"},
        files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body["report"]["components"], list)
    assert len(body["report"]["components"]) > 0


def test_analyze_pdf_response_contains_risks(
    client: TestClient,
    pdf_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "pdf-test-04"},
        files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body["report"]["risks"], list)
    assert len(body["report"]["risks"]) > 0


def test_analyze_pdf_response_contains_recommendations(
    client: TestClient,
    pdf_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "pdf-test-05"},
        files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body["report"]["recommendations"], list)
    assert len(body["report"]["recommendations"]) > 0


def test_analyze_corrupted_pdf_returns_422(
    client: TestClient,
    corrupted_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "pdf-test-06"},
        files={"file": ("corrupt.pdf", corrupted_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_analyze_pdf_missing_analysis_id_returns_422(
    client: TestClient,
    pdf_bytes: bytes,
) -> None:
    response = client.post(
        "/analyze",
        files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
