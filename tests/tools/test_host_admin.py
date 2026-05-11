from __future__ import annotations

import json

from marius.config.contracts import AgentConfig, MariusConfig
from marius.config.doctor import Check, Section
from marius.config.store import ConfigStore
from marius.provider_config.contracts import AuthType, ProviderEntry, ProviderKind
from marius.provider_config.store import ProviderStore
from marius.storage.log_store import log_event
from marius.storage.secret_ref_store import SecretRefStore
from marius.tools.host_admin import make_host_admin_tools


def _provider(path):
    entry = ProviderEntry(
        id="provider-1",
        name="Provider One",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        api_key="secret",
        model="gpt-test",
    )
    ProviderStore(path=path).save([entry])
    return entry


def test_host_status_reports_configured_agents(tmp_path):
    config_path = tmp_path / "config.json"
    ConfigStore(path=config_path).save(
        MariusConfig(
            permission_mode="limited",
            main_agent="main",
            agents={
                "main": AgentConfig(
                    name="main",
                    provider_id="provider-1",
                    model="gpt-test",
                    tools=["read_file", "host_status"],
                    skills=["assistant"],
                )
            },
        )
    )
    tools = make_host_admin_tools(
        config_path=config_path,
        status_runner=lambda agent: agent == "main",
    )

    result = tools["host_status"].handler({})

    assert result.ok is True
    assert "main" in result.summary
    assert result.data["main_agent"] == "main"
    assert result.data["agents"][0]["gateway_running"] is True
    assert result.data["agents"][0]["tool_count"] == 2


def test_host_agent_list_omits_tools_by_default(tmp_path):
    config_path = tmp_path / "config.json"
    ConfigStore(path=config_path).save(
        MariusConfig(
            permission_mode="limited",
            main_agent="main",
            agents={
                "main": AgentConfig(
                    name="main",
                    provider_id="provider-1",
                    model="gpt-test",
                    tools=["read_file"],
                    skills=["assistant"],
                )
            },
        )
    )
    tools = make_host_admin_tools(config_path=config_path)

    result = tools["host_agent_list"].handler({})

    assert result.ok is True
    assert result.data["agents"][0]["name"] == "main"
    assert "tools" not in result.data["agents"][0]


def test_host_agent_save_creates_agent_from_provider(tmp_path):
    config_path = tmp_path / "config.json"
    provider_path = tmp_path / "providers.json"
    _provider(provider_path)
    ConfigStore(path=config_path).save(
        MariusConfig(permission_mode="limited", main_agent="main", agents={})
    )
    tools = make_host_admin_tools(config_path=config_path, provider_path=provider_path)

    result = tools["host_agent_save"].handler(
        {
            "name": "worker",
            "provider_id": "provider-1",
            "add_tools": ["host_status"],
            "skills": ["assistant"],
            "set_main": True,
        }
    )

    loaded = ConfigStore(path=config_path).load()
    assert result.ok is True
    assert loaded is not None
    assert loaded.main_agent == "worker"
    assert loaded.agents["worker"].model == "gpt-test"
    assert "host_status" in loaded.agents["worker"].tools


def test_host_agent_save_rejects_unknown_tool(tmp_path):
    config_path = tmp_path / "config.json"
    provider_path = tmp_path / "providers.json"
    _provider(provider_path)
    ConfigStore(path=config_path).save(
        MariusConfig(permission_mode="limited", main_agent="main", agents={})
    )
    tools = make_host_admin_tools(config_path=config_path, provider_path=provider_path)

    result = tools["host_agent_save"].handler(
        {"name": "worker", "provider_id": "provider-1", "tools": ["nope"]}
    )

    assert result.ok is False
    assert result.error == "invalid_tools"


def test_host_agent_delete_requires_confirmation_and_refuses_main_agent(tmp_path):
    config_path = tmp_path / "config.json"
    ConfigStore(path=config_path).save(
        MariusConfig(
            permission_mode="limited",
            main_agent="main",
            agents={
                "main": AgentConfig(name="main", provider_id="provider-1", model="gpt-test"),
                "worker": AgentConfig(name="worker", provider_id="provider-1", model="gpt-test"),
            },
        )
    )
    tools = make_host_admin_tools(config_path=config_path)

    without_confirm = tools["host_agent_delete"].handler({"name": "worker"})
    main_deleted = tools["host_agent_delete"].handler({"name": "main", "confirm": True})
    worker_deleted = tools["host_agent_delete"].handler({"name": "worker", "confirm": True})

    loaded = ConfigStore(path=config_path).load()
    assert without_confirm.error == "confirmation_required"
    assert main_deleted.error == "main_agent_delete_forbidden"
    assert worker_deleted.ok is True
    assert loaded is not None
    assert loaded.main_agent == "main"
    assert "worker" not in loaded.agents


def test_host_telegram_configure_uses_env_ref_without_exposing_secret(tmp_path, monkeypatch):
    telegram_path = tmp_path / "telegram.json"
    monkeypatch.setenv("MARIUS_TEST_TELEGRAM_TOKEN", "123456:secret")
    tools = make_host_admin_tools(telegram_path=telegram_path)

    result = tools["host_telegram_configure"].handler(
        {
            "token_ref": "env:MARIUS_TEST_TELEGRAM_TOKEN",
            "agent": "main",
            "allowed_users": [42],
            "enabled": False,
        }
    )

    raw = json.loads(telegram_path.read_text(encoding="utf-8"))
    assert result.ok is True
    assert "123456:secret" not in result.summary
    assert result.data["token_source"] == "env:MARIUS_TEST_TELEGRAM_TOKEN"
    assert raw["token"] == "123456:secret"
    assert raw["allowed_users"] == [42]
    assert raw["enabled"] is False


