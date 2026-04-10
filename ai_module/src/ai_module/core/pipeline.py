"""AI analysis pipeline orchestrating preprocessing, LLM calls, and validation."""

from __future__ import annotations

import time

from ai_module.adapters.base import LLMAdapter
from ai_module.core.exceptions import (
    AIFailureError,
    InvalidInputError,
    LLMCallError,
    LLMTimeoutError,
    UnsupportedFormatError,
)
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics
from ai_module.core.preprocessor import preprocess
from ai_module.core.prompt_builder import (
    build_correction_prompt,
    build_system_prompt,
    build_user_prompt,
)
from ai_module.core.report_validator import validate_and_normalize
from ai_module.core.settings import settings
from ai_module.models.report import AnalyzeResponse, Report, ReportMetadata

logger = get_logger(__name__, level=settings.LOG_LEVEL)

_PROVIDER = settings.LLM_PROVIDER.upper()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate_for_log(value: str, limit: int = 500) -> str:
    """Compact and truncate a string for safe inclusion in structured log entries.

    Replaces newlines with literal escape sequences and cuts at ``limit``
    characters, appending an ellipsis when the value is longer.

    Parameters
    ----------
    value : str
        Raw string to compact.
    limit : int
        Maximum character length before truncation (default 500).

    Returns
    -------
    str
        Single-line string of at most ``limit + 3`` characters.
    """ 
    compact = value.replace("\n", "\\n").replace("\r", "\\r")
    return compact[:limit] + "..." if len(compact) > limit else compact


def _file_signature_hex(file_bytes: bytes, limit: int = 16) -> str:
    """Return the first ``limit`` bytes of a file as a hex string.

    Useful for diagnostic logging — allows identification of file
    type by magic bytes without exposing the full content.

    Parameters
    ----------
    file_bytes : bytes
        Raw file content.
    limit : int
        Number of leading bytes to include (default 16).

    Returns
    -------
    str
        Hex-encoded prefix (e.g. ``"89504e47..."``).
    """
    return file_bytes[:limit].hex()


def _classify_validation_error(error: str) -> str:
    """Map a validation error message to a targeted correction instruction.

    Parameters
    ----------
    error : str
        Validation error string returned by ``validate_and_normalize``.

    Returns
    -------
    str
        Human-readable correction instruction to embed in the next
        LLM prompt so the model can self-correct the specific issue.
    """
    if "JSON_PARSE_ERROR" in error:
        return (
            "Your response was not valid JSON. "
            "Return ONLY the raw JSON object, no markdown, no extra text."
        )
    if "components" in error:
        return (
            "The 'components' field is missing or empty. "
            "You MUST identify at least one component visible in the diagram."
        )
    if "summary" in error:
        return (
            "The 'summary' field is missing or exceeds 500 characters. "
            "Provide a concise summary of at most 500 characters."
        )
    if "severity" in error:
        return "Use only 'high', 'medium', or 'low' for risk severity."
    if "priority" in error:
        return "Use only 'high', 'medium', or 'low' for recommendation priority."
    if "SCHEMA_ERROR" in error:
        return (
            f"Schema validation failed: {error}. "
            "Fix only the invalid fields and return the complete JSON."
        )
    return f"Fix the invalid response. Error: {error}"


# ── Semantic consistency guardrail ────────────────────────────────────────────

def _apply_semantic_guardrails(report: Report, analysis_id: str) -> Report:
    """Validate and repair cross-section consistency of the report.

    Rules applied:

    1. ``Risk.affected_components`` must only reference known component names.
       Unknown references are silently removed (LLM hallucination guard).
    2. Summary should mention at least one identified component.
       If it does not, a ``WARNING`` is logged but the report is not rejected
       because the LLM may use synonyms or abbreviations.

    Parameters
    ----------
    report : Report
        Validated report to inspect and repair in place.
    analysis_id : str
        Correlation identifier for structured logs.

    Returns
    -------
    Report
        The same report object with hallucinated component references removed.
    """
    component_names = {c.name for c in report.components}

    for risk in report.risks:
        unknown_refs = set(risk.affected_components) - component_names
        if unknown_refs:
            logger.warning(
                "Risk references unknown components — removing hallucinated refs",
                extra={
                    "event": "semantic_guardrail_component_ref",
                    "analysis_id": analysis_id,
                    "details": {
                        "risk_title": risk.title,
                        "unknown_refs": list(unknown_refs),
                        "known_components": list(component_names),
                    },
                },
            )
            risk.affected_components = [
                c for c in risk.affected_components if c in component_names
            ]

    summary_lower = report.summary.lower()
    mentioned = any(c.name.lower() in summary_lower for c in report.components)
    if not mentioned:
        logger.warning(
            "Summary does not mention any identified component — possible hallucination",
            extra={
                "event": "semantic_guardrail_summary_mismatch",
                "analysis_id": analysis_id,
                "details": {"component_names": list(component_names)},
            },
        )

    return report


