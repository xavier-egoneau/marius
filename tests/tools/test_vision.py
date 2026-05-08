from __future__ import annotations

import base64
import json
import urllib.error
from unittest.mock import MagicMock

from marius.tools.vision import VISION


def _mock_response(body: dict) -> MagicMock:
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode("utf-8")
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_vision_calls_local_ollama(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_bytes(b"fake-image-bytes")
    calls = []

    def fake_urlopen(req, timeout=120):
        calls.append((req, timeout))
        return _mock_response({"message": {"content": "Une capture avec du texte."}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = VISION.handler({"path": str(image), "prompt": "Que vois-tu ?"})

    assert result.ok is True
    assert result.summary == "Une capture avec du texte."
    assert result.data["model"] == "gemma4"
    assert result.data["base_url"] == "http://localhost:11434"
    assert result.artifacts[0].path == str(image)

    req, timeout = calls[0]
    assert req.full_url == "http://localhost:11434/api/chat"
    assert timeout == 120
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["model"] == "gemma4"
    assert payload["stream"] is False
    assert payload["messages"][0]["content"] == "Que vois-tu ?"
    assert payload["messages"][0]["images"] == [
        base64.b64encode(b"fake-image-bytes").decode("ascii")
    ]


def test_vision_uses_env_configuration(monkeypatch, tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"jpg")
    seen_urls = []

    def fake_urlopen(req, timeout=120):
        seen_urls.append(req.full_url)
        return _mock_response({"message": {"content": "Photo."}})

    monkeypatch.setenv("MARIUS_VISION_MODEL", "gemma4:latest")
    monkeypatch.setenv("MARIUS_VISION_OLLAMA_URL", "http://127.0.0.1:11434/")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = VISION.handler({"path": str(image)})

    assert result.ok is True
    assert result.data["model"] == "gemma4:latest"
    assert seen_urls == ["http://127.0.0.1:11434/api/chat"]


def test_vision_rejects_missing_path():
    result = VISION.handler({})
    assert result.ok is False
    assert result.error == "missing_arg:path"


def test_vision_rejects_unsupported_file_type(tmp_path):
    file = tmp_path / "note.txt"
    file.write_text("not an image", encoding="utf-8")

    result = VISION.handler({"path": str(file)})

    assert result.ok is False
    assert result.error == "unsupported_image_type"


def test_vision_reports_missing_image(tmp_path):
    result = VISION.handler({"path": str(tmp_path / "missing.png")})
    assert result.ok is False
    assert result.error == "file_not_found"


def test_vision_reports_unreachable_ollama(monkeypatch, tmp_path):
    image = tmp_path / "screen.webp"
    image.write_bytes(b"webp")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("refused")),
    )

    result = VISION.handler({"path": str(image)})

    assert result.ok is False
    assert result.error == "ollama_unreachable"


def test_vision_reports_empty_ollama_response(monkeypatch, tmp_path):
    image = tmp_path / "screen.gif"
    image.write_bytes(b"gif")
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _mock_response({"message": {}}))

    result = VISION.handler({"path": str(image)})

    assert result.ok is False
    assert result.error == "empty_vision_response"
