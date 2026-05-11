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
                daily_model="gemma4-mini",
                tools=["read_file", "vision"],
                skills=["assistant"],
            )
        },
    )

    store.save(config)
    loaded = store.load()

    assert loaded is not None
    assert loaded.permission_mode == "limited"
    assert loaded.agents["main"].daily_model == "gemma4-mini"
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


def test_config_store_migrates_pre_marius_web_default_tools(tmp_path):
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
                            "vision",
                            "skill_view",
                            "spawn_agent",
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


def test_config_store_migrates_pre_project_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "host_agent_list",
                            "host_agent_save",
                            "host_agent_delete",
                            "host_telegram_configure",
                            "host_status",
                            "host_doctor",
                            "host_logs",
                            "self_update_propose",
                            "self_update_report_bug",
                            "self_update_list",
                            "self_update_show",
                            "watch_add",
                            "watch_list",
                            "watch_remove",
                            "watch_run",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_security_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "host_agent_list",
                            "host_agent_save",
                            "host_agent_delete",
                            "host_telegram_configure",
                            "host_status",
                            "host_doctor",
                            "host_logs",
                            "project_list",
                            "project_set_active",
                            "self_update_propose",
                            "self_update_report_bug",
                            "self_update_list",
                            "self_update_show",
                            "watch_add",
                            "watch_list",
                            "watch_remove",
                            "watch_run",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_rag_default_tools(tmp_path):
    path = tmp_path / "config.json"
    pre_rag_tools = [tool for tool in ALL_TOOLS if not tool.startswith("rag_")]
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
                        "tools": pre_rag_tools,
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


def test_config_store_migrates_pre_provider_admin_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "host_agent_list",
                            "host_agent_save",
                            "host_agent_delete",
                            "host_telegram_configure",
                            "host_status",
                            "host_doctor",
                            "host_logs",
                            "project_list",
                            "project_set_active",
                            "approval_list",
                            "approval_decide",
                            "approval_forget",
                            "secret_ref_list",
                            "secret_ref_save",
                            "secret_ref_delete",
                            "self_update_propose",
                            "self_update_report_bug",
                            "self_update_list",
                            "self_update_show",
                            "watch_add",
                            "watch_list",
                            "watch_remove",
                            "watch_run",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_dreaming_tools_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "host_agent_list",
                            "host_agent_save",
                            "host_agent_delete",
                            "host_telegram_configure",
                            "host_status",
                            "host_doctor",
                            "host_logs",
                            "project_list",
                            "project_set_active",
                            "approval_list",
                            "approval_decide",
                            "approval_forget",
                            "secret_ref_list",
                            "secret_ref_save",
                            "secret_ref_delete",
                            "provider_list",
                            "provider_save",
                            "provider_delete",
                            "provider_models",
                            "self_update_propose",
                            "self_update_report_bug",
                            "self_update_list",
                            "self_update_show",
                            "watch_add",
                            "watch_list",
                            "watch_remove",
                            "watch_run",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_filesystem_completion_default_tools(tmp_path):
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
                            "vision",
                            "skill_view",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_explore_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_skill_authoring_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_host_admin_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_host_actions_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "host_status",
                            "host_doctor",
                            "host_logs",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_self_update_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "host_agent_list",
                            "host_agent_save",
                            "host_agent_delete",
                            "host_telegram_configure",
                            "host_status",
                            "host_doctor",
                            "host_logs",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_watch_default_tools(tmp_path):
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
                            "make_dir",
                            "move_path",
                            "explore_tree",
                            "explore_grep",
                            "explore_summary",
                            "run_bash",
                            "web_fetch",
                            "web_search",
                            "vision",
                            "skill_view",
                            "skill_create",
                            "skill_list",
                            "skill_reload",
                            "host_agent_list",
                            "host_agent_save",
                            "host_agent_delete",
                            "host_telegram_configure",
                            "host_status",
                            "host_doctor",
                            "host_logs",
                            "self_update_propose",
                            "self_update_report_bug",
                            "self_update_list",
                            "self_update_show",
                            "open_marius_web",
                            "spawn_agent",
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


def test_config_store_migrates_pre_gateway_restart_secret_file_default_tools(tmp_path):
    path = tmp_path / "config.json"
    previous_default = [
        tool for tool in ALL_TOOLS
        if tool not in (
            "host_gateway_restart",
            "secret_ref_prepare_file",
            "self_update_apply",
            "self_update_rollback",
        )
    ]
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
                        "tools": previous_default,
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


def test_config_store_migrates_pre_self_update_apply_default_tools(tmp_path):
    path = tmp_path / "config.json"
    previous_default = [
        tool for tool in ALL_TOOLS
        if tool not in ("self_update_apply", "self_update_rollback")
    ]
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
                        "tools": previous_default,
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
