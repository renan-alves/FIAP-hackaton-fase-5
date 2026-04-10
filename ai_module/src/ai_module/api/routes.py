# Note 1: `from __future__ import annotations` ativa avaliacao preguicosa de type hints
# (PEP 563), permitindo referencias antecipadas e melhor desempenho na importacao.
from __future__ import annotations

# Note 2: `Annotated` permite combinar tipo com metadados extras. O FastAPI usa isso
# para injetar dados de Form, Query, Header e Depends pela assinatura da funcao.
from typing import Annotated

# Note 3: APIRouter agrupa rotas em modulos; Depends implementa injecao de dependencias;
# Form extrai campos de formulario multipart; HTTPException levanta erros HTTP com JSON.
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

# Note 4: Imports internos seguem arquitetura em camadas: adapters (provedores LLM),
# core (logica, config, logging), models (schemas Pydantic de entrada/saida).
from ai_module.adapters.base import LLMAdapter
from ai_module.adapters.factory import get_llm_adapter
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics as _metrics
from ai_module.core.pipeline import run_pipeline
from ai_module.core.settings import settings
from ai_module.models.report import AnalyzeResponse

"""Rotas da API para o Módulo de IA."""

# Note 5: APIRouter cria um roteador modular. As rotas aqui sao montadas no app
# principal em main.py via `app.include_router(router)`.
router = APIRouter()

# Note 6: Variavel de estado usada como "circuit breaker" simplificado.
# O prefixo underscore sinaliza uso interno ao modulo (convencao Python).
_service_healthy: bool = True


# Note 7: Usa `global` para modificar a variavel do escopo do modulo.
# Sem `global`, Python criaria uma variavel local com o mesmo nome.
def set_service_health(healthy: bool) -> None:
    global _service_healthy
    _service_healthy = healthy

# Note 8: `__name__` resolve para o caminho do modulo (ex: "ai_module.api.routes"),
# criando um logger JSON estruturado e unico por modulo.
logger = get_logger(__name__, level=settings.LOG_LEVEL)


# Note 9: `@router.get` registra a funcao como handler HTTP GET. `async def` permite
# que o event loop do asyncio gerencie I/O sem bloquear outras requisicoes.
@router.get("/health")
async def health_check() -> dict:
    # Note 10: HTTP 503 (Service Unavailable) sinaliza degradacao temporaria.
    # Orquestradores como Kubernetes usam health checks para decidir sobre restarts.
    if not _service_healthy:
       
 
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


# Note 11: `response_class=PlainTextResponse` retorna text/plain, formato Prometheus.
# Note 12: `def` (sincrono) em vez de `async def`: sem operacoes await neste handler.
# FastAPI executa handlers sincronos em thread pool separado automaticamente.
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
    # Note 13: Formato de exposicao Prometheus: HELP (descricao), TYPE (counter/gauge/
    # histogram), e valor. Ferramentas como Grafana e AlertManager consomem este formato.
    lines = [
        "# HELP ai_module_requests_success_total Total de solicitações de análise bem-sucedidas",
        "# TYPE ai_module_requests_success_total counter",
        f"ai_module_requests_success_total {_metrics.requests_success}",
        "# HELP ai_module_requests_error_total Total de solicitações de análise com falha",
        "# TYPE ai_module_requests_error_total counter",
        f"ai_module_requests_error_total {_metrics.requests_error}",
        "# HELP ai_module_processing_time_ms_total Tempo total de processamento em milissegundos",
        "# TYPE ai_module_processing_time_ms_total counter",
        f"ai_module_processing_time_ms_total {_metrics.processing_time_ms_total}",
        "# HELP ai_module_llm_retries_total Total de tentativas de retry do LLM",
        "# TYPE ai_module_llm_retries_total counter",
        f"ai_module_llm_retries_total {_metrics.llm_retries_total}",
    ]
    return "\n".join(lines) + "\n"

# Note 14: `response_model` faz o FastAPI validar e serializar a resposta com Pydantic,
# gerando automaticamente o schema OpenAPI/Swagger para documentacao.
@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    file: UploadFile,
    # Note 15: `Form(...)` extrai campo obrigatorio de formulario multipart.
    # O `...` (Ellipsis) indica campo required, sem valor padrao.
    analysis_id: Annotated[str, Form(...)],
    # Note 16: `Depends(get_llm_adapter)` injeta o adapter LLM configurado.
    # FastAPI resolve dependencias automaticamente a cada requisicao (padrao DI).
    adapter: Annotated[LLMAdapter, Depends(get_llm_adapter)],
) -> AnalyzeResponse:
    """Executa o pipeline completo de análise de IA para um arquivo enviado."""
    # Note 17: `request.state` e um objeto mutavel por requisicao, permitindo
    # compartilhar o analysis_id entre middlewares e exception handlers.
    request.state.analysis_id = analysis_id
    file_bytes = await file.read()
    # Note 18: Log estruturado com `extra` contendo `event` e `details`.
    # Produz JSON parsavel por plataformas de observabilidade (ELK, Datadog, Loki).
    logger.info(
        "Solicitação de análise recebida",
        extra={
            "event": "analyze_request_received",
            "analysis_id": analysis_id,
            "details": {
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size_bytes": len(file_bytes),
                "app_version": settings.APP_VERSION,
                "llm_provider": settings.LLM_PROVIDER,
            },
        },
    )
    # Note 19: O handler delega toda logica de negocio ao pipeline. Manter
    # o endpoint como orquestrador fino facilita testes e separacao de responsabilidades.
    return await run_pipeline(
        file_bytes=file_bytes,
        filename=file.filename, # type: ignore
        analysis_id=analysis_id,
        adapter=adapter,
    )
