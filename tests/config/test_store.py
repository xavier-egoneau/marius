from __future__ import annotations

import json

from marius.config.contracts import ALL_TOOLS, AgentConfig, MariusConfig
from marius.config.store import ConfigStore


def test_config_store_roundtrip(tmp_path):
    store = ConfigStore(path=tmp_path / "config.json")
    config = MariusConfig(
        permission_mode="limited",
        main_agent="main",
        agents={
            "main": AgentConfig(
                name="main",
                provider_id="provider-1",
                model="gemma4",
                tools=["read_file", "vision"],
                skills=["assistant"],
            )
        },
    )

    store.save(config)
    loaded = store.load()

    assert loaded is not None
    assert loaded.permission_mode == "limited"
    assert loaded.agents["main"].tools == ["read_file", "vision"]
    assert loaded.agents["main"].skills == ["assistant"]


def test_config_store_migrates_pre_vision_default_tools(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "permission_mode": "limited",
                "main_agent": "main",
                "agents": {
                    "main": {
                        "name": "main",
                        "provider_id": "provider-1",
                        "model": "gemma4",
                        "tools": [
                            "read_file",
                            "list_dir",
                            "write_file",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "skill_view",
                        ],
                        "skills": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = ConfigStore(path=path).load()

    assert loaded is not None
    assert loaded.agents["main"].tools == ALL_TOOLS


def test_config_store_keeps_custom_tools_without_forcing_vision(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "permission_mode": "safe",
                "main_agent": "main",
                "agents": {
                    "main": {
                        "name": "main",
                        "provider_id": "provider-1",
                        "model": "gemma4",
                        "tools": ["read_file"],
                        "skills": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = ConfigStore(path=path).load()

    assert loaded is not None
    assert loaded.agents["main"].tools == ["read_file"]
