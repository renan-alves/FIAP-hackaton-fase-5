"""Ponto de entrada da aplicação FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ai_module.api.routes import router
from ai_module.core.exceptions import (
    AIFailureError,
    AITimeoutError,
    InvalidInputError,
    UnsupportedFormatError,
)
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics
from ai_module.core.settings import settings
from ai_module.core.state import set_service_health
from ai_module.models.report import ErrorResponse

# Initialize logger
logger = get_logger("ai_module.main", level=settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Gerencia o ciclo de vida de inicialização e encerramento da aplicação."""
    logger.info(
        "Application startup",
        extra={
            "event": "startup_initiated",
            "details": {
                "app_version": settings.APP_VERSION,
                "log_level": settings.LOG_LEVEL,
                "llm_provider": settings.LLM_PROVIDER,
            },
        },
    )

    healthy = True

    if settings.LLM_PROVIDER == "gemini" and not settings.GEMINI_API_KEY:
        logger.warning(
            "Service degraded: GEMINI_API_KEY is not set",
            extra={
                "event": "startup_degraded",
                "details": {"reason": "GEMINI_API_KEY missing"},
            },
        )
        healthy = False

    if settings.LLM_PROVIDER == "openai" and not settings.OPENAI_API_KEY:
        logger.warning(
            "Service degraded: OPENAI_API_KEY is not set",
            extra={
                "event": "startup_degraded",
                "details": {"reason": "OPENAI_API_KEY missing"},
            },
        )
        healthy = False

    set_service_health(healthy)

    if healthy:
        logger.info(
            "Service started",
            extra={
                "event": "startup_success",
                "details": {
                    "provider": settings.LLM_PROVIDER,
                    "model": settings.LLM_MODEL,
                },
            },
        )

    yield
    logger.info("Application shutdown")


# Create FastAPI app with lifespan context
app = FastAPI(
    title="AI Module — Architecture Diagram Analyser",
    version=settings.APP_VERSION,
    description="Architecture Diagram Analysis Module",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Register router
app.include_router(router)


def _get_analysis_id(request: Request) -> str:
    """Obtém o identificador da análise a partir do estado da requisição ou dos cabeçalhos."""
    state_analysis_id = getattr(request.state, "analysis_id", None)
    if isinstance(state_analysis_id, str) and state_analysis_id:
        return state_analysis_id
    return request.headers.get("X-Analysis-Id", "unknown")


@app.middleware("http")
async def security_headers(
    request: Request,
    call_next: Callable[..., Awaitable[Response]],
) -> Response:
    """Adiciona cabeçalhos de segurança a todas as respostas HTTP."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(UnsupportedFormatError)
async def unsupported_format_handler(request: Request, exc: UnsupportedFormatError) -> JSONResponse:
    """Retorna a resposta HTTP para erros de formato de arquivo não suportado."""
    logger.warning(
        "Returning unsupported format error",
        extra={
            "event": "unsupported_format_response",
            "analysis_id": _get_analysis_id(request),
            "details": {"message": exc.message},
        },
    )
    metrics.requests_error += 1
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            analysis_id=_get_analysis_id(request),
            status="error",
            error_code="UNSUPPORTED_FORMAT",
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(InvalidInputError)
async def invalid_input_handler(request: Request, exc: InvalidInputError) -> JSONResponse:
    """Retorna a resposta HTTP para erros de entrada inválida."""
    logger.warning(
        "Returning invalid input error",
        extra={
            "event": "invalid_input_response",
            "analysis_id": _get_analysis_id(request),
            "details": {"message": exc.message},
        },
    )
    metrics.requests_error += 1
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            analysis_id=_get_analysis_id(request),
            status="error",
            error_code="INVALID_INPUT",
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(AIFailureError)
async def ai_failure_handler(request: Request, exc: AIFailureError) -> JSONResponse:
    """Retorna a resposta HTTP para falhas internas na análise por IA."""
    logger.error(
        "Returning AI failure error",
        extra={
            "event": "ai_failure_response",
            "analysis_id": _get_analysis_id(request),
            "details": {"message": exc.message},
        },
    )
    metrics.requests_error += 1
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            analysis_id=_get_analysis_id(request),
            status="error",
            error_code="AI_FAILURE",
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(AITimeoutError)
async def timeout_handler(request: Request, exc: AITimeoutError) -> JSONResponse:
    """Retorna a resposta HTTP para erros de tempo limite na análise por IA."""
    logger.error(
        "Returning AI timeout error",
        extra={
            "event": "ai_timeout_response",
            "analysis_id": _get_analysis_id(request),
            "details": {"message": exc.message},
        },
    )
    metrics.requests_error += 1
    return JSONResponse(
        status_code=504,
        content=ErrorResponse(
            analysis_id=_get_analysis_id(request),
            status="error",
            error_code="AI_TIMEOUT",
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Retorna a resposta HTTP para exceções não tratadas."""
    logger.error(
        "Unhandled exception",
        exc_info=True,
        extra={"details": {"error_type": type(exc).__name__}},
    )
    metrics.requests_error += 1
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            analysis_id=_get_analysis_id(request),
            status="error",
            error_code="AI_FAILURE",
            message="An unexpected error occurred. Please try again.",
        ).model_dump(),
    )


def dev() -> None:
    """Inicia o servidor em modo de desenvolvimento com recarga automática."""
    uvicorn.run(
        "ai_module.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )


def main() -> None:
    """Inicia o servidor em modo de produção."""
    uvicorn.run(
        "ai_module.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
