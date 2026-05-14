"""Health check route — returns service liveness and configuration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ai_module.core import state as _state
from ai_module.core.settings import settings

router = APIRouter()


def _health_payload(status: str, queue_connected: bool) -> dict[str, Any]:
    """Build the canonical health response body (top-level fields, no nesting)."""
    return {
        "status": status,
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER,
        "queue_connected": queue_connected,
    }


@router.get("/health")
async def health_check() -> JSONResponse:
    """Retorna status de saúde do serviço.

    HTTP 200 quando o serviço está saudável; HTTP 503 quando degradado.
    The body always uses top-level fields (never nested under ``detail``).
    """
    queue_connected = _state.get_queue_connected()
    if not _state._service_healthy:
        return JSONResponse(
            status_code=503,
            content=_health_payload("degraded", queue_connected),
        )
    return JSONResponse(
        status_code=200,
        content=_health_payload("healthy", queue_connected),
    )
