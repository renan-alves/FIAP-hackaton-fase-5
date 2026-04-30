"""Pydantic models for architecture analysis reports.

The models in this module follow the report contract defined in `specs/spec.md` v2.1.
All models reject unknown fields (`extra="forbid"`) and enforce strict enums.

Breaking change (v2.1): ``AnalyzeResponse`` now wraps report fields inside a nested
``report`` object instead of exposing them at the top level.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# ---------------------------------------------------------------------------
# Typed string aliases
# ---------------------------------------------------------------------------

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
SummaryStr = Annotated[str, StringConstraints(min_length=1, max_length=500)]
TitleStr = Annotated[str, StringConstraints(min_length=1, max_length=160)]
DescriptionStr = Annotated[str, StringConstraints(min_length=1, max_length=500)]
AnalysisIdStr = Annotated[str, StringConstraints(min_length=1)]
ErrorCodeStr = Annotated[str, StringConstraints(min_length=1)]

# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    """Base model que rejeita campos desconhecidos."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComponentType(StrEnum):
    """Categorias de componentes de arquitetura suportados."""

    SERVICE = "service"
    DATABASE = "database"
    QUEUE = "queue"
    GATEWAY = "gateway"
    CACHE = "cache"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Níveis de severidade de risco."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Priority(StrEnum):
    """Níveis de prioridade de recomendação."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------


class Component(StrictModel):
    """Componente identificado no diagrama de arquitetura."""

    name: str = Field(min_length=1, max_length=120)
    type: ComponentType
    description: DescriptionStr


class Risk(StrictModel):
    """Risco identificado durante a análise de arquitetura."""

    title: TitleStr
    severity: Severity
    description: DescriptionStr
    affected_components: list[str] = Field(default_factory=list)


class Recommendation(StrictModel):
    """Ação recomendada para melhorar a arquitetura."""

    title: TitleStr
    priority: Priority
    description: DescriptionStr


class Report(StrictModel):
    """Payload principal do relatório retornado pelo pipeline de IA."""

    summary: SummaryStr
    components: list[Component] = Field(min_length=1)
    risks: list[Risk] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class ReportMetadata(StrictModel):
    """Metadados descrevendo como o relatório foi gerado."""

    model_used: NonEmptyStr
    processing_time_ms: int = Field(ge=0)
    input_type: Literal["image", "pdf"]
    context_text_provided: bool = False
    context_text_length: int = Field(default=0, ge=0)
    downsampling_applied: bool = False
    conflict_detected: bool = False
    conflict_decision: str = "NO_CONFLICT"
    conflict_policy: str = "DIAGRAM_FIRST"


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------


class BaseResponse(StrictModel):
    """Base para respostas da API contendo analysis_id."""

    analysis_id: AnalysisIdStr


class AnalyzeResponse(BaseResponse):
    """Contrato de resposta de sucesso para POST /analyze per spec v2.1.

    O relatório é retornado como objeto aninhado ``report`` em vez de campos planos.
    """

    status: Literal["success"] = "success"
    report: Report
    metadata: ReportMetadata


class ErrorResponse(BaseResponse):
    """Contrato de resposta de erro para POST /analyze."""

    status: Literal["error"] = "error"
    error_code: ErrorCodeStr
    message: NonEmptyStr
