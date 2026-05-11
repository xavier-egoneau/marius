from __future__ import annotations

from marius.config.contracts import AgentConfig, MariusConfig
from marius.config.store import ConfigStore
from marius.provider_config.contracts import AuthType, ProviderEntry, ProviderKind
from marius.provider_config.store import ProviderStore
from marius.tools.provider_admin import make_provider_admin_tools


def test_provider_save_creates_provider_with_secret_ref(tmp_path):
    provider_path = tmp_path / "providers.json"
    tools = make_provider_admin_tools(provider_path=provider_path)

    result = tools["provider_save"].handler(
        {
            "name": "openai",
            "provider": "openai",
            "auth_type": "api",
            "api_key_ref": "secret:openai",
            "model": "gpt-4o",
        }
    )

    providers = ProviderStore(path=provider_path).load()
    assert result.ok is True
    assert providers[0].api_key == "secret:openai"
    assert result.data["provider"]["api_key_ref"] == "secret:openai"


def test_provider_save_refuses_raw_api_key(tmp_path):
    tools = make_provider_admin_tools(provider_path=tmp_path / "providers.json")

    result = tools["provider_save"].handler(
        {"name": "openai", "provider": "openai", "api_key": "sk-test"}
    )

    assert result.ok is False
    assert result.error == "raw_secret_refused"


def test_provider_save_updates_existing_by_name(tmp_path):
    provider_path = tmp_path / "providers.json"
    store = ProviderStore(path=provider_path)
    store.add(
        ProviderEntry(
            id="p1",
            name="openai",
            provider=ProviderKind.OPENAI,
            auth_type=AuthType.API,
            base_url="https://api.openai.com/v1",
            api_key="secret:openai",
            model="gpt-4o",
        )
    )
    tools = make_provider_admin_tools(provider_path=provider_path)

    result = tools["provider_save"].handler({"name": "openai", "model": "gpt-4.1"})

    assert result.ok is True
    assert result.data["created"] is False
    assert ProviderStore(path=provider_path).load()[0].model == "gpt-4.1"


def test_provider_list_redacts_legacy_raw_key(tmp_path):
    provider_path = tmp_path / "providers.json"
    ProviderStore(path=provider_path).add(
        ProviderEntry(
            id="p1",
            name="legacy",
            provider=ProviderKind.OPENAI,
            auth_type=AuthType.API,
            api_key="sk-test",
            model="gpt-4o",
        )
    )
    tools = make_provider_admin_tools(provider_path=provider_path)

    result = tools["provider_list"].handler({})

    assert result.ok is True
    assert result.data["providers"][0]["api_key_ref"] == "<legacy-raw-secret>"
    assert "sk-test" not in result.summary


def test_provider_delete_refuses_provider_in_use_without_force(tmp_path):
    provider_path = tmp_path / "providers.json"
    config_path = tmp_path / "config.json"
    ProviderStore(path=provider_path).add(
        ProviderEntry(id="p1", name="openai", provider=ProviderKind.OPENAI, auth_type=AuthType.API)
    )
    ConfigStore(path=config_path).save(
        MariusConfig(
            permission_mode="limited",
            main_agent="main",
            agents={"main": AgentConfig(name="main", provider_id="p1", model="gpt-4o")},
        )
    )
    tools = make_provider_admin_tools(provider_path=provider_path, config_path=config_path)

    result = tools["provider_delete"].handler({"id": "p1", "confirm": True})

    assert result.ok is False
    assert result.error == "provider_in_use"


def test_provider_delete_with_force(tmp_path):
    provider_path = tmp_path / "providers.json"
    ProviderStore(path=provider_path).add(
        ProviderEntry(id="p1", name="openai", provider=ProviderKind.OPENAI, auth_type=AuthType.API)
    )
    tools = make_provider_admin_tools(provider_path=provider_path, config_path=tmp_path / "config.json")

    result = tools["provider_delete"].handler({"id": "p1", "confirm": True, "force": True})

    assert result.ok is True
    assert ProviderStore(path=provider_path).load() == []


def test_provider_models_uses_injected_fetcher(tmp_path):
    provider_path = tmp_path / "providers.json"
    ProviderStore(path=provider_path).add(
        ProviderEntry(id="p1", name="ollama", provider=ProviderKind.OLLAMA, auth_type=AuthType.API)
    )
    tools = make_provider_admin_tools(
        provider_path=provider_path,
        model_fetcher=lambda entry: ["llama3", "mistral"],
    )

    result = tools["provider_models"].handler({"name": "ollama"})

    assert result.ok is True
    assert result.data["models"] == ["llama3", "mistral"]
