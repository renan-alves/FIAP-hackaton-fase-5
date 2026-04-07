"""Request validation models for the analysis endpoint.

This module defines the input schema for the /analyze endpoint,
ensuring strict validation of the analysis identifier.
"""

from __future__ import annotations

from pydantic import UUID4, BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    """Request schema for POST /analyze endpoint.

    Parameters
    ----------
    analysis_id : UUID4 
        Unique identifier for this analysis request.
        Must be a valid UUID v4 format.
    """

    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID4 = Field(
        description="Unique identifier for the analysis request (UUID v4 format)"
    )