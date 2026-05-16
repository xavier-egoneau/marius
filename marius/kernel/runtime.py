"""Orchestrateur minimal du kernel.

Ce module définit le pipeline logique d'un tour sans dépendre d'un canal concret.
Gère la boucle agentique : appel provider → outils → appel provider → … → réponse finale.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .compaction import (
    CompactionConfig,
    CompactionLevel,
    compaction_level,
    estimate_tokens_from_messages,
    resolve_token_count,
)
from .contracts import CompactionNotice, ContextUsage, Message, Role, ToolCall, ToolResult
from .provider import ProviderAdapter, ProviderError, ProviderRequest, ProviderResponse
from .session import SessionRuntime
from .tool_result_context import format_tool_result_for_context
from .tool_router import ToolRouter

_MAX_TOOL_ITERATIONS = 20
_MAX_PROVIDER_RETRIES = 2          # retries for transient ProviderErrors

_FINAL_RESPONSE_INSTRUCTION = (
    "La limite d'appels outils de ce tour est atteinte. "
    "N'appelle plus aucun outil. Produis maintenant la réponse finale pour l'utilisateur : "
    "résume ce qui a été fait, signale ce qui reste incertain ou non vérifié, "
    "et propose une prochaine étape utile si elle existe."
)

_EMPTY_RESPONSE_NUDGE = (
    "Tu as reçu les résultats des outils. "
    "Produis maintenant la réponse finale pour l'utilisateur sans appeler d'outils supplémentaires."
)

_COMPACTION_SUMMARY = (
    "[Contexte compacté automatiquement — les tours les plus anciens ont été retirés "
    "du contexte actif. La conversation continue depuis les tours récents conservés.]"
)

_COMPACTION_CONTINUATION_HINT = (
    "Le contexte de cette conversation vient d'être compacté pour libérer de la place. "
    "Ne répète pas le travail déjà effectué et ne relance pas des outils "
    "dont les résultats sont déjà visibles dans le contexte."
)


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
        is_cancelled: Callable[[], bool] | None = None,
    ) -> TurnOutput:
        # ── [1] Snapshot du contexte AVANT de démarrer le nouveau tour ──────────
        prior_messages = turn_input.session.internal_messages(
            include_summary=True,
            include_tool_results=True,
        )

        # ── [2] Évaluation du niveau de compaction ───────────────────────────────
        # On estime sur prior_messages + user_message pour anticiper la pression
        # réelle que ce tour va ajouter.
        probe_messages = list(prior_messages) + [turn_input.user_message]
        usage = self._build_usage(probe_messages, turn_input.usage)
        level = compaction_level(
            resolve_token_count(usage),
            self._effective_compaction_config(usage),
        )

        compaction_notice: CompactionNotice | None = None
        _compacted = False

        # ── [3] Auto-compaction pré-tour (SUMMARIZE / RESET) ─────────────────────
        # Pour TRIM on laisse passer — le contexte est sous les 75%, c'est gérable.
        # Pour SUMMARIZE/RESET on tronque les tours anciens AVANT de démarrer
        # le nouveau tour, pour ne pas dépasser la fenêtre provider.
        if level in (CompactionLevel.SUMMARIZE, CompactionLevel.RESET):
            compaction_notice = CompactionNotice(
                level=level.value,
                metadata={
                    "session_id": turn_input.session.session_id,
                    "auto": True,
                    "visible_history_untouched": True,
                },
            )
            kept = self.compaction_config.keep_recent_turns
            # Pour RESET on est encore plus agressif
            if level == CompactionLevel.RESET:
                kept = max(1, kept // 2)

            if len(turn_input.session.state.turns) > kept:
                turn_input.session.state.turns = turn_input.session.state.turns[-kept:]
                turn_input.session.register_compaction_summary(
                    _COMPACTION_SUMMARY,
                    notice=compaction_notice,
                )
                # Reconstruire prior_messages depuis la session tronquée
                prior_messages = turn_input.session.internal_messages(
                    include_summary=True,
                    include_tool_results=True,
                )
                _compacted = True

        elif level == CompactionLevel.TRIM and not compaction_notice:
            compaction_notice = CompactionNotice(
                level=level.value,
                metadata={
                    "session_id": turn_input.session.session_id,
                    "visible_history_untouched": True,
                },
            )

        # ── [4] Démarrage du tour ────────────────────────────────────────────────
        turn = turn_input.session.start_turn(
            user_message=turn_input.user_message,
            metadata=turn_input.metadata,
        )

        # ── [5] Construction de provider_messages ────────────────────────────────
        # Ordre : [system?] + prior_messages + [continuation_hint?] + user_message
        provider_messages: list[Message] = list(prior_messages)

        if turn_input.system_prompt:
            system_msg = Message(
                role=Role.SYSTEM,
                content=turn_input.system_prompt,
                created_at=turn_input.user_message.created_at,
                visible=False,
                metadata={"kind": "system_prompt"},
            )
            provider_messages = [system_msg, *provider_messages]

        # Hint de continuation injecté juste avant le message utilisateur
        if _compacted:
            hint_msg = Message(
                role=Role.SYSTEM,
                content=_COMPACTION_CONTINUATION_HINT,
                created_at=turn_input.user_message.created_at,
                visible=False,
                metadata={"kind": "compaction_continuation_hint"},
            )
            provider_messages.append(hint_msg)

        provider_messages.append(turn_input.user_message)

        # Recalcul usage post-compaction pour le TurnOutput
        usage = self._build_usage(provider_messages, turn_input.usage)

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
                "compacted_this_turn": _compacted,
                "system_prompt": turn_input.system_prompt,
            },
        )

        if self.provider is None:
            return output

        # ── [6] Boucle agentique ─────────────────────────────────────────────────
        tools = self.tool_router.definitions() if self.tool_router else []
        all_tool_results: list[ToolResult] = []
        final_message: Message | None = None
        use_streaming = on_text_delta is not None and hasattr(self.provider, "stream")
        _empty_retry_done = False  # guard: un seul retry sur réponse vide

        try:
            for _iteration in range(_MAX_TOOL_ITERATIONS):
                if is_cancelled is not None and is_cancelled():
                    raise KeyboardInterrupt
                request = ProviderRequest(
                    messages=provider_messages,
                    tools=tools,
                    metadata={
                        **turn_input.metadata,
                        "session_id": turn_input.session.session_id,
                        "turn_id": turn.id,
                    },
                )

                # Appel provider avec retry sur erreurs transientes (hors streaming)
                provider_response = self._call_provider(
                    request,
                    use_streaming=use_streaming,
                    on_text_delta=on_text_delta,
                    is_cancelled=is_cancelled,
                )

                usage = self._merge_usage(usage, provider_response.usage)

                if provider_response.finish_reason == "tool_calls" and provider_response.tool_calls:
                    provider_messages.append(provider_response.message)

                    for tool_call in provider_response.tool_calls:
                        if is_cancelled is not None and is_cancelled():
                            raise KeyboardInterrupt
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

                        if is_cancelled is not None and is_cancelled():
                            raise KeyboardInterrupt
                        if on_tool_result:
                            on_tool_result(tool_call, result)

                        tool_msg = Message(
                            role=Role.TOOL,
                            content=format_tool_result_for_context(result),
                            created_at=datetime.now(timezone.utc),
                            correlation_id=tool_call.id,
                            visible=False,
                        )
                        provider_messages.append(tool_msg)

                    continue  # prochain tour provider

                # Réponse finale — retry si vide (une seule tentative)
                if not provider_response.message.content.strip() and not _empty_retry_done:
                    _empty_retry_done = True
                    nudge = Message(
                        role=Role.SYSTEM,
                        content=_EMPTY_RESPONSE_NUDGE,
                        created_at=datetime.now(timezone.utc),
                        visible=False,
                        metadata={"kind": "empty_response_nudge"},
                    )
                    provider_messages.append(nudge)
                    continue  # relancer sans outils

                final_message = provider_response.message
                break

            # Limite d'itérations atteinte sans réponse finale
            if final_message is None:
                provider_response = self._request_final_response(
                    provider_messages,
                    turn_input=turn_input,
                    turn_id=turn.id,
                    on_text_delta=on_text_delta if use_streaming else None,
                    is_cancelled=is_cancelled,
                )
                usage = self._merge_usage(usage, provider_response.usage)
                final_message = provider_response.message
                if not final_message.content.strip():
                    final_message = Message(
                        role=Role.ASSISTANT,
                        content=self._fallback_final_response(all_tool_results),
                        created_at=datetime.now(timezone.utc),
                        metadata={"kind": "tool_iteration_limit_fallback"},
                    )
                turn.metadata["tool_iteration_limit_reached"] = True

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

        # ── [7] Persistance en session ───────────────────────────────────────────
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
                "tool_iteration_limit_reached": turn.metadata.get(
                    "tool_iteration_limit_reached",
                    False,
                ),
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

    def cancel_current_provider(self) -> None:
        cancel = getattr(self.provider, "cancel_current_request", None)
        if callable(cancel):
            cancel()

    # ── provider call with retry ──────────────────────────────────────────────

    def _call_provider(
        self,
        request: ProviderRequest,
        *,
        use_streaming: bool,
        on_text_delta: Callable[[str], None] | None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> ProviderResponse:
        """Appel provider avec retry exponentiel sur erreurs transientes."""
        if use_streaming:
            last_error: ProviderError | None = None
            for attempt in range(_MAX_PROVIDER_RETRIES + 1):
                stream_started = False

                def _track_delta(delta: str) -> None:
                    nonlocal stream_started
                    if delta:
                        stream_started = True
                    if on_text_delta:
                        on_text_delta(delta)

                try:
                    if is_cancelled is not None and is_cancelled():
                        raise KeyboardInterrupt
                    return self._run_streaming(
                        request,
                        on_text_delta=_track_delta,
                        is_cancelled=is_cancelled,
                    )
                except ProviderError as exc:
                    if stream_started or not exc.retryable or attempt == _MAX_PROVIDER_RETRIES:
                        raise
                    last_error = exc
                    time.sleep(2 ** attempt)  # 1s, 2s

            raise last_error  # type: ignore[misc]  # ne peut pas être None ici

        last_error: ProviderError | None = None
        for attempt in range(_MAX_PROVIDER_RETRIES + 1):
            try:
                if is_cancelled is not None and is_cancelled():
                    raise KeyboardInterrupt
                return self.provider.generate(request)  # type: ignore[union-attr]
            except ProviderError as exc:
                if not exc.retryable or attempt == _MAX_PROVIDER_RETRIES:
                    raise
                last_error = exc
                time.sleep(2 ** attempt)  # 1s, 2s

        raise last_error  # type: ignore[misc]  # ne peut pas être None ici

    # ── streaming ─────────────────────────────────────────────────────────────

    def _request_final_response(
        self,
        provider_messages: list[Message],
        *,
        turn_input: TurnInput,
        turn_id: str,
        on_text_delta: Callable[[str], None] | None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> ProviderResponse:
        final_instruction = Message(
            role=Role.SYSTEM,
            content=_FINAL_RESPONSE_INSTRUCTION,
            created_at=datetime.now(timezone.utc),
            visible=False,
            metadata={"kind": "final_response_instruction"},
        )
        request = ProviderRequest(
            messages=[*provider_messages, final_instruction],
            tools=[],
            metadata={
                **turn_input.metadata,
                "session_id": turn_input.session.session_id,
                "turn_id": turn_id,
                "forced_final_response": True,
            },
        )
        if on_text_delta is not None:
            return self._call_provider(
                request,
                use_streaming=True,
                on_text_delta=on_text_delta,
                is_cancelled=is_cancelled,
            )
        if is_cancelled is not None and is_cancelled():
            raise KeyboardInterrupt
        return self.provider.generate(request)  # type: ignore[union-attr]

    def _fallback_final_response(self, tool_results: list[ToolResult]) -> str:
        recent = [result for result in tool_results[-5:] if result.summary]
        if not recent:
            return (
                "J'ai atteint la limite d'appels outils avant de pouvoir formuler "
                "un récap complet. Je n'ai pas de résultat exploitable à résumer."
            )
        lines = [
            "J'ai atteint la limite d'appels outils avant de pouvoir formuler un récap complet.",
            "Derniers résultats observés :",
        ]
        for result in recent:
            status = "ok" if result.ok else "échec"
            summary = " ".join(result.summary.split())
            if len(summary) > 220:
                summary = f"{summary[:217]}..."
            lines.append(f"- {status} : {summary}")
        lines.append("Prochaine étape utile : relancer un tour court pour vérifier et finaliser proprement.")
        return "\n".join(lines)

    def _run_streaming(
        self,
        request: ProviderRequest,
        *,
        on_text_delta: Callable[[str], None] | None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> ProviderResponse:
        """Consomme le stream et reconstruit un ProviderResponse complet."""
        from .provider import ProviderChunk

        text_buf = ""
        tool_calls: list[ToolCall] = []
        finish_reason = "stop"
        final_usage = ContextUsage()

        try:
            for chunk in self.provider.stream(request):  # type: ignore[union-attr]
                if is_cancelled is not None and is_cancelled():
                    raise KeyboardInterrupt
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
                            provider_output_tokens=chunk.usage.get("output_tokens"),
                        )
                    elif chunk.usage and isinstance(chunk.usage, ContextUsage):
                        final_usage = chunk.usage
                    if chunk.finish_reason and not tool_calls:
                        finish_reason = chunk.finish_reason
        except Exception:
            if is_cancelled is not None and is_cancelled():
                raise KeyboardInterrupt
            raise

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

    # ── helpers ───────────────────────────────────────────────────────────────

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
            provider_output_tokens=usage.provider_output_tokens,
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
            provider_output_tokens=(
                override.provider_output_tokens
                if override.provider_output_tokens is not None
                else base.provider_output_tokens
            ),
            max_context_tokens=override.max_context_tokens or base.max_context_tokens,
        )
