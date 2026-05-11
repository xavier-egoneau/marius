from __future__ import annotations

from types import SimpleNamespace

from marius.tools.marius_web import OPEN_MARIUS_WEB


def test_open_marius_web_reuses_existing_server(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("marius.tools.marius_web._default_agent_name", lambda: "main")
    monkeypatch.setattr("marius.tools.marius_web._web_is_available", lambda port: True)
    monkeypatch.setattr("marius.tools.marius_web._open_browser", lambda url: opened.append(url) or True)

    result = OPEN_MARIUS_WEB.handler({"port": 8765})

    assert result.ok is True
    assert result.data["already_running"] is True
    assert result.data["url"] == "http://localhost:8765"
    assert opened == ["http://localhost:8765"]


def test_open_marius_web_starts_gateway_and_web_server(monkeypatch):
    calls: dict[str, object] = {}
    availability = iter([False, True])
    monkeypatch.setattr("marius.tools.marius_web._default_agent_name", lambda: "main")
    monkeypatch.setattr("marius.tools.marius_web._web_is_available", lambda port: next(availability))
    monkeypatch.setattr("marius.tools.marius_web._wait_for_web", lambda port: True)
    monkeypatch.setattr("marius.tools.marius_web._open_browser", lambda url: False)
    monkeypatch.setattr("marius.gateway.launcher.is_running", lambda agent: False)
    monkeypatch.setattr("marius.gateway.launcher.start", lambda agent: calls.setdefault("gateway", agent) or True)

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return SimpleNamespace(pid=123)

    monkeypatch.setattr("marius.tools.marius_web.subprocess.Popen", fake_popen)

    result = OPEN_MARIUS_WEB.handler({"agent": "main", "port": 9999, "open_browser": False})

    assert result.ok is True
    assert result.data["already_running"] is False
    assert result.data["url"] == "http://localhost:9999"
    assert calls["gateway"] == "main"
    assert calls["command"][-4:] == ["--agent", "main", "--port", "9999"]
    assert calls["kwargs"]["start_new_session"] is True


def test_open_marius_web_validates_port():
    result = OPEN_MARIUS_WEB.handler({"port": "nope"})

    assert result.ok is False
    assert result.error == "invalid_port"
