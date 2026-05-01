"""Pipeline de análise de IA orquestrando pré-processamento, chamadas ao LLM e validação."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ai_module.adapters.base import LLMAdapter
from ai_module.core.exceptions import (
    AIFailureError,
    AITimeoutError,
    InvalidInputError,
    LLMCallError,
    LLMTimeoutError,
    UnsupportedFormatError,
    classify_validation_error,
)
from ai_module.core.logger import file_signature_hex, get_logger, truncate_for_log
from ai_module.core.metrics import metrics
from ai_module.core.preprocessor import preprocess
from ai_module.core.prompt_builder import (
    build_correction_prompt,
    build_system_prompt,
    build_user_prompt,
)
from ai_module.core.report_validator import detect_conflict, validate_and_normalize
from ai_module.core.settings import settings
from ai_module.models.report import AnalyzeResponse, Report, ReportMetadata

logger = get_logger(__name__, level=settings.LOG_LEVEL)

_PROVIDER = settings.LLM_PROVIDER.upper()


@dataclass
class AnalysisMetadata:
    model_used: str
    processing_time_ms: int
    input_type: str
    context_text_provided: bool
    context_text_length: int
    conflict_detected: bool = False
    conflict_decision: str = "NO_CONFLICT"
    conflict_policy: str = "DIAGRAM_FIRST"


@dataclass
class AnalysisResult:
    analysis_id: str
    status: str  # "success" | "error"
    report: Report | None = None
    metadata: AnalysisMetadata | None = None
    error_code: str | None = None
    message: str | None = None


async def run_pipeline(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
    adapter: LLMAdapter,
    context_text: str | None = None,
) -> AnalyzeResponse:
    """Executa o pipeline completo de análise de ponta a ponta.

    Orquestra pré-processamento → construção de prompts → loop de retentativas do LLM →
    montagem da resposta, atualizando as métricas globais em cada etapa.

    Parameters
    ----------
    file_bytes : bytes
        Bytes brutos do arquivo enviado.
    filename : str
        Nome original do arquivo.
    analysis_id : str
        UUID4 único identificando esta requisição.
    adapter : LLMAdapter
        Adaptador específico do provedor resolvido pelo handler de rota.

    Returns
    -------
    AnalyzeResponse
        Resposta completa incluindo o relatório validado e metadados.

    Raises
    ------
    UnsupportedFormatError
        Propagado do pré-processamento.
    InvalidInputError
        Propagado do pré-processamento.
    AIFailureError
        Quando o LLM falha em produzir um relatório válido após todas as tentativas.
    """
    logger.info(
        "Analysis request received",
        extra={
            "event": "request_received",
            "analysis_id": analysis_id,
            "details": {
                "filename": filename,
                "file_size_bytes": len(file_bytes),
                "context_text_provided": bool(context_text),
                "context_text_length": len(context_text or ""),
                "provider": _PROVIDER,
                "model": settings.LLM_MODEL,
            },
        },
    )
    total_start = time.monotonic()

    image_bytes, input_type = _step_preprocess(file_bytes, filename, analysis_id)
    system_prompt, user_prompt = _step_build_prompts(image_bytes, analysis_id, context_text)
    report, _flags, successful_attempt = await _step_retry_loop(
        adapter,
        image_bytes,
        system_prompt,
        user_prompt,
        analysis_id,
    )
    conflict_detected, conflict_decision = _detect_conflict(context_text, report, analysis_id)

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

    return _build_response(
        report,
        analysis_id,
        input_type,
        total_ms,
        context_text,
        conflict_detected,
        conflict_decision,
    )


def _detect_conflict(
    context_text: str | None,
    report: Report,
    analysis_id: str,
) -> tuple[bool, str]:
    """Evaluate context-vs-diagram conflict under DIAGRAM_FIRST policy."""
    if not settings.ENABLE_CONFLICT_GUARDRAIL:
        return False, "NO_CONFLICT"

    conflict_detected, conflict_decision = detect_conflict(context_text, report)
    if conflict_detected:
        logger.warning(
            "Conflict between context and diagram detected",
            extra={
                "event": "conflict_detected",
                "analysis_id": analysis_id,
                "details": {
                    "conflict_policy": settings.CONFLICT_POLICY,
                    "conflict_decision": conflict_decision,
                },
            },
        )
    return conflict_detected, conflict_decision


def _apply_semantic_guardrails(report: Report, analysis_id: str) -> Report:
    """Valida e corrige a consistência entre seções do relatório.

    Regras aplicadas:

    1. ``Risk.affected_components`` deve referenciar apenas nomes de componentes
       conhecidos. Referências desconhecidas são removidas silenciosamente (guarda
       contra alucinações do LLM).
    2. O summary deve mencionar ao menos um componente identificado. Caso não mencione,
       um ``WARNING`` é registrado, mas o relatório não é rejeitado, pois o LLM pode
       usar sinônimos ou abreviações.

    Parameters
    ----------
    report : Report
        Relatório validado a inspecionar e corrigir in-place.
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    Report
        O mesmo objeto de relatório com referências alucinadas de componentes removidas.
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
            risk.affected_components = [c for c in risk.affected_components if c in component_names]

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


