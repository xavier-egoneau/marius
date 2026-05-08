from __future__ import annotations

from marius.kernel.contracts import ToolCall
from marius.kernel.tool_router import ToolRouter
from marius.storage.memory_store import MemoryStore
from marius.tools.memory import make_memory_tool


def test_memory_tool_add_returns_valid_tool_result(tmp_path):
    store = MemoryStore(db_path=tmp_path / "memory.db")
    try:
        tool = make_memory_tool(store, tmp_path)

        result = tool.handler({"action": "add", "target": "agent", "content": "Préférence stable"})

        assert result.ok is True
        assert result.tool_call_id == ""
        assert result.data["target"] == "agent"
        assert store.list()[0].content == "Préférence stable"
    finally:
        store.close()


def test_memory_tool_router_fills_call_id(tmp_path):
    store = MemoryStore(db_path=tmp_path / "memory.db")
    try:
        router = ToolRouter([make_memory_tool(store, tmp_path)])

        result = router.dispatch(
            ToolCall(
                id="call-memory",
                name="memory",
                arguments={"action": "add", "target": "user", "content": "Aime les réponses concises"},
            )
        )

        assert result.ok is True
        assert result.tool_call_id == "call-memory"
    finally:
        store.close()


def test_memory_tool_validation_returns_valid_tool_result(tmp_path):
    store = MemoryStore(db_path=tmp_path / "memory.db")
    try:
        tool = make_memory_tool(store, tmp_path)

        result = tool.handler({"action": "add", "target": "agent"})

        assert result.ok is False
        assert result.tool_call_id == ""
        assert "content" in result.summary
    finally:
        store.close()
