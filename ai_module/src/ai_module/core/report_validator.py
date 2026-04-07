"""Parsing, enum normalisation, and schema validation for raw LLM JSON responses."""

from __future__ import annotations

import json

from ai_module.models.report import (
    ComponentType,
    Priority,
    Report,
    Severity,
)


def _normalize_enums(data: dict) -> dict:
    valid_types = {e.value for e in ComponentType}
    valid_severities = {e.value for e in Severity}
    valid_priorities = {e.value for e in Priority}

    for component in data.get("components", []):
        if component.get("type") not in valid_types:
            component["type"] = ComponentType.UNKNOWN.value

    for risk in data.get("risks", []):
        if risk.get("severity") not in valid_severities:
            risk["severity"] = Severity.MEDIUM.value

    for rec in data.get("recommendations", []):
        if rec.get("priority") not in valid_priorities:
            rec["priority"] = Priority.MEDIUM.value

    return data


def _truncate_summary(data: dict) -> tuple[dict, bool]:
    summary = data.get("summary", "")
    if len(summary) > 500:
        data["summary"] = summary[:500]
        return data, True
    return data, False


def validate_and_normalize(raw_response: str) -> tuple[Report, dict]:
    """Parse, normalise enums, and validate the JSON returned by the LLM.

    Returns:
        (Report, metadata_flags) onde metadata_flags contém {"summary_truncated": bool}

    Raises:
        ValueError: com prefixo JSON_PARSE_ERROR ou SCHEMA_ERROR
    """
    try:
        data: dict = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON_PARSE_ERROR: {e}") from e

    data = _normalize_enums(data)
    data, summary_truncated = _truncate_summary(data)

    try:
        report = Report.model_validate(data)
    except Exception as e:
        raise ValueError(f"SCHEMA_ERROR: {e}") from e

    return report, {"summary_truncated": summary_truncated}