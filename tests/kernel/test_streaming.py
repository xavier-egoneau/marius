"""Tests du streaming dans le runtime et les adapters."""

from __future__ import annotations

from datetime import datetime

from marius.kernel.contracts import ContextUsage, ToolCall
from marius.kernel.provider import InMemoryProviderAdapter, ProviderChunk, ProviderConfig, ProviderRequest
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.contracts import Message, Role
from marius.kernel.tool_router import ToolDefinition, ToolEntry, ToolRouter
from marius.kernel.contracts import ToolResult


def _user(text: str = "Go") -> Message:
    return Message(role=Role.USER, content=text, created_at=datetime(2026, 5, 8, 10, 0, 0))


def _session() -> SessionRuntime:
    return SessionRuntime(session_id="stream-test")


def _adapter(text: str = "Bonjour !") -> InMemoryProviderAdapter:
    return InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text=text,
    )


# ── InMemoryProviderAdapter.stream() ─────────────────────────────────────────


def test_in_memory_adapter_stream_yields_text_delta():
    adapter = _adapter("Salut")
    chunks = list(adapter.stream(ProviderRequest(messages=[])))
    types = [c.type for c in chunks]
    assert "text_delta" in types
    assert "done" in types


def test_in_memory_adapter_stream_text_matches_completion():
    adapter = _adapter("Réponse complète")
    deltas = "".join(c.delta for c in adapter.stream(ProviderRequest(messages=[])) if c.type == "text_delta")
    assert deltas == "Réponse complète"


def test_in_memory_adapter_stream_tool_calls_emits_tool_calls_chunk():
    tool_call = ToolCall(id="c1", name="echo", arguments={"text": "test"})
    adapter = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="Done.",
        tool_call_sequence=[[tool_call]],
    )
    chunks = list(adapter.stream(ProviderRequest(messages=[])))
    tc_chunks = [c for c in chunks if c.type == "tool_calls"]
    assert len(tc_chunks) == 1
    assert tc_chunks[0].tool_calls[0].name == "echo"


# ── RuntimeOrchestrator streaming ────────────────────────────────────────────


def test_runtime_uses_streaming_when_on_text_delta_provided():
    adapter = _adapter("Token par token")
    orchestrator = RuntimeOrchestrator(provider=adapter)

    received: list[str] = []
    output = orchestrator.run_turn(
        TurnInput(session=_session(), user_message=_user()),
        on_text_delta=received.append,
    )

    assert "".join(received) == "Token par token"
    assert output.assistant_message is not None
    assert output.assistant_message.content == "Token par token"


def test_runtime_falls_back_to_generate_without_on_text_delta():
    adapter = _adapter("Sans streaming")
    orchestrator = RuntimeOrchestrator(provider=adapter)

    output = orchestrator.run_turn(
        TurnInput(session=_session(), user_message=_user()),
    )
    assert output.assistant_message.content == "Sans streaming"


def test_runtime_streaming_with_tool_calls():
    def _echo_handler(args: dict) -> ToolResult:
        return ToolResult(tool_call_id="", ok=True, summary=f"echo:{args.get('text', '')}")

    tool_call = ToolCall(id="c1", name="echo", arguments={"text": "world"})
    adapter = InMemoryProviderAdapter(
        config=ProviderConfig("test", "stub"),
        completion_text="Terminé.",
        tool_call_sequence=[[tool_call]],
    )
    router = ToolRouter([ToolEntry(
        definition=ToolDefinition(name="echo", description="", parameters={}),
        handler=_echo_handler,
    )])
    orchestrator = RuntimeOrchestrator(provider=adapter, tool_router=router)

    text_deltas: list[str] = []
    tool_starts: list[str] = []

    output = orchestrator.run_turn(
        TurnInput(session=_session(), user_message=_user()),
        on_text_delta=text_deltas.append,
        on_tool_start=lambda call: tool_starts.append(call.name),
    )

    assert "echo" in tool_starts
    assert output.assistant_message.content == "Terminé."
    assert len(output.tool_results) == 1