# ── Pipeline steps ────────────────────────────────────────────────────────────

def _step_preprocess(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
) -> tuple[bytes, str]:
    """Validate and normalise the uploaded file into a PNG image.

    Delegates to :func:`~ai_module.core.preprocessor.preprocess` for
    format detection and image conversion. Logs timing and error details.

    Parameters
    ----------
    file_bytes : bytes
        Raw bytes of the uploaded file.
    filename : str
        Original filename (used for logging only).
    analysis_id : str
        Correlation identifier for structured logs.

    Returns
    -------
    tuple[bytes, str]
        ``(image_bytes, input_type)`` where *image_bytes* is the
        normalised PNG and *input_type* is ``"image"`` or ``"pdf"``.

    Raises
    ------
    UnsupportedFormatError
        When the file type is not PNG, JPEG or PDF.
    InvalidInputError
        When the file is empty or exceeds the size limit.
    """
    logger.info(
        "Preprocessing started",
        extra={
            "event": "preprocessing_start",
            "analysis_id": analysis_id,
            "details": {"filename": filename},
        },
    )
    pre_start = time.monotonic()
    try:
        image_bytes, input_type = preprocess(file_bytes, filename)
    except (UnsupportedFormatError, InvalidInputError) as e:
        logger.error(
            "Preprocessing failed",
            extra={
                "event": "preprocessing_error",
                "analysis_id": analysis_id,
                "details": {
                    "error_code": type(e).__name__,
                    "message": e.message,
                    "filename": filename,
                    "file_size_bytes": len(file_bytes),
                    "file_signature_hex": _file_signature_hex(file_bytes),
                },
            },
        )
        raise

    pre_ms = int((time.monotonic() - pre_start) * 1000)
    logger.info(
        "Preprocessing completed",
        extra={
            "event": "preprocessing_success",
            "analysis_id": analysis_id,
            "details": {
                "processing_time_ms": pre_ms,
                "input_type": input_type,
                "normalized_image_size_bytes": len(image_bytes),
            },
        },
    )
    return image_bytes, input_type


def _step_build_prompts(image_bytes: bytes, analysis_id: str) -> tuple[str, str]:
    """Construct the system and user prompts for the LLM.

    The user prompt embeds the base-64 encoded image and the JSON
    schema that the LLM must follow when producing the report.

    Parameters
    ----------
    image_bytes : bytes
        Normalised PNG image bytes.
    analysis_id : str
        Correlation identifier for structured logs.

    Returns
    -------
    tuple[str, str]
        ``(system_prompt, user_prompt)``.
    """
    system_prompt = build_system_prompt()
    user_prompt, _ = build_user_prompt(image_bytes)
    logger.info(
        "Prompts built",
        extra={
            "event": "prompt_build_success",
            "analysis_id": analysis_id,
            "details": {
                "system_prompt_length": len(system_prompt),
                "user_prompt_length": len(user_prompt),
            },
        },
    )
    return system_prompt, user_prompt


