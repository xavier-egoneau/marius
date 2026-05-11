from __future__ import annotations

import pytest

from marius.storage.secret_ref_store import SecretRefStore


def test_secret_ref_store_saves_env_reference(tmp_path):
    store = SecretRefStore(path=tmp_path / "secret_refs.json")

    secret = store.save(name="telegram", ref="env:BOT_TOKEN", description="bot")

    assert secret.name == "telegram"
    assert secret.kind == "env"
    assert store.get("telegram") is not None


def test_secret_ref_store_rejects_invalid_ref(tmp_path):
    store = SecretRefStore(path=tmp_path / "secret_refs.json")

    with pytest.raises(ValueError, match="invalid_secret_ref"):
        store.save(name="telegram", ref="raw-secret")


def test_secret_ref_store_deletes_reference(tmp_path):
    store = SecretRefStore(path=tmp_path / "secret_refs.json")
    store.save(name="telegram", ref="env:BOT_TOKEN")

    assert store.delete("telegram") is True
    assert store.get("telegram") is None
