"""Unit tests for report_validator module — Phase 5, tasks 5.4.1–5.4.6."""

from __future__ import annotations

import json

import pytest

from ai_module.core.report_validator import validate_and_normalize


def test_validate_and_normalize_accepts_valid_json(valid_report_json: str) -> None:
    report, metadata = validate_and_normalize(valid_report_json)

    assert report.summary.startswith("Arquitetura distribuida")
    assert metadata == {"summary_truncated": False}


def test_validate_and_normalize_normalizes_invalid_severity(valid_report_json: str) -> None:
    data = json.loads(valid_report_json)
    data["risks"][0]["severity"] = "critical"

    report, _ = validate_and_normalize(json.dumps(data))

    assert report.risks[0].severity.value == "medium"


def test_validate_and_normalize_normalizes_invalid_component_type(valid_report_json: str) -> None:
    data = json.loads(valid_report_json)
    data["components"][0]["type"] = "microservice"

    report, _ = validate_and_normalize(json.dumps(data))

    assert report.components[0].type.value == "unknown"


def test_validate_and_normalize_truncates_long_summary(valid_report_json: str) -> None:
    data = json.loads(valid_report_json)
    data["summary"] = "x" * 600

    report, metadata = validate_and_normalize(json.dumps(data))

    assert len(report.summary) == 500
    assert metadata == {"summary_truncated": True}


def test_validate_and_normalize_raises_schema_error_when_components_missing(
    valid_report_json: str,
) -> None:
    data = json.loads(valid_report_json)
    data.pop("components")

    with pytest.raises(ValueError, match="SCHEMA_ERROR"):
        validate_and_normalize(json.dumps(data))


def test_validate_and_normalize_raises_json_parse_error() -> None:
    with pytest.raises(ValueError, match="JSON_PARSE_ERROR"):
        validate_and_normalize("não é json")