from __future__ import annotations

from marius.channels.dashboard import server as dashboard_server
from marius.config.contracts import MariusConfig
from marius.config.store import ConfigStore
from marius.config import store as config_store_module


def test_agent_doc_get_is_empty_when_override_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(dashboard_server, "_WORKSPACE_ROOT", tmp_path / "workspace")
    global_soul = tmp_path / "SOUL.md"
    global_soul.write_text("global", encoding="utf-8")

    result = dashboard_server._api_agent_doc_get("main", "soul")

    assert result is not None
    assert result["content"] == ""
    assert result["exists"] is False
    assert result["path"].endswith("/workspace/main/SOUL.md")


def test_agent_doc_put_creates_agent_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(dashboard_server, "_WORKSPACE_ROOT", tmp_path / "workspace")

    ok, msg = dashboard_server._api_agent_doc_put("codeur-low", "identity", {"content": "identité codeur"})

    path = tmp_path / "workspace" / "codeur-low" / "IDENTITY.md"
    assert ok is True
    assert msg == "updated"
    assert path.read_text(encoding="utf-8") == "identité codeur"


def test_agent_doc_rejects_path_traversal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(dashboard_server, "_WORKSPACE_ROOT", tmp_path / "workspace")

    assert dashboard_server._api_agent_doc_get("../main", "soul") is None
    ok, msg = dashboard_server._api_agent_doc_put("../main", "soul", {"content": "x"})
    assert ok is False
    assert msg == "invalid agent document"


def test_dashboard_create_agent_seeds_docs_from_global(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ConfigStore(path=config_path).save(
        MariusConfig(permission_mode="limited", main_agent="main", agents={})
    )
    (tmp_path / "SOUL.md").write_text("ame globale", encoding="utf-8")
    (tmp_path / "USER.md").write_text("profil global", encoding="utf-8")
    monkeypatch.setattr(config_store_module, "ConfigStore", lambda: ConfigStore(path=config_path))
    monkeypatch.setattr(dashboard_server, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(dashboard_server, "_WORKSPACE_ROOT", tmp_path / "workspace")

    ok, msg = dashboard_server._create_agent({
        "name": "worker",
        "provider_id": "provider-1",
        "model": "gpt-test",
        "skills": ["assistant"],
        "tools": [],
    })

    assert ok is True
    assert msg == "agent 'worker' created"
    assert (tmp_path / "workspace" / "worker" / "SOUL.md").read_text(encoding="utf-8") == "ame globale"
    assert (tmp_path / "workspace" / "worker" / "USER.md").read_text(encoding="utf-8") == "profil global"
