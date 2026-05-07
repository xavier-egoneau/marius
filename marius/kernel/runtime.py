"""Orchestrateur minimal du kernel.

Ce module définit le pipeline logique d'un tour sans dépendre d'un canal concret.
Il prépare le contexte pour le provider à partir d'une session logique du kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .compaction import (
    CompactionConfig,
    compaction_level,
    estimate_tokens_from_messages,
    resolve_token_count,
)
from .contracts import CompactionNotice, ContextUsage, Message, Role, ToolResult
from .provider import ProviderAdapter, ProviderError, ProviderRequest
from .session import SessionRuntime


@dataclass(slots=True)
class TurnInput:
    session: SessionRuntime
    user_message: Message
    system_prompt: str = ""
    usage: ContextUsage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TurnOutput:
    context_messages: list[Message] = field(default_factory=list)
    assistant_message: Message | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    usage: ContextUsage = field(default_factory=ContextUsage)
    compaction_notice: CompactionNotice | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeOrchestrator:
    """Assemblage minimal des briques kernel autour d'une session logique."""

    def __init__(
        self,
        *,
        compaction_config: CompactionConfig | None = None,
        provider: ProviderAdapter | None = None,
    ) -> None:
        self.compaction_config = compaction_config or CompactionConfig()
        self.provider = provider

    def run_turn(self, turn_input: TurnInput) -> TurnOutput:
        turn = turn_input.session.start_turn(
            user_message=turn_input.user_message,
            metadata=turn_input.metadata,
        )
        context_messages = turn_input.session.internal_messages(
            include_summary=True,
            include_tool_results=True,
        )
        if turn_input.system_prompt:
            context_messages = [
                Message(
                    role=Role.SYSTEM,
                    content=turn_input.system_prompt,
                    created_at=turn_input.user_message.created_at,
                    visible=False,
                    metadata={"kind": "system_prompt"},
                ),
                *context_messages,
            ]

        usage = self._build_usage(context_messages, turn_input.usage)
        level = compaction_level(
            resolve_token_count(usage),
            self._effective_compaction_config(usage),
        )

        compaction_notice: CompactionNotice | None = None
        if level.value != "none":
            compaction_notice = CompactionNotice(
                level=level.value,
                metadata={
                    "session_id": turn_input.session.session_id,
                    "visible_history_untouched": True,
                },
            )

        output = TurnOutput(
            context_messages=context_messages,
            usage=usage,
            compaction_notice=compaction_notice,
            metadata={
                "status": "ready_for_provider",
                "session_id": turn_input.session.session_id,
                "turn_id": turn.id,
                "message_count": len(context_messages),
                "compaction_level": level.value,
                "system_prompt": turn_input.system_prompt,
            },
        )

        if self.provider is None:
            return output

        try:
            provider_response = self.provider.generate(
                ProviderRequest(
                    messages=context_messages,
                    metadata={
                        **turn_input.metadata,
                        "session_id": turn_input.session.session_id,
                        "turn_id": turn.id,
                    },
                )
            )
        except ProviderError as error:
            turn.metadata.update(
                {
                    "status": "provider_error",
                    "provider_name": error.provider_name,
                    "retryable": error.retryable,
                    "error": str(error),
                }
            )
            raise
        turn_input.session.finish_turn(turn.id, assistant_message=provider_response.message)
        output.assistant_message = provider_response.message
        output.usage = self._merge_usage(output.usage, provider_response.usage)
        output.metadata.update(
            {
                "status": "completed",
                "provider_name": provider_response.provider_name,
                "model": provider_response.model,
            }
        )
        return output

    def _build_usage(
        self,
        context_messages: list[Message],
        provided_usage: ContextUsage | None,
    ) -> ContextUsage:
        usage = provided_usage or ContextUsage()
        estimated_tokens = usage.estimated_input_tokens or estimate_tokens_from_messages(
            context_messages
        )
        max_context_tokens = usage.max_context_tokens or self.compaction_config.context_window_tokens
        return ContextUsage(
            estimated_input_tokens=estimated_tokens,
            provider_input_tokens=usage.provider_input_tokens,
            max_context_tokens=max_context_tokens,
        )

    def _effective_compaction_config(self, usage: ContextUsage) -> CompactionConfig:
        return CompactionConfig(
            context_window_tokens=usage.max_context_tokens or self.compaction_config.context_window_tokens,
            trim_threshold=self.compaction_config.trim_threshold,
            summarize_threshold=self.compaction_config.summarize_threshold,
            reset_threshold=self.compaction_config.reset_threshold,
            keep_recent_turns=self.compaction_config.keep_recent_turns,
        )

    def _merge_usage(self, base: ContextUsage, override: ContextUsage) -> ContextUsage:
        return ContextUsage(
            estimated_input_tokens=override.estimated_input_tokens or base.estimated_input_tokens,
            provider_input_tokens=(
                override.provider_input_tokens
                if override.provider_input_tokens is not None
                else base.provider_input_tokens
            ),
            max_context_tokens=override.max_context_tokens or base.max_context_tokens,
        )
