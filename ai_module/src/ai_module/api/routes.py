"""API routes for the AI Module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import PlainTextResponse

from ai_module.adapters.base import LLMAdapter
from ai_module.adapters.factory import get_llm_adapter
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics as _metrics
from ai_module.core.pipeline import run_pipeline
from ai_module.core.settings import settings
from ai_module.models.report import AnalyzeResponse

router = APIRouter()
 
_service_healthy: bool = True
 
 
def set_service_health(healthy: bool) -> None:
    global _service_healthy
    _service_healthy = healthy
 
logger = get_logger(__name__, level=settings.LOG_LEVEL)
 

@router.get("/health")
async def health_check() -> dict:

    if not _service_healthy:
        from fastapi import HTTPException
 
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "version": settings.APP_VERSION,
                "llm_provider": settings.LLM_PROVIDER,
            },
        )
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER,
    }


@router.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    """Metrics endpoint returning Prometheus format."""
    logger.debug(
        "Received metrics request",
        extra={
            "details": {
                "app_version": settings.APP_VERSION,
                "llm_provider": settings.LLM_PROVIDER,
            }
        },
    )
    lines = [
        "# HELP ai_module_requests_success_total Total successful analysis requests",
        "# TYPE ai_module_requests_success_total counter",
        f"ai_module_requests_success_total {_metrics.requests_success}",
        "# HELP ai_module_requests_error_total Total failed analysis requests",
        "# TYPE ai_module_requests_error_total counter",
        f"ai_module_requests_error_total {_metrics.requests_error}",
        "# HELP ai_module_processing_time_ms_total Total processing time in milliseconds",
        "# TYPE ai_module_processing_time_ms_total counter",
        f"ai_module_processing_time_ms_total {_metrics.processing_time_ms_total}",
        "# HELP ai_module_llm_retries_total Total LLM retry attempts",
        "# TYPE ai_module_llm_retries_total counter",
        f"ai_module_llm_retries_total {_metrics.llm_retries_total}",
    ]
    return "\n".join(lines) + "\n"

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    file: UploadFile,
    analysis_id: Annotated[str, Form(...)],
    adapter: Annotated[LLMAdapter, Depends(get_llm_adapter)],
) -> AnalyzeResponse:
    """Run the complete AI analysis pipeline for an uploaded file."""
    request.state.analysis_id = analysis_id
    logger.debug("Received analyze request (stub)",
                 extra={"details": {"app_version": settings.APP_VERSION, 
                                    "llm_provider": settings.LLM_PROVIDER}})

    file_bytes = await file.read()
    return await run_pipeline(
        file_bytes=file_bytes,
        filename=file.filename,
        analysis_id=analysis_id,
        adapter=adapter,
    )
