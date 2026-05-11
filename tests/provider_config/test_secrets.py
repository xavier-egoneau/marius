from __future__ import annotations

from marius.provider_config.secrets import public_secret_label, resolve_provider_secret
from marius.storage.secret_ref_store import SecretRefStore


def test_resolve_provider_secret_keeps_legacy_raw_value():
    assert resolve_provider_secret("sk-test") == "sk-test"


def test_resolve_provider_secret_reads_env(monkeypatch):
    monkeypatch.setenv("MARIUS_TEST_KEY", "sk-env")
    assert resolve_provider_secret("env:MARIUS_TEST_KEY") == "sk-env"


def test_resolve_provider_secret_reads_named_secret(tmp_path, monkeypatch):
    path = tmp_path / "secret_refs.json"
    monkeypatch.setenv("MARIUS_TEST_KEY", "sk-env")
    SecretRefStore(path=path).save(name="openai", ref="env:MARIUS_TEST_KEY")

    assert resolve_provider_secret("secret:openai", secret_ref_path=path) == "sk-env"


def test_public_secret_label_redacts_legacy_raw_value():
    assert public_secret_label("sk-test") == "<legacy-raw-secret>"
    assert public_secret_label("secret:openai") == "secret:openai"
