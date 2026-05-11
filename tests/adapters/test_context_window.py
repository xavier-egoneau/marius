from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

from marius.adapters.context_window import make_api_resolver, resolve_via_api


def _mock_urlopen(body: dict) -> MagicMock:
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_resolve_via_api_ollama_format():
    body = {"modelinfo": {"llama.context_length": 131_072, "other": "data"}}
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        result = resolve_via_api("http://localhost:11434", "/api/show", "llama3")
    assert result == 131_072


def test_resolve_via_api_returns_none_on_missing_key():
    body = {"modelinfo": {"some_other_key": 42}}
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        result = resolve_via_api("http://localhost:11434", "/api/show", "llama3")
    assert result is None


def test_resolve_via_api_returns_none_on_network_error():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        result = resolve_via_api("http://localhost:11434", "/api/show", "llama3")
    assert result is None


def test_resolve_via_api_returns_none_on_http_error():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None),
    ):
        result = resolve_via_api("http://localhost:11434", "/api/show", "llama3")
    assert result is None


def test_make_api_resolver_returns_callable():
    body = {"modelinfo": {"llama.context_length": 32_768}}
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        resolver = make_api_resolver("http://localhost:11434", "/api/show", "llama3")
        result = resolver()
    assert result == 32_768


def test_make_api_resolver_returns_none_on_failure():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        resolver = make_api_resolver("http://localhost:11434", "/api/show", "llama3")
        result = resolver()
    assert result is None
