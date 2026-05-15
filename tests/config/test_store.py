from __future__ import annotations

import json

from marius.config.contracts import ALL_TOOLS, DEFAULT_AGENT_TOOLS, SKILL_GATED_TOOLS, AgentConfig, MariusConfig
from marius.config.store import ConfigStore

DEFAULT_ADMIN_TOOLS = [tool for tool in ALL_TOOLS if tool not in SKILL_GATED_TOOLS]


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


def test_config_store_serializes_disabled_tools_instead_of_enabled_tools(tmp_path):
    store = ConfigStore(path=tmp_path / "config.json")
    config = MariusConfig(
        permission_mode="limited",
        main_agent="main",
        agents={
            "main": AgentConfig(
                name="main",
                provider_id="provider-1",
                model="gemma4",
                role="admin",
            )
        },
    )

    store.save(config)
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    loaded = store.load()

    assert "tools" not in raw["agents"]["main"]
    assert "tools_mode" not in raw["agents"]["main"]
    assert raw["agents"]["main"]["disabled_tools"] == [tool for tool in ALL_TOOLS if tool in SKILL_GATED_TOOLS]
    assert loaded is not None
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


def test_config_store_migrates_legacy_near_default_toolset_to_dynamic_default(tmp_path):
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
                        "role": "admin",
                        "tools": ALL_TOOLS[:-1],
                        "skills": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = ConfigStore(path=path).load()

    assert loaded is not None
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


def test_config_store_persists_custom_toolset_as_disabled_tools(tmp_path):
    store = ConfigStore(path=tmp_path / "config.json")
    custom_tools = ALL_TOOLS[:-1]
    config = MariusConfig(
        permission_mode="limited",
        main_agent="main",
        agents={
            "main": AgentConfig(
                name="main",
                provider_id="provider-1",
                model="gemma4",
                role="admin",
                tools=custom_tools,
            )
        },
    )

    store.save(config)
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    loaded = store.load()

    assert "tools_mode" not in raw["agents"]["main"]
    assert "tools" not in raw["agents"]["main"]
    assert raw["agents"]["main"]["disabled_tools"] == [
        tool for tool in ALL_TOOLS if tool in SKILL_GATED_TOOLS or tool == ALL_TOOLS[-1]
    ]
    assert loaded is not None
    assert loaded.agents["main"].tools == [tool for tool in custom_tools if tool not in SKILL_GATED_TOOLS]


def test_agent_config_defaults_follow_role():
    admin = AgentConfig(name="main", provider_id="provider-1", model="gemma4", role="admin")
    named = AgentConfig(name="worker", provider_id="provider-1", model="gemma4", role="agent")

    assert admin.tools == DEFAULT_ADMIN_TOOLS
    assert named.tools == DEFAULT_AGENT_TOOLS
    assert "spawn_agent" not in named.tools
    assert "host_agent_save" not in named.tools
    assert "browser_open" not in named.tools


def test_named_agent_can_keep_spawn_agent_when_explicitly_enabled():
    named = AgentConfig(
        name="worker",
        provider_id="provider-1",
        model="gemma4",
        role="agent",
        tools=["read_file", "spawn_agent", "host_agent_save"],
    )

    assert named.tools == ["read_file", "spawn_agent"]


def test_active_kanban_skill_grants_task_tools():
    agent = AgentConfig(
        name="main",
        provider_id="provider-1",
        model="gemma4",
        role="admin",
        tools=["read_file"],
        skills=["kanban"],
    )

    assert agent.tools == ["read_file", "task_create", "task_list", "task_update"]


def test_active_browser_skill_grants_browser_tools():
    agent = AgentConfig(
        name="main",
        provider_id="provider-1",
        model="gemma4",
        role="agent",
        tools=["read_file"],
        skills=["browser"],
    )

    assert "browser_open" in agent.tools
    assert "browser_close" in agent.tools


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS
    assert loaded.agents["main"].role == "admin"


def test_config_store_migrates_named_agent_to_agent_toolset(tmp_path):
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
                        "tools": ALL_TOOLS,
                        "skills": [],
                    },
                    "worker": {
                        "name": "worker",
                        "provider_id": "provider-1",
                        "model": "gemma4",
                        "tools": ALL_TOOLS,
                        "skills": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = ConfigStore(path=path).load()

    assert loaded is not None
    assert loaded.agents["main"].role == "admin"
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS
    assert loaded.agents["worker"].role == "agent"
    assert loaded.agents["worker"].tools == DEFAULT_AGENT_TOOLS


def test_config_store_preserves_explicit_spawn_agent_for_named_agent(tmp_path):
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
                        "tools": ALL_TOOLS,
                        "skills": [],
                    },
                    "worker": {
                        "name": "worker",
                        "provider_id": "provider-1",
                        "model": "gemma4",
                        "role": "agent",
                        "tools": ["read_file", "spawn_agent", "host_agent_save"],
                        "skills": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = ConfigStore(path=path).load()

    assert loaded is not None
    assert loaded.agents["worker"].tools == ["read_file", "spawn_agent"]


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS


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
    assert loaded.agents["main"].tools == DEFAULT_ADMIN_TOOLS
