from __future__ import annotations

from marius.storage.rag_store import RagStore


def test_rag_store_add_sync_search_and_get(tmp_path):
    source_dir = tmp_path / "knowledge"
    source_dir.mkdir()
    (source_dir / "rules.md").write_text(
        """---
scope: org
tags: [security]
---

# Security

[always] Never expose secrets.

## Token refs

[important] Use file or env references for tokens.
""",
        encoding="utf-8",
    )
    store = RagStore(tmp_path / "rag.db")

    source = store.add_source(
        name="Company Rules",
        uri=str(source_dir),
        scope="org",
        audience="devs",
        tags="security",
    )
    report = store.sync_source(source.id)
    results = store.search("tokens")

    assert report.documents_indexed == 1
    assert report.chunks_indexed == 2
    assert report.always_chunks == 1
    assert report.important_chunks == 1
    assert report.documents[0].title == "Security"
    assert report.documents[0].chunk_count == 2
    assert len(results) == 1
    assert "important" in results[0].tags
    assert store.get_chunk(results[0].id) is not None
    store.close()


def test_rag_store_important_returns_tagged_chunks(tmp_path):
    source_file = tmp_path / "daily.md"
    source_file.write_text("# Daily\n\n[daily] Check open loops.\n", encoding="utf-8")
    store = RagStore(tmp_path / "rag.db")
    source = store.add_source(name="Daily", uri=str(source_file), scope="user")

    store.sync_source(source.id)
    chunks = store.important(tag="daily")

    assert len(chunks) == 1
    assert chunks[0].title == "Daily"
    store.close()


def test_rag_store_search_finds_plural_file_title_from_natural_query(tmp_path):
    source_dir = tmp_path / "secondBrain"
    lists_dir = source_dir / "lists"
    lists_dir.mkdir(parents=True)
    (lists_dir / "courses.md").write_text(
        "# Courses\n\n- Cafe\n- gateaux\n- saucisson\n- bananes\n",
        encoding="utf-8",
    )
    store = RagStore(tmp_path / "rag.db")
    source = store.add_source(name="secondBrain", uri=str(source_dir), scope="user")

    report = store.sync_source(source.id)
    chunks = store.search("liste de course")
    documents = store.search_documents("liste de course")

    assert report.documents[0].bullet_count == 4
    assert report.chunks_indexed == 0
    assert chunks == []
    assert len(documents) == 1
    assert documents[0].title == "Courses"
    assert documents[0].bullet_count == 4
    store.close()