def _step_preprocess(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
) -> tuple[bytes, str]:
    """Valida e normaliza o arquivo enviado para uma imagem PNG.

    Delega a :func:`~ai_module.core.preprocessor.preprocess` para
    detecção de formato e conversão de imagem. Registra temporização e detalhes de erros.

    Parameters
    ----------
    file_bytes : bytes
        Bytes brutos do arquivo enviado.
    filename : str
        Nome original do arquivo (usado apenas para logging).
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    tuple[bytes, str]
        ``(image_bytes, input_type)`` onde *image_bytes* é o PNG
        normalizado e *input_type* é ``"image"`` ou ``"pdf"``.

    Raises
    ------
    UnsupportedFormatError
        Quando o tipo de arquivo não é PNG, JPEG ou PDF.
    InvalidInputError
        Quando o arquivo está vazio ou excede o limite de tamanho.
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
        image_bytes, input_type = preprocess(file_bytes)
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
                    "file_signature_hex": file_signature_hex(file_bytes),
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


def _step_build_prompts(
    image_bytes: bytes,
    analysis_id: str,
    context_text: str | None,
) -> tuple[str, str]:
    """Constrói os prompts de sistema e de usuário para o LLM.

    O prompt de usuário incorpora a imagem codificada em base 64 e o esquema JSON
    que o LLM deve seguir ao produzir o relatório.

    Parameters
    ----------
    image_bytes : bytes
        Bytes da imagem PNG normalizada.
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    tuple[str, str]
        ``(system_prompt, user_prompt)``.
    """
    system_prompt = build_system_prompt()
    user_prompt, _ = build_user_prompt(image_bytes, context_text=context_text)
    logger.info(
        "Prompts built",
        extra={
            "event": "prompt_build_success",
            "analysis_id": analysis_id,
            "details": {
                "system_prompt_length": len(system_prompt),
                "user_prompt_length": len(user_prompt),
                "context_text_provided": bool(context_text),
                "context_text_length": len(context_text or ""),
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
    """Envia uma única requisição ao provedor LLM configurado.

    Encapsula ``adapter.analyze`` com logging estruturado para eventos de
    início, sucesso, timeout e erro.

    Parameters
    ----------
    adapter : LLMAdapter
        Adaptador específico do provedor (Gemini ou OpenAI).
    image_bytes : bytes
        Bytes da imagem PNG normalizada.
    current_prompt : str
        Prompt de usuário (pode ser o original ou um prompt de correção).
    system_prompt : str
        Prompt de instrução em nível de sistema.
    analysis_id : str
        Identificador de correlação para os logs estruturados.
    attempt : int
        Número da tentativa atual (base 1).

    Returns
    -------
    str
        Resposta textual bruta do LLM.

    Raises
    ------
    LLMTimeoutError
        Quando o provedor não responde dentro da janela de timeout.
    LLMCallError
        Quando o provedor retorna um erro irrecuperável.
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


