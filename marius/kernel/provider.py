"""Provider adapter pour Marius.

Définit le protocole d'accès à un LLM et le double de test en mémoire.
Les implémentations HTTP concrètes vivent dans adapters/.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

from .contracts import ContextUsage, Message, Role, ToolCall

if TYPE_CHECKING:
    from marius.kernel.tool_router import ToolDefinition


@dataclass(slots=True)
class ProviderConfig:
    provider_name: str
    model: str


@dataclass(slots=True)
class ProviderRequest:
    messages: list[Message]
    tools: list[ToolDefinition] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResponse:
    message: Message
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"          # "stop" | "tool_calls"
    usage: ContextUsage = field(default_factory=ContextUsage)
    provider_name: str = ""
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderChunk:
    """Fragment d'une réponse streamée."""

    type: str                              # "text_delta" | "tool_calls" | "usage" | "done"
    delta: str = ""                        # pour type == "text_delta"
    tool_calls: list[ToolCall] = field(default_factory=list)   # pour type == "tool_calls"
    finish_reason: str = ""                # "stop" | "tool_calls" | ""
    usage: ContextUsage | None = None      # pour type == "usage" ou "done"


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

    def stream(self, request: ProviderRequest) -> Iterator[ProviderChunk]:
        ...


class InMemoryProviderAdapter:
    """Double de test : retourne une réponse fixe ou lève une erreur configurée.

    Supporte aussi la simulation d'un tour avec appel d'outil via `tool_call_sequence`.
    """

    def __init__(
        self,
        *,
        config: ProviderConfig,
        completion_text: str = "",
        usage: ContextUsage | None = None,
        error: ProviderError | None = None,
        tool_call_sequence: list[list[ToolCall]] | None = None,
    ) -> None:
        self.config = config
        self.completion_text = completion_text
        self.usage = usage or ContextUsage()
        self.error = error
        self.tool_call_sequence = tool_call_sequence or []
        self.calls: list[ProviderRequest] = []
        self._call_index = 0

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error

        created_at = request.messages[-1].created_at if request.messages else datetime.now(timezone.utc)

        # Si une séquence d'appels d'outils est configurée, retourner le prochain
        if self._call_index < len(self.tool_call_sequence):
            tool_calls = self.tool_call_sequence[self._call_index]
            self._call_index += 1
            return ProviderResponse(
                message=Message(
                    role=Role.ASSISTANT,
                    content="",
                    created_at=created_at,
                    tool_calls=list(tool_calls),
                ),
                tool_calls=list(tool_calls),
                finish_reason="tool_calls",
                usage=self.usage,
                provider_name=self.config.provider_name,
                model=self.config.model,
            )

        self._call_index += 1
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
            finish_reason="stop",
            usage=self.usage,
            provider_name=self.config.provider_name,
            model=self.config.model,
        )

    def stream(self, request: ProviderRequest) -> Iterator[ProviderChunk]:
        """Simule le streaming : délègue à generate() et émet les chunks."""
        response = self.generate(request)
        if response.tool_calls:
            yield ProviderChunk(
                type="tool_calls",
                tool_calls=response.tool_calls,
                finish_reason="tool_calls",
            )
        else:
            yield ProviderChunk(type="text_delta", delta=response.message.content)
        yield ProviderChunk(
            type="done",
            finish_reason=response.finish_reason,
            usage=response.usage,
        )
