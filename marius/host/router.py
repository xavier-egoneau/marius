"""Entrées host normalisées pour les canaux concrets.

Le host reste une surface mince : il transforme une requête entrante en
`TurnInput`, orchestre le kernel puis renvoie un payload visible.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from marius.kernel.contracts import Artifact, Message, Role
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.render.adapter import RenderSurface, render_turn_output
from marius.storage.ui_history import InMemoryVisibleHistoryStore, VisibleHistoryEntry


@dataclass(slots=True)
class InboundRequest:
    channel: str
    session_id: str
    peer_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutboundPayload:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class HostRouter:
    """Routeur minimal entre un canal concret et le runtime kernel."""

    def __init__(
        self,
        *,
        orchestrator: RuntimeOrchestrator,
        history_store: InMemoryVisibleHistoryStore | None = None,
        sessions: MutableMapping[str, SessionRuntime] | None = None,
        system_prompt: str = "",
    ) -> None:
        self.orchestrator = orchestrator
        self.history_store = history_store or InMemoryVisibleHistoryStore()
        self.sessions = sessions or {}
        self.system_prompt = system_prompt

    def route(self, request: InboundRequest) -> OutboundPayload:
        session = self._get_or_create_session(request)
        user_message = self._build_message(request, role=Role.USER)
        turn_metadata = self._build_turn_metadata(request)

        self.history_store.append(
            request.session_id,
            VisibleHistoryEntry(
                role=Role.USER.value,
                content=request.text,
                metadata=dict(turn_metadata),
            ),
        )

        turn_output = self.orchestrator.run_turn(
            TurnInput(
                session=session,
                user_message=user_message,
                system_prompt=self.system_prompt,
                metadata=turn_metadata,
            )
        )

        if turn_output.assistant_message is not None:
            rendered_text = render_turn_output(
                turn_output.assistant_message,
                tool_results=turn_output.tool_results,
                compaction_notice=turn_output.compaction_notice,
                surface=_surface_for_channel(request.channel),
            )
            self.history_store.append(
                request.session_id,
                self._visible_entry_from_message(turn_output.assistant_message, content=rendered_text),
            )
        else:
            rendered_text = render_turn_output(
                None,
                tool_results=turn_output.tool_results,
                compaction_notice=turn_output.compaction_notice,
                surface=_surface_for_channel(request.channel),
            ) or "Requête prête pour le provider."

        payload_metadata = {
            **turn_output.metadata,
            "channel": request.channel,
            "peer_id": request.peer_id,
            "session_id": request.session_id,
        }
        if turn_output.compaction_notice is not None:
            payload_metadata["compaction_level"] = turn_output.compaction_notice.level
        return OutboundPayload(text=rendered_text, metadata=payload_metadata)

    def _get_or_create_session(self, request: InboundRequest) -> SessionRuntime:
        session = self.sessions.get(request.session_id)
        if session is None:
            session = SessionRuntime(
                session_id=request.session_id,
                metadata={
                    "channel": request.channel,
                    "peer_id": request.peer_id,
                },
            )
            self.sessions[request.session_id] = session
        return session

    def _build_turn_metadata(self, request: InboundRequest) -> dict[str, Any]:
        return {
            "channel": request.channel,
            "peer_id": request.peer_id,
            **dict(request.metadata),
        }

    def _build_message(self, request: InboundRequest, *, role: Role) -> Message:
        return Message(
            role=role,
            content=request.text,
            created_at=datetime.now(timezone.utc),
            metadata=self._build_turn_metadata(request),
        )

    def _visible_entry_from_message(self, message: Message, *, content: str | None = None) -> VisibleHistoryEntry:
        return VisibleHistoryEntry(
            role=message.role.value,
            content=message.content if content is None else content,
            metadata=dict(message.metadata),
            artifacts=[self._artifact_to_dict(artifact) for artifact in message.artifacts],
        )

    @staticmethod
    def _artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
        return {
            "type": artifact.type.value,
            "path": artifact.path,
            "data": dict(artifact.data),
        }


def _surface_for_channel(channel: str) -> RenderSurface:
    try:
        return RenderSurface(channel)
    except ValueError:
        return RenderSurface.PORTABLE