def test_host_telegram_configure_refuses_raw_token(tmp_path):
    tools = make_host_admin_tools(telegram_path=tmp_path / "telegram.json")

    result = tools["host_telegram_configure"].handler({"token": "123456:secret"})

    assert result.ok is False
    assert result.error == "raw_secret_refused"


def test_host_telegram_configure_uses_named_secret_ref(tmp_path, monkeypatch):
    telegram_path = tmp_path / "telegram.json"
    secret_ref_path = tmp_path / "secret_refs.json"
    monkeypatch.setenv("MARIUS_TEST_TELEGRAM_TOKEN", "123456:secret")
    SecretRefStore(path=secret_ref_path).save(name="telegram", ref="env:MARIUS_TEST_TELEGRAM_TOKEN")
    tools = make_host_admin_tools(
        telegram_path=telegram_path,
        secret_ref_path=secret_ref_path,
    )

    result = tools["host_telegram_configure"].handler(
        {"token_ref": "secret:telegram", "agent": "main"}
    )

    raw = json.loads(telegram_path.read_text(encoding="utf-8"))
    assert result.ok is True
    assert result.data["token_source"] == "secret:telegram"
    assert raw["token"] == "123456:secret"


def test_host_status_reports_missing_agent(tmp_path):
    config_path = tmp_path / "config.json"
    ConfigStore(path=config_path).save(
        MariusConfig(
            permission_mode="limited",
            main_agent="main",
            agents={
                "main": AgentConfig(name="main", provider_id="provider-1", model="gpt-test")
            },
        )
    )
    tools = make_host_admin_tools(config_path=config_path, status_runner=lambda _: False)

    result = tools["host_status"].handler({"agent": "worker"})

    assert result.ok is False
    assert result.error == "agent_not_found"
    assert result.data["agents"][0] == {"name": "worker", "configured": False}


def test_host_doctor_returns_structured_report():
    tools = make_host_admin_tools(
        doctor_runner=lambda agent: [
            Section("Config", [Check("config.json", True)]),
            Section("Gateway", [Check("gateway", False, "start it")]),
        ]
    )

    result = tools["host_doctor"].handler({"agent": "main"})

    assert result.ok is False
    assert result.error == "doctor_failed"
    assert result.data["agent"] == "main"
    assert result.data["errors"] == 1
    assert result.data["sections"][1]["checks"][0]["hint"] == "start it"


def test_host_logs_filters_recent_entries(tmp_path):
    log_path = tmp_path / "marius.jsonl"
    log_event("turn_start", {"agent": "main", "message": "hello"}, log_path=log_path)
    log_event("tool_result", {"agent": "main", "tool": "read_file"}, log_path=log_path)
    log_event("tool_result", {"agent": "other", "tool": "run_bash"}, log_path=log_path)
    tools = make_host_admin_tools(log_path=log_path)

    result = tools["host_logs"].handler({"event": "tool_result", "agent": "main", "limit": 10})

    assert result.ok is True
    assert result.data["event"] == "tool_result"
    assert len(result.data["entries"]) == 1
    assert result.data["entries"][0]["data"]["tool"] == "read_file"


def test_host_logs_bounds_limit(tmp_path):
    log_path = tmp_path / "marius.jsonl"
    log_event("event", {"agent": "main"}, log_path=log_path)
    tools = make_host_admin_tools(log_path=log_path)

    result = tools["host_logs"].handler({"limit": 999})

    assert result.ok is True
    assert result.data["limit"] == 200


def test_host_gateway_restart_requires_confirmation(tmp_path):
    config_path = tmp_path / "config.json"
    ConfigStore(path=config_path).save(
        MariusConfig(
            permission_mode="limited",
            main_agent="main",
            agents={"main": AgentConfig(name="main", provider_id="provider-1", model="gpt-test")},
        )
    )
    tools = make_host_admin_tools(config_path=config_path)

    result = tools["host_gateway_restart"].handler({"agent": "main"})

    assert result.ok is False
    assert result.error == "confirmation_required"


def test_host_gateway_restart_schedules_known_agent(tmp_path):
    config_path = tmp_path / "config.json"
    ConfigStore(path=config_path).save(
        MariusConfig(
            permission_mode="limited",
            main_agent="main",
            agents={"main": AgentConfig(name="main", provider_id="provider-1", model="gpt-test")},
        )
    )
    calls = []
    tools = make_host_admin_tools(
        config_path=config_path,
        restart_runner=lambda agent, delay, mode: (
            calls.append((agent, delay, mode)) is None,
            "",
            {"scheduled": True},
        ),
    )

    result = tools["host_gateway_restart"].handler(
        {"agent": "main", "confirm": True, "delay_seconds": 0.1, "mode": "direct"}
    )

    assert result.ok is True
    assert calls == [("main", 0.5, "direct")]
    assert result.data["scheduled"] is True
