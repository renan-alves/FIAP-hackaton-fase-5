"""Metrics route — exposes Prometheus-formatted counters and gauges."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics as _metrics
from ai_module.core.settings import settings

router = APIRouter()

logger = get_logger(__name__, level=settings.LOG_LEVEL)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    """Endpoint de métricas que retorna no formato Prometheus."""
    logger.debug(
        "Received metrics request",
        extra={
            "details": {
                "app_version": settings.APP_VERSION,
                "llm_provider": settings.LLM_PROVIDER,
            }
        },
    )
    total_requests = _metrics.requests_success + _metrics.requests_error
    avg_ms = int(_metrics.processing_time_ms_total / total_requests) if total_requests else 0
    lines = [
        "# HELP ai_requests_total Total de solicitações de análise",
        "# TYPE ai_requests_total counter",
        f'ai_requests_total{{status="success"}} {_metrics.requests_success}',
        f'ai_requests_total{{status="error"}} {_metrics.requests_error}',
        "# HELP ai_processing_time_ms_avg Tempo médio de processamento em milissegundos",
        "# TYPE ai_processing_time_ms_avg gauge",
        f"ai_processing_time_ms_avg {avg_ms}",
        "# HELP ai_llm_retries_total Total de tentativas de retry do LLM",
        "# TYPE ai_llm_retries_total counter",
        f"ai_llm_retries_total {_metrics.llm_retries_total}",
        "# HELP ai_llm_provider_active Provedor LLM ativo (1=ativo)",
        "# TYPE ai_llm_provider_active gauge",
        f'ai_llm_provider_active{{provider="{settings.LLM_PROVIDER}"}} 1',
        "# HELP queue_messages_consumed_total Total de mensagens consumidas da fila",
        "# TYPE queue_messages_consumed_total counter",
        f"queue_messages_consumed_total {_metrics.messages_consumed}",
        "# HELP queue_messages_published_total Total de mensagens publicadas na fila",
        "# TYPE queue_messages_published_total counter",
        f"queue_messages_published_total {_metrics.results_published + _metrics.errors_published}",
        "# HELP queue_validation_errors_total Total de erros de validação de mensagens",
        "# TYPE queue_validation_errors_total counter",
        f"queue_validation_errors_total {_metrics.validation_errors}",
        "# HELP queue_pipeline_errors_total Total de erros no pipeline de análise",
        "# TYPE queue_pipeline_errors_total counter",
        f"queue_pipeline_errors_total {_metrics.pipeline_errors}",
        "# HELP queue_publish_failures_total Total de falhas de publicação na fila",
        "# TYPE queue_publish_failures_total counter",
        f"queue_publish_failures_total {_metrics.publish_failures}",
        "# HELP queue_results_published_total Total de resultados publicados na fila por status",
        "# TYPE queue_results_published_total counter",
        f'queue_results_published_total{{status="success"}} {_metrics.results_published}',
        f'queue_results_published_total{{status="error"}} {_metrics.errors_published}',
    ]
    return "\n".join(lines) + "\n"
