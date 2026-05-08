from __future__ import annotations

from marius.provider_config.contracts import AuthType, ProviderEntry, ProviderKind
from marius.provider_config.store import ProviderStore


def _entry(name: str = "test", **kwargs) -> ProviderEntry:
    defaults = dict(
        id=ProviderEntry.generate_id(),
        name=name,
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o",
    )
    defaults.update(kwargs)
    return ProviderEntry(**defaults)


def test_load_returns_empty_when_file_absent(tmp_path):
    store = ProviderStore(path=tmp_path / "providers.json")
    assert store.load() == []


def test_add_and_load(tmp_path):
    store = ProviderStore(path=tmp_path / "providers.json")
    store.add(_entry("openai-1"))
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].name == "openai-1"
    assert loaded[0].model == "gpt-4o"


def test_add_multiple(tmp_path):
    store = ProviderStore(path=tmp_path / "providers.json")
    store.add(_entry("openai-1"))
    store.add(_entry("ollama-1", provider=ProviderKind.OLLAMA, api_key=""))
    entries = store.load()
    assert len(entries) == 2
    assert {e.name for e in entries} == {"openai-1", "ollama-1"}


def test_update_existing(tmp_path):
    store = ProviderStore(path=tmp_path / "providers.json")
    e = _entry("openai-1")
    store.add(e)
    updated = ProviderEntry(
        id=e.id,
        name="openai-updated",
        provider=e.provider,
        auth_type=e.auth_type,
        model="gpt-4-turbo",
    )
    assert store.update(updated) is True
    loaded = store.load()
    assert loaded[0].name == "openai-updated"
    assert loaded[0].model == "gpt-4-turbo"


def test_update_unknown_id_returns_false(tmp_path):
    store = ProviderStore(path=tmp_path / "providers.json")
    store.add(_entry("openai-1"))
    unknown = ProviderEntry(
        id="unknown-id",
        name="ghost",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
    )
    assert store.update(unknown) is False
    assert len(store.load()) == 1


def test_roundtrip_all_fields(tmp_path):
    store = ProviderStore(path=tmp_path / "providers.json")
    e = ProviderEntry(
        id="abc123",
        name="my-provider",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        base_url="https://custom.example.com",
        api_key="sk-xyz",
        model="gpt-4o",
        added_at="2026-05-08T10:00:00+00:00",
        metadata={"custom": True},
    )
    store.add(e)
    loaded = store.load()[0]
    assert loaded.id == "abc123"
    assert loaded.base_url == "https://custom.example.com"
    assert loaded.api_key == "sk-xyz"
    assert loaded.metadata == {"custom": True}
    assert loaded.added_at == "2026-05-08T10:00:00+00:00"


def test_store_creates_parent_directory(tmp_path):
    nested = tmp_path / "deep" / "dir" / "providers.json"
    store = ProviderStore(path=nested)
    store.add(_entry("test"))
    assert nested.exists()
