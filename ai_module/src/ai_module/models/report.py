"""Pydantic models for architecture analysis reports.

The models in this module follow the report contract defined in `specs/spec.md`.
All models reject unknown fields (`extra="forbid"`) and enforce strict enums.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComponentType(str, Enum):
    """Supported architecture component categories."""

    SERVICE = "service"
    DATABASE = "database"
    QUEUE = "queue"
    GATEWAY = "gateway"
    CACHE = "cache"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Risk severity levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Priority(str, Enum):
    """Recommendation priority levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Component(BaseModel):
    """A component identified in the architecture diagram."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    type: ComponentType
    description: str = Field(min_length=1, max_length=500)


class Risk(BaseModel):
    """A risk identified during architecture analysis."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    severity: Severity
    description: str = Field(min_length=1, max_length=500)
    affected_components: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """An action recommended to improve the architecture."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    priority: Priority
    description: str = Field(min_length=1, max_length=500)


class Report(BaseModel):
    """Top-level report payload returned by the AI pipeline."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=500)
    components: list[Component] = Field(min_length=1)
    risks: list[Risk] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class ReportMetadata(BaseModel):
    """Metadata describing how the report was generated."""

    model_config = ConfigDict(extra="forbid")

    model_used: str = Field(min_length=1)
    processing_time_ms: int = Field(ge=0)
    input_type: Literal["image", "pdf"]


class AnalyzeResponse(BaseModel):
    """Successful response contract for POST /analyze."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(min_length=1)
    status: Literal["success"] = "success"
    report: Report
    metadata: ReportMetadata


class ErrorResponse(BaseModel):
    """Error response contract for POST /analyze."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(min_length=1)
    status: Literal["error"] = "error"
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)