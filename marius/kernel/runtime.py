"""Orchestrateur minimal du kernel.

Ce module définit le pipeline logique d'un tour sans dépendre d'un canal concret.
Gère la boucle agentique : appel provider → outils → appel provider → … → réponse finale.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .compaction import (
    CompactionConfig,
    compaction_level,
    estimate_tokens_from_messages,
    resolve_token_count,
)
from .contracts import CompactionNotice, ContextUsage, Message, Role, ToolCall, ToolResult
from .provider import ProviderAdapter, ProviderError, ProviderRequest, ProviderResponse
from .session import SessionRuntime
from .tool_router import ToolRouter

_MAX_TOOL_ITERATIONS = 20


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
        tool_router: ToolRouter | None = None,
    ) -> None:
        self.compaction_config = compaction_config or CompactionConfig()
        self.provider = provider
        self.tool_router = tool_router

    def run_turn(
        self,
        turn_input: TurnInput,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        on_tool_start: Callable[[ToolCall], None] | None = None,
        on_tool_result: Callable[[ToolCall, ToolResult], None] | None = None,
    ) -> TurnOutput:
        # Capturer le contexte des tours précédents AVANT de démarrer le nouveau tour.
        prior_messages = turn_input.session.internal_messages(
            include_summary=True,
            include_tool_results=True,
        )

        turn = turn_input.session.start_turn(
            user_message=turn_input.user_message,
            metadata=turn_input.metadata,
        )

        # La liste de messages envoyée au provider est gérée manuellement
        # pendant la boucle agentique pour conserver l'ordre précis :
        # [system?] + prior_messages + user + [asst_tool_calls + tool_results]*
        provider_messages: list[Message] = list(prior_messages) + [turn_input.user_message]

        if turn_input.system_prompt:
            system_msg = Message(
                role=Role.SYSTEM,
                content=turn_input.system_prompt,
                created_at=turn_input.user_message.created_at,
                visible=False,
                metadata={"kind": "system_prompt"},
            )
            provider_messages = [system_msg, *provider_messages]

        usage = self._build_usage(provider_messages, turn_input.usage)
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
            context_messages=provider_messages,
            usage=usage,
            compaction_notice=compaction_notice,
            metadata={
                "status": "ready_for_provider",
                "session_id": turn_input.session.session_id,
                "turn_id": turn.id,
                "message_count": len(provider_messages),
                "compaction_level": level.value,
                "system_prompt": turn_input.system_prompt,
            },
        )

        if self.provider is None:
            return output

        # --- boucle agentique ---
        tools = self.tool_router.definitions() if self.tool_router else []
        all_tool_results: list[ToolResult] = []
        final_message: Message | None = None
        use_streaming = on_text_delta is not None and hasattr(self.provider, "stream")

        try:
            for _iteration in range(_MAX_TOOL_ITERATIONS):
                request = ProviderRequest(
                    messages=provider_messages,
                    tools=tools,
                    metadata={
                        **turn_input.metadata,
                        "session_id": turn_input.session.session_id,
                        "turn_id": turn.id,
                    },
                )

                if use_streaming:
                    provider_response = self._run_streaming(request, on_text_delta=on_text_delta)
                else:
                    provider_response = self.provider.generate(request)

                usage = self._merge_usage(usage, provider_response.usage)

                if provider_response.finish_reason == "tool_calls" and provider_response.tool_calls:
                    # Ajouter le message assistant (avec tool_calls) au contexte
                    provider_messages.append(provider_response.message)

                    # Exécuter les outils
                    for tool_call in provider_response.tool_calls:
                        if on_tool_start:
                            on_tool_start(tool_call)

                        result = (
                            self.tool_router.dispatch(tool_call)
                            if self.tool_router
                            else ToolResult(
                                tool_call_id=tool_call.id,
                                ok=False,
                                summary=f"Aucun tool_router configuré pour {tool_call.name!r}.",
                            )
                        )
                        all_tool_results.append(result)

                        if on_tool_result:
                            on_tool_result(tool_call, result)

                        # Ajouter le résultat comme message tool dans le contexte
                        tool_msg = Message(
                            role=Role.TOOL,
                            content=result.summary if result.ok else (result.error or result.summary),
                            created_at=datetime.now(timezone.utc),
                            correlation_id=tool_call.id,
                            visible=False,
                        )
                        provider_messages.append(tool_msg)

                    continue  # prochain tour provider

                # Réponse finale (texte)
                final_message = provider_response.message
                break

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

        # Enregistrer dans la session
        for result in all_tool_results:
            turn_input.session.attach_tool_result(turn.id, result)

        if final_message is not None:
            turn_input.session.finish_turn(turn.id, assistant_message=final_message)

        output.assistant_message = final_message
        output.tool_results = all_tool_results
        output.usage = self._merge_usage(output.usage, usage)
        output.metadata.update(
            {
                "status": "completed",
                "tool_calls_count": len(all_tool_results),
            }
        )
        if final_message is not None:
            output.metadata.update(
                {
                    "provider_name": provider_response.provider_name,  # type: ignore[possibly-undefined]
                    "model": provider_response.model,                   # type: ignore[possibly-undefined]
                }
            )
        return output

    # --- streaming ---

    def _run_streaming(
        self,
        request: ProviderRequest,
        *,
        on_text_delta: Callable[[str], None] | None,
    ) -> ProviderResponse:
        """Consomme le stream et reconstruit un ProviderResponse complet."""
        from .provider import ProviderChunk

        text_buf = ""
        tool_calls: list[ToolCall] = []
        finish_reason = "stop"
        final_usage = ContextUsage()

        for chunk in self.provider.stream(request):  # type: ignore[union-attr]
            if chunk.type == "text_delta":
                text_buf += chunk.delta
                if on_text_delta:
                    on_text_delta(chunk.delta)
            elif chunk.type == "tool_calls":
                tool_calls = chunk.tool_calls
                finish_reason = chunk.finish_reason or "tool_calls"
            elif chunk.type in ("usage", "done"):
                if chunk.usage and isinstance(chunk.usage, dict):
                    final_usage = ContextUsage(
                        estimated_input_tokens=chunk.usage.get("input_tokens", 0),
                        provider_input_tokens=chunk.usage.get("input_tokens"),
                    )
                elif chunk.usage and isinstance(chunk.usage, ContextUsage):
                    final_usage = chunk.usage
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason

        assistant_msg = Message(
            role=Role.ASSISTANT,
            content=text_buf,
            created_at=datetime.now(timezone.utc),
            tool_calls=tool_calls,
        )
        return ProviderResponse(
            message=assistant_msg,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=final_usage,
        )

    # --- helpers ---

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
