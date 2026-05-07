"""Provider adapter minimal pour Marius.

Cette brique normalise l'appel à un provider LLM sans dépendre d'un host concret.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from .contracts import ContextUsage, Message, Role


@dataclass(slots=True)
class ProviderConfig:
    provider_name: str
    model: str


@dataclass(slots=True)
class ProviderRequest:
    messages: list[Message]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResponse:
    message: Message
    usage: ContextUsage = field(default_factory=ContextUsage)
    provider_name: str = ""
    model: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider_name: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_name = provider_name
        self.retryable = retryable


class ProviderAdapter(Protocol):
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...


class InMemoryProviderAdapter:
    """Double de test pour valider le contrat provider du runtime."""

    def __init__(
        self,
        *,
        config: ProviderConfig,
        completion_text: str = "",
        usage: ContextUsage | None = None,
        error: ProviderError | None = None,
    ) -> None:
        self.config = config
        self.completion_text = completion_text
        self.usage = usage or ContextUsage()
        self.error = error
        self.calls: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        created_at = request.messages[-1].created_at if request.messages else datetime.now(timezone.utc)
        return ProviderResponse(
            message=Message(
                role=Role.ASSISTANT,
                content=self.completion_text,
                created_at=created_at,
                metadata={
                    "provider_name": self.config.provider_name,
                    "model": self.config.model,
                },
            ),
            usage=self.usage,
            provider_name=self.config.provider_name,
            model=self.config.model,
        )
