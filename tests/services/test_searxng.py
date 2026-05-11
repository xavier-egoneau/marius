from __future__ import annotations

from marius.services.searxng import DEFAULT_SEARCH_URL, ensure_searxng_started


def test_ensure_searxng_started_returns_when_already_running(monkeypatch):
    monkeypatch.setattr("marius.services.searxng._url_ok", lambda _url: True)

    result = ensure_searxng_started()

    assert result.ok is True
    assert result.status == "already_running"


def test_ensure_searxng_started_runs_compose_and_waits(monkeypatch, tmp_path):
    compose = tmp_path / "docker-compose.searxng.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    calls: list[list[str]] = []
    checks = {"count": 0}

    def fake_url_ok(_url):
        checks["count"] += 1
        return checks["count"] >= 2

    def fake_run(command, **_kwargs):
        calls.append(command)

    monkeypatch.setattr("marius.services.searxng._url_ok", fake_url_ok)
    monkeypatch.setattr("marius.services.searxng.subprocess.run", fake_run)
    monkeypatch.setattr("marius.services.searxng.time.sleep", lambda _seconds: None)

    result = ensure_searxng_started(compose_file=compose)

    assert result.ok is True
    assert result.status == "started"
    assert calls == [["docker", "compose", "-f", str(compose), "up", "-d"]]


def test_ensure_searxng_started_does_not_start_custom_url(monkeypatch):
    monkeypatch.setattr("marius.services.searxng._url_ok", lambda _url: False)

    result = ensure_searxng_started(url="http://search.example.test")

    assert result.ok is False
    assert result.status == "custom_url_unreachable"
    assert result.url != DEFAULT_SEARCH_URL

