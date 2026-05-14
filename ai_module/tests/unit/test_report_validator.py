"""Unit tests for report_validator module — Phase 5, tasks 5.4.1–5.4.6."""

from __future__ import annotations

import json

import pytest  # type: ignore

from ai_module.core.report_validator import detect_conflict, validate_and_normalize


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


def test_detect_conflict_returns_no_conflict_when_context_matches_component(
    valid_report_json: str,
) -> None:
    report, _ = validate_and_normalize(valid_report_json)

    conflict_detected, conflict_decision = detect_conflict(
        "api-service recebe trafego e processa requisicoes",
        report,
    )

    assert conflict_detected is False
    assert conflict_decision == "NO_CONFLICT"


def test_detect_conflict_returns_diagram_first_for_conflicting_context(
    valid_report_json: str,
) -> None:
    report, _ = validate_and_normalize(valid_report_json)

    conflict_detected, conflict_decision = detect_conflict(
        "mainframe legado processo batch noturno fila cassandra externo",
        report,
    )

    assert conflict_detected is True
    assert conflict_decision == "DIAGRAM_FIRST"


# ---------------------------------------------------------------------------
# T024 — Markdown fence stripping
# ---------------------------------------------------------------------------


def test_validate_and_normalize_accepts_json_fenced_with_backticks(
    valid_report_json: str,
) -> None:
    """LLM response wrapped in ```json ... ``` fences is correctly parsed (T021)."""
    fenced = f"```json\n{valid_report_json}\n```"
    report, _ = validate_and_normalize(fenced)

    assert report.summary.startswith("Arquitetura distribuida")


def test_validate_and_normalize_accepts_plain_fence_without_language_tag(
    valid_report_json: str,
) -> None:
    """LLM response wrapped in ``` ... ``` (no language) is correctly parsed."""
    fenced = f"```\n{valid_report_json}\n```"
    report, _ = validate_and_normalize(fenced)

    assert len(report.components) > 0


def test_validate_and_normalize_strips_fence_with_leading_trailing_whitespace(
    valid_report_json: str,
) -> None:
    """Whitespace around fenced block is stripped before parse."""
    fenced = f"   ```json\n{valid_report_json}\n```   "
    report, _ = validate_and_normalize(fenced)

    assert report is not None


def test_validate_and_normalize_raises_on_fenced_invalid_json() -> None:
    """Fenced but invalid JSON still raises JSON_PARSE_ERROR."""
    fenced = "```json\nnot valid json {{{\n```"
    with pytest.raises(ValueError, match="JSON_PARSE_ERROR"):
        validate_and_normalize(fenced)


def test_validate_and_normalize_enum_normalization_works_inside_fenced_json(
    valid_report_json: str,
) -> None:
    """Enum normalization still applies after fence stripping (T022)."""
    data = json.loads(valid_report_json)
    data["components"][0]["type"] = "microservice"  # invalid type
    fenced = f"```json\n{json.dumps(data)}\n```"

    report, _ = validate_and_normalize(fenced)

    assert report.components[0].type.value == "unknown"
