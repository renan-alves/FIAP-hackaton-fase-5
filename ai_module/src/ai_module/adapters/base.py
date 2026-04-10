"""Base interface for LLM adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    """Classe base abstrata para todos os adaptadores de provedores LLM."""

    @abstractmethod
    async def analyze(self, image_bytes: bytes, prompt: str, system_prompt: str) -> str:
        """Envie uma imagem e uma solicitação ao provedor de LLM e retorne a resposta bruta.

        Gera os seguintes erros:
            LLMTimeoutError: se a chamada exceder o tempo limite configurado.
            LLMCallError: em caso de falha do SDK ou do provedor.
        """
        ...
