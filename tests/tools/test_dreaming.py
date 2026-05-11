from __future__ import annotations

from pathlib import Path

from marius.dreaming.operations import DreamingResult
from marius.provider_config.contracts import AuthType, ProviderEntry, ProviderKind
from marius.storage.memory_store import MemoryStore
from marius.tools.dreaming import make_dreaming_tools


def _entry() -> ProviderEntry:
    return ProviderEntry(
        id="p1",
        name="test",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        api_key="secret:test",
        model="gpt-test",
    )


def test_dreaming_run_returns_structured_result(tmp_path: Path, monkeypatch):
    memory = MemoryStore(db_path=tmp_path / "memory.db")
    calls = {}

    def fake_run_dreaming(**kwargs):
        calls.update(kwargs)
        return DreamingResult(added=1, updated=2, removed=0, raw_ops=3, summary="ok")

    monkeypatch.setattr("marius.tools.dreaming.run_dreaming", fake_run_dreaming)
    tools = make_dreaming_tools(memory_store=memory, entry=_entry(), project_root=tmp_path, active_skills=["dev"])

    result = tools["dreaming_run"].handler({"archive_sessions": False})

    assert result.ok is True
    assert result.data["added"] == 1
    assert result.data["archive_sessions"] is False
    assert calls["active_skills"] == ["dev"]
    memory.close()


def test_daily_digest_returns_markdown_artifact(tmp_path: Path, monkeypatch):
    memory = MemoryStore(db_path=tmp_path / "memory.db")
    calls = {}

    def fake_run_daily(**kwargs):
        calls.update(kwargs)
        return "# Briefing\n\nSalut\n\n---\n_Tokens daily : entrée 10 · sortie 5 · total 15 · modèle `gpt-mini`_"

    monkeypatch.setattr("marius.tools.dreaming.run_daily", fake_run_daily)
    tools = make_dreaming_tools(memory_store=memory, entry=_entry(), project_root=tmp_path, daily_model="gpt-mini")

    result = tools["daily_digest"].handler({})

    assert result.ok is True
    assert result.data["markdown"].startswith("# Briefing\n\nSalut")
    assert result.data["model"] == "gpt-mini"
    assert result.data["usage_footer"] == "_Tokens daily : entrée 10 · sortie 5 · total 15 · modèle `gpt-mini`_"
    assert result.data["usage_footer"] in result.summary
    assert calls["model"] == "gpt-mini"
    assert result.artifacts
    assert result.artifacts[0].data["format"] == "markdown"
    memory.close()


def test_daily_digest_marks_provider_error(tmp_path: Path, monkeypatch):
    memory = MemoryStore(db_path=tmp_path / "memory.db")

    monkeypatch.setattr(
        "marius.tools.dreaming.run_daily",
        lambda **kwargs: "# Briefing\n\nErreur provider : nope",
    )
    tools = make_dreaming_tools(memory_store=memory, entry=_entry(), project_root=tmp_path)

    result = tools["daily_digest"].handler({})

    assert result.ok is False
    assert result.error == "daily_failed"
    memory.close()
