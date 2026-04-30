"""Request validation models for the analysis endpoint.

This module defines the input schema for the /analyze endpoint.
Per GUD-006, analysis_id is accepted as a plain string — format
validation is delegated to the orchestrator (SOAT).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    """Esquema de requisição para o endpoint POST /analyze.

    Parameters
    ----------
    analysis_id : str
        Identificador rastreável fornecido pelo orquestrador.
        Aceito como string pura — validação de formato delegada ao SOAT (GUD-006).
    context_text : str | None
        Texto de contexto opcional. Máximo de 1000 caracteres.
    """

    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(..., description="Identificador da análise")
    context_text: str | None = Field(default=None, max_length=1000)
