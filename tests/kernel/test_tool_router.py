from __future__ import annotations

import pytest

from marius.kernel.contracts import ToolCall, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry, ToolRouter


def _make_entry(name: str, ok: bool = True, summary: str = "ok") -> ToolEntry:
    def handler(args: dict) -> ToolResult:
        return ToolResult(tool_call_id="", ok=ok, summary=summary)
    return ToolEntry(
        definition=ToolDefinition(name=name, description=f"Tool {name}", parameters={}),
        handler=handler,
    )


def test_tool_router_dispatch_known_tool():
    router = ToolRouter([_make_entry("read_file", summary="file content")])
    result = router.dispatch(ToolCall(id="c1", name="read_file", arguments={}))
    assert result.ok is True
    assert result.summary == "file content"


def test_tool_router_dispatch_unknown_tool():
    router = ToolRouter([])
    result = router.dispatch(ToolCall(id="c1", name="unknown_tool", arguments={}))
    assert result.ok is False
    assert "unknown_tool" in result.summary


def test_tool_router_definitions_returns_all():
    router = ToolRouter([_make_entry("a"), _make_entry("b")])
    defs = router.definitions()
    assert {d.name for d in defs} == {"a", "b"}


def test_tool_router_contains():
    router = ToolRouter([_make_entry("read_file")])
    assert "read_file" in router
    assert "write_file" not in router


def test_tool_router_len():
    router = ToolRouter([_make_entry("a"), _make_entry("b")])
    assert len(router) == 2


def test_tool_router_captures_exception_as_tool_result():
    def bad_handler(args: dict) -> ToolResult:
        raise ValueError("explosion")

    entry = ToolEntry(
        definition=ToolDefinition(name="bad", description="", parameters={}),
        handler=bad_handler,
    )
    router = ToolRouter([entry])
    result = router.dispatch(ToolCall(id="c1", name="bad", arguments={}))
    assert result.ok is False
    assert "explosion" in result.summary


def test_tool_router_passes_arguments_to_handler():
    received = {}

    def handler(args: dict) -> ToolResult:
        received.update(args)
        return ToolResult(tool_call_id="", ok=True, summary="done")

    entry = ToolEntry(
        definition=ToolDefinition(name="echo", description="", parameters={}),
        handler=handler,
    )
    router = ToolRouter([entry])
    router.dispatch(ToolCall(id="c1", name="echo", arguments={"foo": "bar"}))
    assert received == {"foo": "bar"}


def test_tool_router_fills_missing_tool_call_id():
    entry = _make_entry("echo")
    router = ToolRouter([entry])

    result = router.dispatch(ToolCall(id="call_123", name="echo", arguments={}))

    assert result.tool_call_id == "call_123"


def test_tool_router_preserves_handler_tool_call_id():
    def handler(args: dict) -> ToolResult:
        return ToolResult(tool_call_id="custom", ok=True, summary="done")

    entry = ToolEntry(
        definition=ToolDefinition(name="echo", description="", parameters={}),
        handler=handler,
    )
    router = ToolRouter([entry])

    result = router.dispatch(ToolCall(id="call_123", name="echo", arguments={}))

    assert result.tool_call_id == "custom"
