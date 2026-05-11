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


def test_memory_tool_search_returns_matching_memories(tmp_path):
    store = MemoryStore(db_path=tmp_path / "memory.db")
    try:
        tool = make_memory_tool(store, tmp_path)
        store.add("Le projet utilise pytest", category="agent_notes")
        store.add("Aime les réponses courtes", category="user_profile")

        result = tool.handler({"action": "search", "query": "pytest"})

        assert result.ok is True
        assert result.data["memories"][0]["content"] == "Le projet utilise pytest"
        assert "pytest" in result.summary
    finally:
        store.close()


def test_memory_tool_list_can_filter_by_target(tmp_path):
    store = MemoryStore(db_path=tmp_path / "memory.db")
    try:
        tool = make_memory_tool(store, tmp_path)
        store.add("Note agent", category="agent_notes")
        store.add("Profil user", category="user_profile")

        result = tool.handler({"action": "list", "target": "user"})

        assert result.ok is True
        contents = [m["content"] for m in result.data["memories"]]
        assert contents == ["Profil user"]
    finally:
        store.close()


def test_memory_tool_get_returns_memory_by_id(tmp_path):
    store = MemoryStore(db_path=tmp_path / "memory.db")
    try:
        tool = make_memory_tool(store, tmp_path)
        memory_id = store.add("Souvenir précis", category="agent_notes")

        result = tool.handler({"action": "get", "memory_id": memory_id})

        assert result.ok is True
        assert result.data["memories"][0]["memory_id"] == memory_id
        assert "Souvenir précis" in result.summary
    finally:
        store.close()


def test_memory_tool_get_unknown_id_returns_error(tmp_path):
    store = MemoryStore(db_path=tmp_path / "memory.db")
    try:
        tool = make_memory_tool(store, tmp_path)

        result = tool.handler({"action": "get", "memory_id": 999})

        assert result.ok is False
        assert result.error == "memory_not_found"
    finally:
        store.close()
