from __future__ import annotations

import json
from email.message import Message
from unittest.mock import MagicMock

from marius.tools.web import WEB_FETCH, WEB_SEARCH


def _mock_response(body: bytes, *, status: int = 200, content_type: str = "text/plain") -> MagicMock:
    headers = Message()
    headers["content-type"] = content_type
    mock = MagicMock()
    mock.status = status
    mock.headers = headers
    mock.read.return_value = body
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_web_fetch_returns_valid_tool_result(monkeypatch):
    monkeypatch.setattr(
        "marius.tools.web.urlopen",
        lambda *args, **kwargs: _mock_response(b"bonjour", content_type="text/plain; charset=utf-8"),
    )

    result = WEB_FETCH.handler({"url": "https://example.test"})

    assert result.ok is True
    assert result.tool_call_id == ""
    assert result.data["text"] == "bonjour"


def test_web_fetch_validation_returns_valid_tool_result():
    result = WEB_FETCH.handler({})

    assert result.ok is False
    assert result.tool_call_id == ""


def test_web_search_returns_valid_tool_result(monkeypatch):
    payload = {"results": [{"title": "Marius", "url": "https://example.test", "content": "ok"}]}
    monkeypatch.setattr(
        "marius.tools.web.urlopen",
        lambda *args, **kwargs: _mock_response(json.dumps(payload).encode("utf-8"), content_type="application/json"),
    )

    result = WEB_SEARCH.handler({"query": "marius"})

    assert result.ok is True
    assert result.tool_call_id == ""
    assert result.data["results"][0]["title"] == "Marius"


def test_web_search_validation_returns_valid_tool_result():
    result = WEB_SEARCH.handler({})

    assert result.ok is False
    assert result.tool_call_id == ""