async def _step_call_llm(
    adapter: LLMAdapter,
    image_bytes: bytes,
    current_prompt: str,
    system_prompt: str,
    analysis_id: str,
    attempt: int,
) -> str:
    """Send a single request to the configured LLM provider.

    Wraps ``adapter.analyze`` with structured logging for start,
    success, timeout and error events.

    Parameters
    ----------
    adapter : LLMAdapter
        Provider-specific adapter (Gemini ou OpenAI).
    image_bytes : bytes
        Normalised PNG image bytes.
    current_prompt : str
        User prompt (may be the original or a correction prompt).
    system_prompt : str
        System-level instruction prompt.
    analysis_id : str
        Correlation identifier for structured logs.
    attempt : int
        Current attempt number (1-based).

    Returns
    -------
    str
        Raw text response from the LLM.

    Raises
    ------
    LLMTimeoutError
        When the provider does not respond within the timeout window.
    LLMCallError
        When the provider returns an unrecoverable error.
    """
    logger.info(
        "LLM call started",
        extra={
            "event": "llm_call_start",
            "analysis_id": analysis_id,
            "details": {
                "attempt": attempt,
                "provider": _PROVIDER,
                "model": settings.LLM_MODEL,
                "image_size_bytes": len(image_bytes),
            },
        },
    )
    llm_start = time.monotonic()

    try:
        raw = await adapter.analyze(image_bytes, current_prompt, system_prompt)
    except LLMTimeoutError as e:
        logger.warning(
            "LLM call timed out",
            extra={
                "event": "llm_call_timeout",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "timeout_seconds": settings.LLM_TIMEOUT_SECONDS,
                    "message": e.message,
                },
            },
        )
        raise
    except LLMCallError as e:
        logger.error(
            "LLM call failed",
            extra={
                "event": "llm_call_error",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "error_type": type(e).__name__,
                    "message": e.message,
                },
            },
        )
        raise

    llm_ms = int((time.monotonic() - llm_start) * 1000)
    logger.info(
        "LLM call succeeded",
        extra={
            "event": "llm_call_success",
            "analysis_id": analysis_id,
            "details": {
                "attempt": attempt,
                "processing_time_ms": llm_ms,
                "model_used": settings.LLM_MODEL,
                "raw_response_length": len(raw),
            },
        },
    )
    return raw


def _step_validate(raw: str, analysis_id: str, attempt: int) -> tuple[Report, dict]:
    """Parse and validate the raw LLM response into a ``Report``.

    Delegates to :func:`~ai_module.core.report_validator.validate_and_normalize`
    which extracts JSON, enforces the Pydantic schema and applies
    normalisation rules (e.g. summary truncation).

    Parameters
    ----------
    raw : str
        Raw text returned by the LLM.
    analysis_id : str
        Correlation identifier for structured logs.
    attempt : int
        Current attempt number (1-based).

    Returns
    -------
    tuple[Report, dict]
        ``(report, metadata_flags)`` where *metadata_flags* contains
        post-processing indicators such as ``summary_truncated``.

    Raises
    ------
    ValueError
        When the response cannot be parsed or violates the schema.
    """
    try:
        report, metadata_flags = validate_and_normalize(raw)
    except ValueError as e:
        logger.warning(
            "Validation failed for LLM response",
            extra={
                "event": "validation_error",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "error": _truncate_for_log(str(e), limit=300),
                    "raw_response_excerpt": _truncate_for_log(raw),
                },
            },
        )
        raise

    logger.info(
        "Report validation succeeded",
        extra={
            "event": "validation_success",
            "analysis_id": analysis_id,
            "details": {
                "attempt": attempt,
                "summary_truncated": metadata_flags["summary_truncated"],
                "components_count": len(report.components),
                "risks_count": len(report.risks),
                "recommendations_count": len(report.recommendations),
            },
        },
    )
    return report, metadata_flags


