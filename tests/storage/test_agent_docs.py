from __future__ import annotations

from marius.storage.agent_docs import agent_doc_path, seed_agent_docs_from_global


def test_seed_agent_docs_from_global_copies_existing_docs(tmp_path) -> None:
    home = tmp_path / ".marius"
    home.mkdir()
    (home / "SOUL.md").write_text("ame", encoding="utf-8")
    (home / "IDENTITY.md").write_text("identite", encoding="utf-8")

    copied = seed_agent_docs_from_global("worker", marius_home=home)

    assert sorted(path.name for path in copied) == ["IDENTITY.md", "SOUL.md"]
    assert (home / "workspace" / "worker" / "SOUL.md").read_text(encoding="utf-8") == "ame"
    assert (home / "workspace" / "worker" / "IDENTITY.md").read_text(encoding="utf-8") == "identite"
    assert not (home / "workspace" / "worker" / "USER.md").exists()


def test_seed_agent_docs_does_not_overwrite_existing_override(tmp_path) -> None:
    home = tmp_path / ".marius"
    home.mkdir()
    (home / "SOUL.md").write_text("global", encoding="utf-8")
    target = home / "workspace" / "worker" / "SOUL.md"
    target.parent.mkdir(parents=True)
    target.write_text("local", encoding="utf-8")

    copied = seed_agent_docs_from_global("worker", marius_home=home)

    assert copied == []
    assert target.read_text(encoding="utf-8") == "local"


def test_agent_doc_path_rejects_unsafe_agent_name(tmp_path) -> None:
    assert agent_doc_path("../main", "soul", marius_home=tmp_path) is None
