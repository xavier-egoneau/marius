"""Tests de la boucle agentique du RuntimeOrchestrator avec outils."""

from __future__ import annotations

from datetime import datetime

import pytest

from marius.kernel.contracts import ContextUsage, Message, Role, ToolCall, ToolResult
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.tool_router import ToolDefinition, ToolEntry, ToolRouter


def _session() -> SessionRuntime:
    return SessionRuntime(session_id="test")


def _user(text: str = "Go") -> Message:
    return Message(role=Role.USER, content=text, created_at=datetime(2026, 5, 8, 10, 0, 0))


def _echo_tool() -> ToolEntry:
    def handler(args: dict) -> ToolResult:
        return ToolResult(tool_call_id="", ok=True, summary=f"echo: {args.get('text', '')}")
    return ToolEntry(
        definition=ToolDefinition(
            name="echo",
            description="Retourne le texte passé.",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        ),
        handler=handler,
    )


def test_runtime_executes_tool_and_returns_final_response():
    tool_call = ToolCall(id="c1", name="echo", arguments={"text": "bonjour"})
    provider = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="J'ai échoé.",
        tool_call_sequence=[[tool_call]],
    )
    router = ToolRouter([_echo_tool()])
    orchestrator = RuntimeOrchestrator(provider=provider, tool_router=router)

    output = orchestrator.run_turn(TurnInput(session=_session(), user_message=_user()))

    assert output.assistant_message is not None
    assert output.assistant_message.content == "J'ai échoé."
    assert len(output.tool_results) == 1
    assert output.tool_results[0].ok is True
    assert "bonjour" in output.tool_results[0].summary


def test_runtime_tool_callbacks_are_called():
    tool_call = ToolCall(id="c1", name="echo", arguments={"text": "test"})
    provider = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="Done.",
        tool_call_sequence=[[tool_call]],
    )
    router = ToolRouter([_echo_tool()])
    orchestrator = RuntimeOrchestrator(provider=provider, tool_router=router)

    started = []
    completed = []

    output = orchestrator.run_turn(
        TurnInput(session=_session(), user_message=_user()),
        on_tool_start=lambda call: started.append(call.name),
        on_tool_result=lambda call, result: completed.append(result.ok),
    )

    assert started == ["echo"]
    assert completed == [True]


def test_runtime_handles_unknown_tool_gracefully():
    tool_call = ToolCall(id="c1", name="nonexistent", arguments={})
    provider = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="Impossible.",
        tool_call_sequence=[[tool_call]],
    )
    router = ToolRouter([])  # aucun outil enregistré
    orchestrator = RuntimeOrchestrator(provider=provider, tool_router=router)

    output = orchestrator.run_turn(TurnInput(session=_session(), user_message=_user()))

    assert len(output.tool_results) == 1
    assert output.tool_results[0].ok is False
    assert "nonexistent" in output.tool_results[0].summary


def test_runtime_two_sequential_tool_calls():
    call1 = ToolCall(id="c1", name="echo", arguments={"text": "premier"})
    call2 = ToolCall(id="c2", name="echo", arguments={"text": "second"})
    provider = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="Les deux.",
        tool_call_sequence=[[call1], [call2]],
    )
    router = ToolRouter([_echo_tool()])
    orchestrator = RuntimeOrchestrator(provider=provider, tool_router=router)

    output = orchestrator.run_turn(TurnInput(session=_session(), user_message=_user()))

    assert len(output.tool_results) == 2
    assert output.assistant_message.content == "Les deux."


def test_runtime_tool_results_are_stored_in_session():
    tool_call = ToolCall(id="c1", name="echo", arguments={"text": "check"})
    provider = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="Stored.",
        tool_call_sequence=[[tool_call]],
    )
    router = ToolRouter([_echo_tool()])
    orchestrator = RuntimeOrchestrator(provider=provider, tool_router=router)
    session = _session()

    orchestrator.run_turn(TurnInput(session=session, user_message=_user()))

    turn = session.state.turns[0]
    assert len(turn.tool_results) == 1
    assert turn.tool_results[0].ok is True


def test_runtime_injects_structured_tool_data_into_next_provider_request():
    def handler(_args: dict) -> ToolResult:
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="2 résultat(s)",
            data={
                "results": [
                    {
                        "title": "Marius web search",
                        "url": "https://example.test/marius",
                        "content": "Snippet utile.",
                    }
                ]
            },
        )

    tool_call = ToolCall(id="c1", name="search", arguments={"query": "marius"})
    provider = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="Synthèse sourcée.",
        tool_call_sequence=[[tool_call]],
    )
    router = ToolRouter(
        [
            ToolEntry(
                definition=ToolDefinition(name="search", description="Search"),
                handler=handler,
            )
        ]
    )
    orchestrator = RuntimeOrchestrator(provider=provider, tool_router=router)

    orchestrator.run_turn(TurnInput(session=_session(), user_message=_user()))

    second_request = provider.calls[1]
    tool_messages = [message for message in second_request.messages if message.role is Role.TOOL]
    assert len(tool_messages) == 1
    assert "2 résultat(s)" in tool_messages[0].content
    assert "Marius web search" in tool_messages[0].content
    assert "https://example.test/marius" in tool_messages[0].content
