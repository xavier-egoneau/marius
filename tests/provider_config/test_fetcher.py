from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from marius.provider_config.contracts import AuthType, ProviderEntry, ProviderKind
from marius.provider_config.fetcher import (
    ModelFetchError,
    _CHATGPT_FALLBACK_MODELS,
    fetch_chatgpt_oauth_models,
    fetch_models,
)


def _openai_entry() -> ProviderEntry:
    return ProviderEntry(
        id="abc",
        name="openai-1",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.API,
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o",
    )


def _ollama_entry() -> ProviderEntry:
    return ProviderEntry(
        id="xyz",
        name="ollama-1",
        provider=ProviderKind.OLLAMA,
        auth_type=AuthType.API,
        base_url="http://localhost:11434",
        model="llama3",
    )


def _mock_urlopen(body: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_parse_openai_response():
    body = {
        "data": [
            {"id": "gpt-4o"},
            {"id": "gpt-4-turbo"},
            {"id": "text-embedding-3-large"},  # filtered out
        ]
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        models = fetch_models(_openai_entry())
    assert "gpt-4o" in models
    assert "gpt-4-turbo" in models
    assert "text-embedding-3-large" not in models


def test_parse_ollama_response():
    body = {"models": [{"name": "llama3:latest"}, {"name": "mistral:7b"}]}
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        models = fetch_models(_ollama_entry())
    assert models == ["llama3:latest", "mistral:7b"]


def test_empty_response_returns_empty_list():
    with patch("urllib.request.urlopen", return_value=_mock_urlopen({"data": []})):
        models = fetch_models(_openai_entry())
    assert models == []


def test_unknown_provider_raises():
    entry = ProviderEntry(
        id="unk",
        name="unknown",
        provider="unknown_provider",
        auth_type=AuthType.API,
    )
    with pytest.raises(ModelFetchError, match="non référencé"):
        fetch_models(entry)


def test_http_error_raises_model_fetch_error():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(None, 401, "Unauthorized", {}, None),
    ):
        with pytest.raises(ModelFetchError, match="HTTP 401"):
            fetch_models(_openai_entry())


def test_url_error_raises_model_fetch_error():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        with pytest.raises(ModelFetchError):
            fetch_models(_openai_entry())


# ── fetch_chatgpt_oauth_models ────────────────────────────────────────────────


def test_chatgpt_oauth_models_reads_codex_cache(tmp_path):
    cache = tmp_path / "models_cache.json"
    cache.write_text(json.dumps({
        "models": [
            {"slug": "gpt-5", "visibility": "list", "priority": 1},
            {"slug": "gpt-4o", "visibility": "default", "priority": 2},
            {"slug": "internal-only", "visibility": "hidden", "priority": 3},
        ]
    }), encoding="utf-8")
    models = fetch_chatgpt_oauth_models(cache_path=cache)
    assert models == ["gpt-5", "gpt-4o"]
    assert "internal-only" not in models


def test_chatgpt_oauth_models_sorts_by_priority(tmp_path):
    cache = tmp_path / "models_cache.json"
    cache.write_text(json.dumps({
        "models": [
            {"slug": "model-b", "priority": 2},
            {"slug": "model-a", "priority": 1},
            {"slug": "model-c", "priority": 3},
        ]
    }), encoding="utf-8")
    models = fetch_chatgpt_oauth_models(cache_path=cache)
    assert models == ["model-a", "model-b", "model-c"]


def test_chatgpt_oauth_models_falls_back_when_cache_absent(tmp_path):
    models = fetch_chatgpt_oauth_models(cache_path=tmp_path / "no_cache.json")
    assert models == list(_CHATGPT_FALLBACK_MODELS)


def test_chatgpt_oauth_models_falls_back_on_invalid_json(tmp_path):
    cache = tmp_path / "models_cache.json"
    cache.write_text("not json", encoding="utf-8")
    models = fetch_chatgpt_oauth_models(cache_path=cache)
    assert models == list(_CHATGPT_FALLBACK_MODELS)


def test_fetch_models_routes_oauth_openai_to_cache(tmp_path):
    cache = tmp_path / "models_cache.json"
    cache.write_text(json.dumps({
        "models": [{"slug": "gpt-5", "priority": 1}]
    }), encoding="utf-8")

    entry = ProviderEntry(
        id="x",
        name="chatgpt",
        provider=ProviderKind.OPENAI,
        auth_type=AuthType.AUTH,
        base_url="https://api.openai.com/v1",
        api_key="oauth_token",
    )
    import marius.provider_config.fetcher as fetcher_mod
    original = fetcher_mod._CODEX_MODELS_CACHE
    fetcher_mod._CODEX_MODELS_CACHE = cache
    try:
        models = fetch_models(entry)
    finally:
        fetcher_mod._CODEX_MODELS_CACHE = original

    assert models == ["gpt-5"]
