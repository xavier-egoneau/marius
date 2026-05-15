"""Tests de la factory partagée de construction du registre d'outils."""

from __future__ import annotations

from pathlib import Path

import pytest

from marius.storage.memory_store import MemoryStore
from marius.config.contracts import ALL_TOOLS
from marius.tools.factory import STATIC_ENTRIES, build_tool_entries, registered_tool_names
from marius.provider_config.contracts import AuthType, ProviderEntry, ProviderKind


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
    assert "host_status" in names
    assert "host_gateway_restart" in names
    assert "project_list" in names
    assert "approval_list" in names
    assert "secret_ref_list" in names
    assert "secret_ref_prepare_file" in names
    assert "provider_list" in names
    assert "self_update_propose" in names
    assert "self_update_apply" in names
    assert "self_update_rollback" in names
    assert "rag_source_add" in names
    assert "rag_search" in names
    assert "rag_checklist_add" in names
    assert "reminders" in names
    assert "browser_open" in names
    assert "browser_close" in names
    assert "call_agent" in names


def test_config_tool_catalog_comes_from_factory() -> None:
    assert ALL_TOOLS == registered_tool_names()


def test_dynamic_dreaming_tools_included_when_entry_is_available(
    memory_store: MemoryStore, tmp_path: Path
) -> None:
    entry = ProviderEntry(
        id="p1",
        name="test",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        api_key="secret:test",
        model="gpt-test",
    )
    entries = build_tool_entries(None, memory_store, tmp_path, entry=entry, active_skills=["dev"])
    names = {e.definition.name for e in entries}

    assert "dreaming_run" in names


def test_runtime_bound_tools_are_built_by_factory(
    memory_store: MemoryStore, tmp_path: Path
) -> None:
    entry = ProviderEntry(
        id="p1",
        name="test",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        api_key="secret:test",
        model="gpt-test",
    )

    entries = build_tool_entries(
        ["read_file", "reminders", "browser_open", "spawn_agent", "call_agent"],
        memory_store,
        tmp_path,
        entry=entry,
    )
    names = {e.definition.name for e in entries}

    assert {"read_file", "reminders", "browser_open", "spawn_agent", "call_agent"} <= names


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
        definition=ToolDefinition(name="custom_extra", description="test", parameters={}),
        handler=lambda _: ToolResult(tool_call_id="", ok=True, summary="ok"),
    )
    entries = build_tool_entries(["read_file"], memory_store, tmp_path, extras={"custom_extra": extra})
    names = {e.definition.name for e in entries}
    assert "custom_extra" in names


def test_no_duplicate_entries(memory_store: MemoryStore, tmp_path: Path) -> None:
    entries = build_tool_entries(None, memory_store, tmp_path)
    names = [e.definition.name for e in entries]
    assert len(names) == len(set(names))