async def _step_retry_loop(
    adapter: LLMAdapter,
    image_bytes: bytes,
    system_prompt: str,
    user_prompt: str,
    analysis_id: str,
) -> tuple[Report, dict, int]:
    """Retry the LLM call + validation cycle up to ``LLM_MAX_RETRIES`` times.

    On validation failure the LLM receives a *correction prompt* that
    includes the previous raw response and the validation error so it
    can self-correct.  Timeout and call errors simply skip to the next
    attempt.

    Parameters
    ----------
    adapter : LLMAdapter
        Provider-specific adapter.
    image_bytes : bytes
        Normalised PNG image bytes.
    system_prompt : str
        System-level instruction prompt.
    user_prompt : str
        Initial user prompt (used on the first attempt).
    analysis_id : str
        Correlation identifier for structured logs.

    Returns
    -------
    tuple[Report, dict, int]
        ``(report, metadata_flags, successful_attempt)``.

    Raises
    ------
    AIFailureError
        When all attempts are exhausted without producing a valid report.
    """
    report: Report | None = None
    metadata_flags: dict = {"summary_truncated": False}
    current_prompt = user_prompt
    last_raw: str = ""
    last_error: str = ""
    successful_attempt: int | None = None

    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        if attempt > 1 and last_raw and last_error:
            targeted_instruction = _classify_validation_error(last_error)
            current_prompt = build_correction_prompt(last_raw, targeted_instruction)
            logger.info(
                "Prepared targeted correction prompt",
                extra={
                    "event": "correction_prompt_built",
                    "analysis_id": analysis_id,
                    "details": {
                        "attempt": attempt,
                        "error_class": targeted_instruction[:80],
                    },
                },
            )

        try:
            raw = await _step_call_llm(
                adapter, image_bytes, current_prompt, system_prompt, analysis_id, attempt,
            )
        except (LLMTimeoutError, LLMCallError):
            continue

        try:
            report, metadata_flags = _step_validate(raw, analysis_id, attempt)
        except ValueError as e:
            last_raw = raw
            last_error = str(e)
            continue

        report = _apply_semantic_guardrails(report, analysis_id)
        successful_attempt = attempt
        break

    if report is None or successful_attempt is None:
        logger.error(
            "Analysis failed after all retries",
            extra={
                "event": "analysis_failure",
                "analysis_id": analysis_id,
                "details": {
                    "error_code": "AI_FAILURE",
                    "provider": _PROVIDER,
                    "model": settings.LLM_MODEL,
                    "last_error": _truncate_for_log(last_error, limit=300) if last_error else None,
                    "last_raw_response_excerpt": _truncate_for_log(last_raw) if last_raw else None,
                },
            },
        )
        metrics.requests_error += 1
        raise AIFailureError("Failed to generate a valid report after all retries.")

    return report, metadata_flags, successful_attempt


def _build_response(
    report: Report,
    analysis_id: str,
    input_type: str,
    total_ms: int,
) -> AnalyzeResponse:
    """Assemble the final API response with report and metadata.

    Parameters
    ----------
    report : Report
        Validated analysis report.
    analysis_id : str
        Correlation identifier.
    input_type : str
        Original file type (``"image"`` or ``"pdf"``).
    total_ms : int
        Total pipeline wall-clock time in milliseconds.

    Returns
    -------
    AnalyzeResponse
        Serialisable response model.
    """
    return AnalyzeResponse(
        analysis_id=analysis_id,
        status="success",
        report=report,
        metadata=ReportMetadata(
            model_used=settings.LLM_MODEL,
            processing_time_ms=total_ms,
            input_type=input_type,  # type: ignore[arg-type]
        ),
    )


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def run_pipeline(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
    adapter: LLMAdapter,
) -> AnalyzeResponse:
    """Execute the full analysis pipeline end-to-end.

    Orchestrates preprocessing → prompt building → LLM retry loop →
    response assembly, updating global metrics at each stage.

    Parameters
    ----------
    file_bytes : bytes
        Raw bytes of the uploaded file.
    filename : str
        Original filename.
    analysis_id : str
        Unique UUID4 identifying this request.
    adapter : LLMAdapter
        Provider-specific adapter resolved by the route handler.

    Returns
    -------
    AnalyzeResponse
        Complete response including the validated report and metadata.

    Raises
    ------
    UnsupportedFormatError
        Propagated from preprocessing.
    InvalidInputError
        Propagated from preprocessing.
    AIFailureError
        When the LLM fails to produce a valid report after all retries.
    """
    logger.info(
        "Analysis request received",
        extra={
            "event": "request_received",
            "analysis_id": analysis_id,
            "details": {
                "filename": filename,
                "file_size_bytes": len(file_bytes),
                "provider": _PROVIDER,
                "model": settings.LLM_MODEL,
            },
        },
    )
    total_start = time.monotonic()

    image_bytes, input_type = _step_preprocess(file_bytes, filename, analysis_id)
    system_prompt, user_prompt = _step_build_prompts(image_bytes, analysis_id)
    report, _flags, successful_attempt = await _step_retry_loop(
        adapter, image_bytes, system_prompt, user_prompt, analysis_id,
    )

    metrics.requests_success += 1
    metrics.llm_retries_total += successful_attempt - 1

    total_ms = int((time.monotonic() - total_start) * 1000)
    metrics.processing_time_ms_total += total_ms

    logger.info(
        "Analysis completed successfully",
        extra={
            "event": "analysis_success",
            "analysis_id": analysis_id,
            "details": {"total_time_ms": total_ms, "input_type": input_type},
        },
    )

    return _build_response(report, analysis_id, input_type, total_ms)