"""Tests de la collecte du contexte dreaming."""

from __future__ import annotations

from pathlib import Path

import pytest

from marius.dreaming.context import DreamingContext, build_dreaming_context
from marius.storage.memory_store import MemoryStore
from marius.storage.watch_store import WatchStore


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "mem.db")


def test_empty_context(store: MemoryStore, tmp_path: Path) -> None:
    ctx = build_dreaming_context(
        store,
        sessions_dir=tmp_path / "sessions",
        watch_dir=tmp_path / "watch",
    )
    assert ctx.is_empty
    assert ctx.memories == []
    assert ctx.session_summaries == []
    assert ctx.dream_contracts == []


def test_memories_included(store: MemoryStore, tmp_path: Path) -> None:
    store.add("Fait important")
    ctx = build_dreaming_context(store, watch_dir=tmp_path / "watch")
    assert not ctx.is_empty
    assert any("Fait important" in m.content for m in ctx.memories)


def test_session_summaries(store: MemoryStore, tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "2026-05-09-10h00.md").write_text(
        "---\nproject: marius\ncwd: /home/user/marius\n"
        "opened_at: 2026-05-09T10:00:00Z\nclosed_at: 2026-05-09T10:30:00Z\nturns: 7\n---\n"
    )
    ctx = build_dreaming_context(store, sessions_dir=sessions_dir, watch_dir=tmp_path / "watch")
    assert len(ctx.session_summaries) == 1
    assert "marius" in ctx.session_summaries[0]
    assert "7" in ctx.session_summaries[0]


def test_project_docs(store: MemoryStore, tmp_path: Path) -> None:
    (tmp_path / "DECISIONS.md").write_text("# Décisions\n- A")
    (tmp_path / "ROADMAP.md").write_text("# Roadmap\n- B")
    ctx = build_dreaming_context(store, project_root=tmp_path, watch_dir=tmp_path / "watch")
    assert "Décisions" in ctx.decisions_doc
    assert "Roadmap" in ctx.roadmap_doc


def test_skill_contracts(store: MemoryStore, tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: test\n---\nInstructions."
    )
    (skill_dir / "DREAM.md").write_text("Contrat dreaming du skill.")
    (skill_dir / "DAILY.md").write_text("Contrat daily du skill.")

    ctx = build_dreaming_context(
        store,
        active_skills=["test-skill"],
        skills_dir=skills_dir,
        watch_dir=tmp_path / "watch",
    )
    assert len(ctx.dream_contracts) == 1
    assert ctx.dream_contracts[0][0] == "test-skill"
    assert "dreaming" in ctx.dream_contracts[0][1]
    assert len(ctx.daily_contracts) == 1
    assert "daily" in ctx.daily_contracts[0][1]


def test_watch_reports_included(store: MemoryStore, tmp_path: Path) -> None:
    watch_dir = tmp_path / "watch"
    watch_store = WatchStore(watch_dir)
    topic = watch_store.add(title="Marius", query="Marius updates")
    watch_store.save_report(topic, [{"title": "Release", "url": "https://example.com"}])

    ctx = build_dreaming_context(store, watch_dir=watch_dir)

    assert not ctx.is_empty
    assert len(ctx.watch_reports) == 1
    assert ctx.watch_reports[0].title == "Marius"
