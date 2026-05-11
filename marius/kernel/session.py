"""Session runtime canonique du kernel.

Cette brique gère l'état conversationnel court sans dépendre d'un canal concret
ni d'une représentation UI de l'historique visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .contracts import Artifact, CompactionNotice, Message, Role, ToolResult
from .tool_result_context import format_tool_result_for_context


@dataclass(slots=True)
class TurnRecord:
    id: str
    input_messages: list[Message]
    started_at: datetime
    assistant_message: Message | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    extra_artifacts: list[Artifact] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionState:
    session_id: str
    turns: list[TurnRecord] = field(default_factory=list)
    compaction_notices: list[CompactionNotice] = field(default_factory=list)
    derived_context_summary: str = ""
    derived_context_summary_message: Message | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionRuntime:
    """Gestionnaire minimal de session logique côté kernel."""

    def __init__(self, *, session_id: str, metadata: dict[str, Any] | None = None) -> None:
        self.state = SessionState(session_id=session_id, metadata=dict(metadata or {}))

    @property
    def session_id(self) -> str:
        return self.state.session_id

    def start_turn(
        self,
        *,
        user_message: Message,
        metadata: dict[str, Any] | None = None,
    ) -> TurnRecord:
        if user_message.role is not Role.USER:
            raise ValueError("start_turn expects a message with role Role.USER")
        turn_metadata = {"status": "started", **dict(metadata or {})}
        turn = TurnRecord(
            id=self._next_turn_id(),
            input_messages=[user_message],
            started_at=user_message.created_at,
            metadata=turn_metadata,
        )
        self.state.turns.append(turn)
        return turn

    def attach_tool_result(self, turn_id: str, result: ToolResult) -> TurnRecord:
        turn = self._require_turn(turn_id)
        if any(existing.tool_call_id == result.tool_call_id for existing in turn.tool_results):
            return turn
        turn.tool_results.append(result)
        self._sync_turn_artifacts(turn)
        return turn

    def finish_turn(
        self,
        turn_id: str,
        *,
        assistant_message: Message | None = None,
        artifacts: list[Artifact] | None = None,
    ) -> TurnRecord:
        turn = self._require_turn(turn_id)
        if assistant_message is not None:
            if assistant_message.role is not Role.ASSISTANT:
                raise ValueError("finish_turn expects a message with role Role.ASSISTANT")
            turn.assistant_message = assistant_message
        if artifacts is not None:
            turn.extra_artifacts = list(artifacts)
        turn.metadata["status"] = "completed"
        self._sync_turn_artifacts(turn)
        return turn

    def register_compaction_summary(
        self,
        summary: str,
        *,
        notice: CompactionNotice | None = None,
    ) -> None:
        self.state.derived_context_summary = summary
        self.state.derived_context_summary_message = Message(
            role=Role.SYSTEM,
            content=summary,
            created_at=datetime.now(timezone.utc),
            visible=False,
            metadata={"kind": "compaction_summary"},
        )
        if notice is not None:
            self.state.compaction_notices.append(notice)

    def internal_messages(
        self,
        *,
        include_summary: bool = False,
        include_tool_results: bool = False,
        recent_turn_limit: int | None = None,
    ) -> list[Message]:
        messages: list[Message] = []
        if include_summary and self.state.derived_context_summary_message is not None:
            messages.append(self.state.derived_context_summary_message)

        turns = self.state.turns
        if recent_turn_limit is not None and recent_turn_limit >= 0:
            turns = turns[-recent_turn_limit:] if recent_turn_limit else []

        for turn in turns:
            messages.extend(turn.input_messages)
            if include_tool_results:
                for result in turn.tool_results:
                    if result.summary or result.data or result.artifacts or result.error:
                        messages.append(
                            Message(
                                role=Role.TOOL,
                                content=format_tool_result_for_context(result),
                                created_at=turn.started_at,
                                correlation_id=result.tool_call_id,
                                visible=False,
                                artifacts=list(result.artifacts),
                            )
                        )
            if turn.assistant_message is not None:
                messages.append(turn.assistant_message)
        return messages

    def _require_turn(self, turn_id: str) -> TurnRecord:
        for turn in self.state.turns:
            if turn.id == turn_id:
                return turn
        raise KeyError(f"Unknown turn_id: {turn_id}")

    def _sync_turn_artifacts(self, turn: TurnRecord) -> None:
        artifacts: list[Artifact] = []
        for result in turn.tool_results:
            artifacts.extend(result.artifacts)
        if turn.assistant_message is not None:
            artifacts.extend(turn.assistant_message.artifacts)
        artifacts.extend(turn.extra_artifacts)

        deduped: list[Artifact] = []
        seen: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
        for artifact in artifacts:
            key = (
                artifact.type.value,
                artifact.path,
                tuple(sorted((str(data_key), repr(value)) for data_key, value in artifact.data.items())),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(artifact)
        turn.artifacts = deduped

    def _next_turn_id(self) -> str:
        return f"turn-{len(self.state.turns) + 1}"
