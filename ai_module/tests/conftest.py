from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai_module.core.exceptions import LLMCallError
from ai_module.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (10, 10), color=(255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (10, 10), color=(0, 255, 0)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page()
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def corrupted_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


@pytest.fixture
def valid_report_json() -> str:
    return json.dumps(
        {
            "summary": "Arquitetura distribuida com componentes principais identificados.",
            "components": [
                {
                    "name": "api-service",
                    "type": "service",
                    "description": "Servico principal de API.",
                }
            ],
            "risks": [
                {
                    "title": "Single point of failure",
                    "severity": "high",
                    "description": "Apenas uma instancia do servico foi identificada.",
                    "affected_components": ["api-service"],
                }
            ],
            "recommendations": [
                {
                    "title": "Add redundancy",
                    "priority": "high",
                    "description": "Adicionar replicacao para aumentar resiliencia.",
                }
            ],
        }
    )


@pytest.fixture
def mock_adapter(valid_report_json: str) -> SimpleNamespace:
    return SimpleNamespace(analyze=AsyncMock(return_value=valid_report_json))


@pytest.fixture
def mock_adapter_always_fails() -> SimpleNamespace:
    return SimpleNamespace(analyze=AsyncMock(side_effect=LLMCallError("provider failure")))


@pytest.fixture
def mock_adapter_invalid_json() -> SimpleNamespace:
    return SimpleNamespace(analyze=AsyncMock(return_value="não é json"))