def _step_validate(raw: str, analysis_id: str, attempt: int) -> tuple[Report, dict[str, Any]]:
    """Analisa e valida a resposta bruta do LLM em um ``Report``.

    Delega a :func:`~ai_module.core.report_validator.validate_and_normalize`
    que extrai o JSON, aplica o esquema Pydantic e normaliza os campos
    (ex.: truncamento do summary).

    Parameters
    ----------
    raw : str
        Texto bruto retornado pelo LLM.
    analysis_id : str
        Identificador de correlação para os logs estruturados.
    attempt : int
        Número da tentativa atual (base 1).

    Returns
    -------
    tuple[Report, dict]
        ``(report, metadata_flags)`` onde *metadata_flags* contém
        indicadores de pós-processamento como ``summary_truncated``.

    Raises
    ------
    ValueError
        Quando a resposta não pode ser analisada ou viola o esquema.
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
                    "error": truncate_for_log(str(e), limit=300),
                    "raw_response_excerpt": truncate_for_log(raw),
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
) -> tuple[Report, dict[str, Any], int]:
    """Reexecuta o ciclo de chamada ao LLM + validação até ``LLM_MAX_RETRIES`` vezes.

    Em caso de falha de validação, o LLM recebe um *prompt de correção* que
    inclui a resposta bruta anterior e o erro de validação para que possa
    se autocorrigir. Erros de timeout e de chamada simplesmente avançam para
    a próxima tentativa.

    Parameters
    ----------
    adapter : LLMAdapter
        Adaptador específico do provedor.
    image_bytes : bytes
        Bytes da imagem PNG normalizada.
    system_prompt : str
        Prompt de instrução em nível de sistema.
    user_prompt : str
        Prompt de usuário inicial (usado na primeira tentativa).
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    tuple[Report, dict, int]
        ``(report, metadata_flags, successful_attempt)``.

    Raises
    ------
    AIFailureError
        Quando todas as tentativas são esgotadas sem produzir um relatório válido.
    """
    report: Report | None = None
    metadata_flags: dict[str, Any] = {"summary_truncated": False}
    current_prompt = user_prompt
    last_raw: str = ""
    last_error: str = ""
    last_was_timeout: bool = False
    successful_attempt: int | None = None

    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        if attempt > 1 and last_raw and last_error:
            targeted_instruction = classify_validation_error(last_error)
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
                adapter,
                image_bytes,
                current_prompt,
                system_prompt,
                analysis_id,
                attempt,
            )
        except LLMTimeoutError:
            last_was_timeout = True
            continue
        except LLMCallError:
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
                    "last_error": truncate_for_log(last_error, limit=300) if last_error else None,
                    "last_raw_response_excerpt": truncate_for_log(last_raw) if last_raw else None,
                },
            },
        )
        metrics.requests_error += 1
        if last_was_timeout:
            raise AITimeoutError("LLM timeout after retries")
        raise AIFailureError("Failed to generate a valid report after all retries.")

    return report, metadata_flags, successful_attempt


def _build_response(
    report: Report,
    analysis_id: str,
    input_type: str,
    total_ms: int,
    context_text: str | None,
    conflict_detected: bool,
    conflict_decision: str,
) -> AnalyzeResponse:
    """Monta a resposta final da API com o relatório e metadados.

    Parameters
    ----------
    report : Report
        Relatório de análise validado.
    analysis_id : str
        Identificador de correlação.
    input_type : str
        Tipo original do arquivo (``"image"`` ou ``"pdf"``).
    total_ms : int
        Tempo total de parede do pipeline em milissegundos.

    Returns
    -------
    AnalyzeResponse
        Modelo de resposta serializável.
    """
    return AnalyzeResponse(
        analysis_id=analysis_id,
        status="success",
        report=report,
        metadata=ReportMetadata(
            model_used=settings.LLM_MODEL,
            processing_time_ms=total_ms,
            input_type=input_type,  # type: ignore[arg-type]
            context_text_provided=bool(context_text),
            context_text_length=len(context_text or ""),
            downsampling_applied=False,
            conflict_detected=conflict_detected,
            conflict_decision=conflict_decision,
            conflict_policy=settings.CONFLICT_POLICY,
        ),
    )
