"""Integration tests for /analyze endpoint with image inputs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ai_module.adapters.factory import get_llm_adapter
from ai_module.main import app


def test_analyze_png_returns_success(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-01"},
        files={"file": ("diagram.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["analysis_id"] == "img-test-01"
    assert body["status"] == "success"
    assert isinstance(body["report"]["summary"], str)
    assert len(body["report"]["summary"]) > 0


def test_analyze_jpeg_returns_success(
    client: TestClient,
    jpeg_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-02"},
        files={"file": ("diagram.jpg", jpeg_bytes, "image/jpeg")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["analysis_id"] == "img-test-02"
    assert body["status"] == "success"


def test_analyze_image_response_contains_components(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-03"},
        files={"file": ("arch.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body["report"]["components"], list)
    assert len(body["report"]["components"]) > 0
    component = body["report"]["components"][0]
    assert "name" in component
    assert "type" in component


def test_analyze_image_response_contains_risks(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-04"},
        files={"file": ("arch.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body["report"]["risks"], list)
    assert len(body["report"]["risks"]) > 0
    risk = body["report"]["risks"][0]
    assert "title" in risk
    assert "severity" in risk


def test_analyze_image_response_contains_recommendations(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-05"},
        files={"file": ("arch.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body["report"]["recommendations"], list)
    assert len(body["report"]["recommendations"]) > 0
    rec = body["report"]["recommendations"][0]
    assert "title" in rec
    assert "priority" in rec


def test_analyze_corrupted_image_returns_422(
    client: TestClient,
    corrupted_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-06"},
        files={"file": ("corrupt.png", corrupted_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_analyze_missing_analysis_id_returns_422(
    client: TestClient,
    png_bytes: bytes,
) -> None:
    response = client.post(
        "/analyze",
        files={"file": ("diagram.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_analyze_metadata_input_type_is_image(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-07"},
        files={"file": ("arch.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["metadata"]["input_type"] == "image"


def test_analyze_with_context_text_returns_metadata_flags(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_text = "api-service recebe trafego e valida autenticacao"
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-08", "context_text": context_text},
        files={"file": ("arch.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["metadata"]["context_text_provided"] is True
    assert body["metadata"]["context_text_length"] == len(context_text)
    assert body["metadata"]["conflict_detected"] is False
    assert body["metadata"]["conflict_decision"] == "NO_CONFLICT"
    assert body["metadata"]["conflict_policy"] == "DIAGRAM_FIRST"


def test_analyze_with_context_text_too_long_returns_422(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)
    too_long_context = "x" * 1001

    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-09", "context_text": too_long_context},
        files={"file": ("arch.png", png_bytes, "image/png")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
