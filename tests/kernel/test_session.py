from __future__ import annotations

from datetime import datetime

from marius.kernel.contracts import Artifact, ArtifactType, Message, Role, ToolResult
from marius.kernel.session import SessionRuntime


def test_session_runtime_groups_messages_and_tool_results_per_turn() -> None:
    runtime = SessionRuntime(session_id="canon")
    user_message = Message(
        role=Role.USER,
        content="Lance les tests du projet",
        created_at=datetime(2026, 5, 7, 14, 0, 0),
    )

    turn = runtime.start_turn(user_message=user_message, metadata={"source": "host"})
    assert turn.metadata["status"] == "started"
    runtime.attach_tool_result(
        turn.id,
        ToolResult(
            tool_call_id="tool-1",
            ok=True,
            summary="pytest: 12 passed",
            artifacts=[Artifact(type=ArtifactType.REPORT, data={"path": "report.txt"})],
        ),
    )

    assistant_message = Message(
        role=Role.ASSISTANT,
        content="Les tests sont verts.",
        created_at=datetime(2026, 5, 7, 14, 0, 3),
    )
    completed = runtime.finish_turn(turn.id, assistant_message=assistant_message)

    assert completed.input_messages == [user_message]
    assert completed.assistant_message == assistant_message
    assert completed.metadata["status"] == "completed"
    assert [result.summary for result in completed.tool_results] == ["pytest: 12 passed"]
    assert completed.artifacts[0].type is ArtifactType.REPORT
    assert runtime.state.turns == [completed]


def test_internal_messages_stay_kernel_focused_and_can_include_summary_notice() -> None:
    runtime = SessionRuntime(session_id="branch-1")
    first_turn = runtime.start_turn(
        user_message=Message(
            role=Role.USER,
            content="Résumé du ticket",
            created_at=datetime(2026, 5, 7, 14, 1, 0),
        )
    )
    runtime.finish_turn(
        first_turn.id,
        assistant_message=Message(
            role=Role.ASSISTANT,
            content="Voici le résumé.",
            created_at=datetime(2026, 5, 7, 14, 1, 2),
        ),
    )

    runtime.register_compaction_summary(
        "Contexte précédent compacté autour du ticket courant."
    )

    messages = runtime.internal_messages(include_summary=True)

    assert [message.role for message in messages] == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
    ]
    assert messages[0].metadata["kind"] == "compaction_summary"
    assert messages[0].content.startswith("Contexte précédent compacté")


def test_internal_messages_can_be_limited_to_recent_turns_without_ui_history_logic() -> None:
    runtime = SessionRuntime(session_id="branch-2")
    for index in range(3):
        turn = runtime.start_turn(
            user_message=Message(
                role=Role.USER,
                content=f"message-{index}",
                created_at=datetime(2026, 5, 7, 14, 2, index),
            )
        )
        runtime.finish_turn(
            turn.id,
            assistant_message=Message(
                role=Role.ASSISTANT,
                content=f"réponse-{index}",
                created_at=datetime(2026, 5, 7, 14, 3, index),
            ),
        )

    messages = runtime.internal_messages(recent_turn_limit=1)

    assert [message.content for message in messages] == ["message-2", "réponse-2"]


def test_session_runtime_rejects_invalid_roles_for_turn_boundaries() -> None:
    runtime = SessionRuntime(session_id="canon")

    try:
        runtime.start_turn(
            user_message=Message(
                role=Role.ASSISTANT,
                content="not-a-user-message",
                created_at=datetime(2026, 5, 7, 14, 5, 0),
            )
        )
    except ValueError as exc:
        assert "Role.USER" in str(exc)
    else:
        raise AssertionError("start_turn should reject non-user messages")


def test_session_runtime_is_idempotent_for_tool_results_and_assistant_message() -> None:
    runtime = SessionRuntime(session_id="canon")
    turn = runtime.start_turn(
        user_message=Message(
            role=Role.USER,
            content="run tests",
            created_at=datetime(2026, 5, 7, 14, 6, 0),
        )
    )
    result = ToolResult(
        tool_call_id="tool-1",
        ok=True,
        summary="done",
        artifacts=[Artifact(type=ArtifactType.REPORT, data={"path": "report.txt"})],
    )
    assistant_message = Message(
        role=Role.ASSISTANT,
        content="OK",
        created_at=datetime(2026, 5, 7, 14, 6, 1),
        artifacts=[Artifact(type=ArtifactType.REPORT, data={"path": "assistant.txt"})],
    )

    runtime.attach_tool_result(turn.id, result)
    runtime.attach_tool_result(turn.id, result)
    runtime.finish_turn(turn.id, assistant_message=assistant_message)
    runtime.finish_turn(turn.id, assistant_message=assistant_message)

    completed = runtime.state.turns[0]
    assert [tool.tool_call_id for tool in completed.tool_results] == ["tool-1"]
    assert len(completed.artifacts) == 2


def test_compaction_summary_message_is_stable_between_reads() -> None:
    runtime = SessionRuntime(session_id="canon")
    runtime.register_compaction_summary("summary")

    first = runtime.internal_messages(include_summary=True)[0]
    second = runtime.internal_messages(include_summary=True)[0]

    assert first.created_at == second.created_at
    assert first.metadata == second.metadata
