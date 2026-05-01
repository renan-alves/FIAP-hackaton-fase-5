"""Parsing, enum normalisation, and schema validation for raw LLM JSON responses."""

from __future__ import annotations

import json
from typing import Any, cast

from ai_module.core.logger import get_logger
from ai_module.core.settings import settings
from ai_module.models.report import (
    ComponentType,
    Priority,
    Report,
    Severity,
)

logger = get_logger(__name__, level=settings.LOG_LEVEL)


def _normalize_component_type(value: str) -> str:
    """
    Normalize os valores do tipo de componente, atribuindo o valor ComponentType.
    UNKNOWN aos desconhecidos.
    """
    valid_types = {e.value for e in ComponentType}
    return value if value in valid_types else ComponentType.UNKNOWN.value


def _normalize_severity(value: str) -> str:
    """
    Normalize os valores de severidade, atribuindo o valor Severity.MEDIUM aos desconhecidos.
    """
    valid_severities = {e.value for e in Severity}
    return value if value in valid_severities else Severity.MEDIUM.value


def _normalize_priority(value: str) -> str:
    """
    Normalize os valores de prioridade, atribuindo o valor Priority.MEDIUM aos desconhecidos.
    """
    valid_priorities = {e.value for e in Priority}
    return value if value in valid_priorities else Priority.MEDIUM.value


def _normalize_raw(data: dict[str, Any]) -> dict[str, Any]:
    """Normaliza enums inválidos antes da validação Pydantic."""
    normalizers = (
        ("components", "type", _normalize_component_type, "unknown"),
        ("risks", "severity", _normalize_severity, "medium"),
        ("recommendations", "priority", _normalize_priority, "medium"),
    )

    for section, field, normalizer, fallback in normalizers:
        for item in data.get(section, []):
            if isinstance(item, dict):
                value = item.get(field, fallback)
                if isinstance(value, str):
                    item[field] = normalizer(value)

    return data


def _parse_json(raw_response: str) -> dict[str, Any]:
    """
    Realiza o parse

    Args:
        raw_response (str): _description_

    Raises:
        ValueError: _description_

    Returns:
        dict[str, Any]: _description_
    """
    try:
        return cast("dict[str, Any]", json.loads(raw_response))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON_PARSE_ERROR: {e}") from e


def _validate_report(data: dict[str, Any], schema_error_prefix: str) -> Report:
    try:
        return Report.model_validate(data)
    except Exception as e:
        raise ValueError(f"{schema_error_prefix}: {e}") from e


def parse_and_validate(raw_response: str) -> Report:
    """
        Analisa, normaliza as enums e valida o JSON retornado pelo LLM.
        Parse do JSON bruto do LLM, normaliza e valida contra o schema Report.
        Raises: ValueError em JSON inválido ou schema incompleto.

    Raises:
        ValueError: com prefixo JSON_PARSE_ERROR ou SCHEMA_ERROR
    """
    data = _parse_json(raw_response)
    data = _normalize_raw(data)
    data, _ = _truncate_summary(data)

    return _validate_report(data, "Schema inválido após normalização")


def detect_conflict(context_text: str | None, report: Report) -> tuple[bool, str]:
    """
    Detecta conflito entre context_text e o relatório gerado.
    Heurística MVP: verifica sobreposição entre palavras do contexto e nomes de componentes.
    Returns: (conflict_detected, conflict_decision)

    Detecta conflitos entre o texto de contexto fornecido e os componentes identificados no
    relatório.
    Retorna True se um conflito for detectado, False caso contrário.
    """
    if not context_text:
        return False, "NO_CONFLICT"

    component_names = {c.name.lower() for c in report.components}
    ctx_lower = context_text.lower()
    words_in_context = set(ctx_lower.split())
    overlap = any(name in ctx_lower for name in component_names)

    if not overlap and len(component_names) > 0 and len(words_in_context) > 5:
        logger.warning(
            "Possível conflito detectado",
            extra={
                "event": "conflict_detected",
                "conflict_policy": "DIAGRAM_FIRST",
                "conflict_decision": "DIAGRAM_FIRST",
            },
        )
        return True, "DIAGRAM_FIRST"

    return False, "NO_CONFLICT"


def _truncate_summary(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    summary = data.get("summary", "")
    if isinstance(summary, str) and len(summary) > 500:
        logger.warning(
            "Summary exceeds 500 characters and will be truncated.",
            extra={
                "event": "_truncate_summary",
                "details": {"original_length": len(summary)},
            },
        )
        data["summary"] = summary[:500]
        return data, True
    return data, False


def validate_and_normalize(raw_response: str) -> tuple[Report, dict[str, Any]]:
    """Parse, normalise enums, and validate the JSON returned by the LLM.

    Returns:
        (Report, metadata_flags) onde metadata_flags contém {"summary_truncated": bool}

    Raises:
        ValueError: com prefixo JSON_PARSE_ERROR ou SCHEMA_ERROR
    """
    data = _parse_json(raw_response)
    data = _normalize_raw(data)
    data, summary_truncated = _truncate_summary(data)
    report = _validate_report(data, "SCHEMA_ERROR")

    return report, {"summary_truncated": summary_truncated}
