from __future__ import annotations

from marius.storage.memory_store import MemoryStore
from marius.tools.rag import make_rag_tools


def test_rag_tools_add_sync_search_and_promote(tmp_path):
    source_dir = tmp_path / "knowledge"
    source_dir.mkdir()
    (source_dir / "rules.md").write_text(
        "# Rules\n\n[important] Keep useful facts in memory only when promoted.\n",
        encoding="utf-8",
    )
    memory = MemoryStore(tmp_path / "memory.db")
    tools = make_rag_tools(tmp_path / "rag", memory_store=memory, cwd=tmp_path)

    added = tools["rag_source_add"].handler({
        "name": "Rules",
        "path": str(source_dir),
        "scope": "org",
        "audience": "devs",
    })
    assert added.ok is True

    synced = tools["rag_source_sync"].handler({"source_id": added.data["source"]["id"]})
    assert synced.ok is True
    assert synced.data["reports"][0]["report"]["important_chunks"] == 1

    found = tools["rag_search"].handler({"query": "memory"})
    assert found.ok is True
    assert len(found.data["chunks"]) == 1
    assert found.artifacts[0].data["display"] is False

    promoted = tools["rag_promote_to_memory"].handler({
        "chunk_id": found.data["chunks"][0]["id"],
        "memory_scope": "global",
    })
    assert promoted.ok is True
    assert memory.get(promoted.data["memory_id"]) is not None
    memory.close()


def test_rag_search_without_query_returns_important_chunks(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\n[important] One important note.\n", encoding="utf-8")
    tools = make_rag_tools(tmp_path / "rag")

    added = tools["rag_source_add"].handler({"name": "Notes", "path": str(source), "scope": "user"})
    tools["rag_source_sync"].handler({"source_id": added.data["source"]["id"]})

    result = tools["rag_search"].handler({})

    assert result.ok is True
    assert len(result.data["chunks"]) == 1


def test_rag_source_sync_reports_document_inventory(tmp_path):
    source_dir = tmp_path / "secondBrain"
    lists_dir = source_dir / "lists"
    lists_dir.mkdir(parents=True)
    (lists_dir / "courses.md").write_text("# Courses\n\n- Cafe\n- bananes\n", encoding="utf-8")
    tools = make_rag_tools(tmp_path / "rag")

    added = tools["rag_source_add"].handler({"name": "secondBrain", "path": str(source_dir), "scope": "user"})
    synced = tools["rag_source_sync"].handler({"source_id": added.data["source"]["id"]})

    assert synced.ok is True
    assert "lists/courses.md: Courses (1 chunk(s) catalogued, 2 bullet(s))" in synced.summary
    assert synced.data["reports"][0]["report"]["documents"][0]["bullet_count"] == 2

    found = tools["rag_search"].handler({"query": "liste de course"})
    assert found.ok is True
    assert found.data["chunks"] == []
    assert found.data["documents"][0]["title"] == "Courses"


def test_rag_checklist_add_appends_unchecked_item_and_resyncs_source(tmp_path):
    source_dir = tmp_path / "secondBrain"
    lists_dir = source_dir / "lists"
    lists_dir.mkdir(parents=True)
    courses = lists_dir / "courses.md"
    courses.write_text("# Courses\n\n- [ ] Cafe\n", encoding="utf-8")
    tools = make_rag_tools(tmp_path / "rag")
    added_source = tools["rag_source_add"].handler({"name": "secondBrain", "path": str(source_dir), "scope": "user"})
    tools["rag_source_sync"].handler({"source_id": added_source.data["source"]["id"]})

    result = tools["rag_checklist_add"].handler({
        "path": str(courses),
        "source_id": added_source.data["source"]["id"],
        "item": "bananes",
    })

    assert result.ok is True
    assert "- [ ] bananes" in courses.read_text(encoding="utf-8")
    assert result.data["sync"]["documents"][0]["checklist_open"] == 2


def test_rag_checklist_add_uses_local_list_when_no_path(tmp_path):
    tools = make_rag_tools(tmp_path / "rag")

    result = tools["rag_checklist_add"].handler({"list_name": "courses", "items": ["Cafe", "Cafe", "Tomates"]})

    assert result.ok is True
    path = tmp_path / "rag" / "lists" / "courses.md"
    assert path.read_text(encoding="utf-8").count("- [ ] Cafe") == 1
    assert "- [ ] Tomates" in path.read_text(encoding="utf-8")
