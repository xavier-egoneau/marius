"""Tests de la factory partagée de construction du registre d'outils."""

from __future__ import annotations

from pathlib import Path

import pytest

from marius.storage.memory_store import MemoryStore
from marius.tools.factory import STATIC_ENTRIES, build_tool_entries


@pytest.fixture()
def memory_store(tmp_path: Path) -> MemoryStore:
    s = MemoryStore(db_path=tmp_path / "memory.db")
    yield s
    s.close()


# ── enabled_tools=None : tous les outils ─────────────────────────────────────


def test_all_tools_when_none(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries(None, memory_store, tmp_path)
    names = {e.definition.name for e in entries}
    assert names >= set(STATIC_ENTRIES.keys())
    assert "memory" in names
    assert "open_marius_web" in names


def test_memory_always_present_when_none(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries(None, memory_store, tmp_path)
    assert any(e.definition.name == "memory" for e in entries)


# ── filtrage par enabled_tools ────────────────────────────────────────────────


def test_only_enabled_tools_included(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries(["read_file", "run_bash"], memory_store, tmp_path)
    names = {e.definition.name for e in entries}
    assert "read_file" in names
    assert "run_bash" in names
    assert "web_search" not in names
    assert "list_dir" not in names


def test_memory_injected_even_if_absent_from_list(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries(["read_file"], memory_store, tmp_path)
    names = {e.definition.name for e in entries}
    assert "memory" in names


def test_unknown_tool_name_silently_ignored(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries(["read_file", "outil_inexistant"], memory_store, tmp_path)
    names = {e.definition.name for e in entries}
    assert "outil_inexistant" not in names
    assert "read_file" in names


def test_empty_enabled_tools_still_has_memory(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries([], memory_store, tmp_path)
    names = {e.definition.name for e in entries}
    assert "memory" in names
    assert len(names) == 1


# ── extras ────────────────────────────────────────────────────────────────────


def test_extra_tool_included_when_none(memory_store: MemoryStore, tmp_path: Path) -> None:
    from marius.kernel.tool_router import ToolDefinition, ToolEntry
    from marius.kernel.contracts import ToolResult

    extra = ToolEntry(
        definition=ToolDefinition(name="custom", description="test", parameters={}),
        handler=lambda _: ToolResult(tool_call_id="", ok=True, summary="ok"),
    )
    entries = build_tool_entries(None, memory_store, tmp_path, extras={"custom": extra})
    names = {e.definition.name for e in entries}
    assert "custom" in names


def test_extra_tool_injected_even_if_absent_from_enabled(
    memory_store: MemoryStore, tmp_path: Path
) -> None:
    from marius.kernel.tool_router import ToolDefinition, ToolEntry
    from marius.kernel.contracts import ToolResult

    extra = ToolEntry(
        definition=ToolDefinition(name="reminders", description="test", parameters={}),
        handler=lambda _: ToolResult(tool_call_id="", ok=True, summary="ok"),
    )
    entries = build_tool_entries(["read_file"], memory_store, tmp_path, extras={"reminders": extra})
    names = {e.definition.name for e in entries}
    assert "reminders" in names


def test_no_duplicate_entries(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries(None, memory_store, tmp_path)
    names = [e.definition.name for e in entries]
    assert len(names) == len(set(names))
