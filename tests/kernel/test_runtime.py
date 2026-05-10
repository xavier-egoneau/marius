from __future__ import annotations

from datetime import datetime

from marius.kernel.compaction import CompactionConfig, CompactionLevel
from marius.kernel.contracts import ContextUsage, Message, Role, ToolCall, ToolResult
from marius.kernel.provider import (
    InMemoryProviderAdapter,
    ProviderConfig,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.tool_router import ToolDefinition, ToolEntry, ToolRouter


def test_runtime_orchestrator_registers_turn_and_prepares_provider_context() -> None:
    session = SessionRuntime(session_id="canon")
    orchestrator = RuntimeOrchestrator()
    user_message = Message(
        role=Role.USER,
        content="Fais le point sur la roadmap",
        created_at=datetime(2026, 5, 7, 15, 0, 0),
    )

    output = orchestrator.run_turn(
        TurnInput(
            session=session,
            user_message=user_message,
            system_prompt="Tu es Marius.",
        )
    )

    assert session.state.turns[0].input_messages == [user_message]
    assert [message.content for message in output.context_messages] == [
        "Tu es Marius.",
        "Fais le point sur la roadmap",
    ]
    assert output.context_messages[0].role is Role.SYSTEM
    assert output.metadata["status"] == "ready_for_provider"
    assert output.metadata["session_id"] == "canon"
    assert output.metadata["turn_id"] == "turn-1"
    assert output.metadata["compaction_level"] == CompactionLevel.NONE.value
    assert output.usage.estimated_input_tokens > 0


def test_runtime_orchestrator_uses_provider_usage_for_compaction_notice() -> None:
    session = SessionRuntime(session_id="canon")
    orchestrator = RuntimeOrchestrator(
        compaction_config=CompactionConfig(context_window_tokens=250000)
    )
    user_message = Message(
        role=Role.USER,
        content="x" * 20,
        created_at=datetime(2026, 5, 7, 15, 1, 0),
    )

    output = orchestrator.run_turn(
        TurnInput(
            session=session,
            user_message=user_message,
            usage=ContextUsage(
                estimated_input_tokens=5,
                provider_input_tokens=90,
                max_context_tokens=100,
            ),
        )
    )

    assert output.compaction_notice is not None
    assert output.compaction_notice.level == CompactionLevel.RESET.value
    assert output.compaction_notice.metadata["visible_history_untouched"] is True
    assert output.metadata["compaction_level"] == CompactionLevel.RESET.value
    assert output.usage.provider_input_tokens == 90


def test_runtime_orchestrator_reinjects_previous_tool_results_into_context() -> None:
    session = SessionRuntime(session_id="canon")
    previous_turn = session.start_turn(
        user_message=Message(
            role=Role.USER,
            content="Lance pytest",
            created_at=datetime(2026, 5, 7, 15, 2, 0),
        )
    )
    session.attach_tool_result(
        previous_turn.id,
        ToolResult(tool_call_id="tool-1", ok=True, summary="pytest: 15 passed"),
    )
    session.finish_turn(
        previous_turn.id,
        assistant_message=Message(
            role=Role.ASSISTANT,
            content="Les tests sont passés.",
            created_at=datetime(2026, 5, 7, 15, 2, 1),
        ),
    )

    orchestrator = RuntimeOrchestrator()
    output = orchestrator.run_turn(
        TurnInput(
            session=session,
            user_message=Message(
                role=Role.USER,
                content="Fais le résumé",
                created_at=datetime(2026, 5, 7, 15, 3, 0),
            ),
        )
    )

    assert "pytest: 15 passed" in [message.content for message in output.context_messages]


def test_runtime_orchestrator_calls_provider_and_finishes_turn() -> None:
    session = SessionRuntime(session_id="canon")
    provider = InMemoryProviderAdapter(
        config=ProviderConfig(provider_name="test", model="stub-model"),
        completion_text="Réponse finale",
        usage=ContextUsage(provider_input_tokens=33, max_context_tokens=1000),
    )
    orchestrator = RuntimeOrchestrator(provider=provider)

    output = orchestrator.run_turn(
        TurnInput(
            session=session,
            user_message=Message(
                role=Role.USER,
                content="Donne-moi la synthèse",
                created_at=datetime(2026, 5, 7, 15, 31, 0),
            ),
            system_prompt="Tu es Marius.",
        )
    )

    assert output.assistant_message is not None
    assert output.assistant_message.content == "Réponse finale"
    assert output.usage.provider_input_tokens == 33
    assert session.state.turns[-1].assistant_message == output.assistant_message
    assert session.state.turns[-1].metadata["status"] == "completed"
    assert output.metadata["status"] == "completed"
    assert output.metadata["provider_name"] == "test"


def test_runtime_orchestrator_marks_turn_when_provider_fails() -> None:
    session = SessionRuntime(session_id="canon")
    provider = InMemoryProviderAdapter(
        config=ProviderConfig(provider_name="test", model="stub-model"),
        error=ProviderError("provider down", provider_name="test", retryable=True),
    )
    orchestrator = RuntimeOrchestrator(provider=provider)

    try:
        orchestrator.run_turn(
            TurnInput(
                session=session,
                user_message=Message(
                    role=Role.USER,
                    content="Essaie quand même",
                    created_at=datetime(2026, 5, 7, 15, 35, 0),
                ),
            )
        )
        raise AssertionError("ProviderError should have been raised")
    except ProviderError as error:
        assert str(error) == "provider down"

    turn = session.state.turns[-1]
    assert turn.metadata["status"] == "provider_error"
    assert turn.metadata["provider_name"] == "test"
    assert turn.metadata["retryable"] is True
    assert turn.assistant_message is None


def test_runtime_orchestrator_preserves_existing_provider_usage_when_provider_returns_none() -> None:
    session = SessionRuntime(session_id="canon")
    provider = InMemoryProviderAdapter(
        config=ProviderConfig(provider_name="test", model="stub-model"),
        completion_text="Réponse finale",
        usage=ContextUsage(max_context_tokens=1000),
    )
    orchestrator = RuntimeOrchestrator(provider=provider)

    output = orchestrator.run_turn(
        TurnInput(
            session=session,
            user_message=Message(
                role=Role.USER,
                content="Donne-moi la synthèse",
                created_at=datetime(2026, 5, 7, 15, 36, 0),
            ),
            usage=ContextUsage(provider_input_tokens=21, max_context_tokens=1000),
        )
    )

    assert output.usage.provider_input_tokens == 21


def test_runtime_orchestrator_forces_final_response_when_tool_loop_limit_is_reached() -> None:
    class LoopingToolProvider:
        def __init__(self) -> None:
            self.requests: list[ProviderRequest] = []

        def generate(self, request: ProviderRequest) -> ProviderResponse:
            self.requests.append(request)
            if not request.tools:
                return ProviderResponse(
                    message=Message(
                        role=Role.ASSISTANT,
                        content="Récap final forcé.",
                        created_at=datetime(2026, 5, 7, 16, 0, 0),
                    ),
                    finish_reason="stop",
                    provider_name="test",
                    model="stub-model",
                )
            call = ToolCall(id=f"tool-{len(self.requests)}", name="noop", arguments={})
            return ProviderResponse(
                message=Message(
                    role=Role.ASSISTANT,
                    content="",
                    created_at=datetime(2026, 5, 7, 16, 0, 0),
                    tool_calls=[call],
                ),
                tool_calls=[call],
                finish_reason="tool_calls",
                provider_name="test",
                model="stub-model",
            )

    def noop(_arguments: dict) -> ToolResult:
        return ToolResult(tool_call_id="", ok=True, summary="noop ok")

    session = SessionRuntime(session_id="canon")
    provider = LoopingToolProvider()
    router = ToolRouter(
        [
            ToolEntry(
                ToolDefinition(name="noop", description="No-op"),
                noop,
            )
        ]
    )
    orchestrator = RuntimeOrchestrator(provider=provider, tool_router=router)

    output = orchestrator.run_turn(
        TurnInput(
            session=session,
            user_message=Message(
                role=Role.USER,
                content="Fais la tâche",
                created_at=datetime(2026, 5, 7, 16, 0, 0),
            ),
        )
    )

    assert output.assistant_message is not None
    assert output.assistant_message.content == "Récap final forcé."
    assert output.metadata["tool_iteration_limit_reached"] is True
    assert provider.requests[-1].tools == []
    assert provider.requests[-1].metadata["forced_final_response"] is True
    assert session.state.turns[-1].assistant_message == output.assistant_message
