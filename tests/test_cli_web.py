from __future__ import annotations

import json
from urllib.error import URLError

from marius.cli import _find_marius_dashboard_pids, _find_marius_web_pids, _marius_web_available


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_marius_web_available_accepts_matching_agent(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"ok": True, "agent": "main"}))

    assert _marius_web_available(8765, expected_agent="main") is True


def test_marius_web_available_rejects_other_agent(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"ok": True, "agent": "other"}))

    assert _marius_web_available(8765, expected_agent="main") is False


def test_marius_web_available_returns_false_on_unavailable(monkeypatch):
    def fail(*_args, **_kwargs):
        raise URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", fail)

    assert _marius_web_available(8765, expected_agent="main") is False


def test_find_marius_web_pids_matches_web_and_restart_commands(monkeypatch):
    class _Config:
        main_agent = "main"

    class _Store:
        def load(self):
            return _Config()

    class _Result:
        stdout = "\n".join(
            [
                " 123 /usr/bin/python3 /home/egza/.local/bin/marius web --agent main --port 8765",
                " 124 /usr/bin/python3 /home/egza/.local/bin/marius restart --agent=main --port=8765",
                " 127 /usr/bin/python3 /home/egza/.local/bin/marius restart",
                " 125 /usr/bin/python3 /home/egza/.local/bin/marius web --agent other --port 8765",
                " 126 /usr/bin/python3 /home/egza/.local/bin/marius web --agent main --port 8766",
            ]
        )

    monkeypatch.setattr("marius.config.store.ConfigStore", lambda: _Store())
    monkeypatch.setattr("subprocess.run", lambda *_args, **_kwargs: _Result())

    assert _find_marius_web_pids("main", 8765) == [123, 124, 127]


def test_find_marius_dashboard_pids_matches_cli_and_module(monkeypatch):
    class _Result:
        stdout = "\n".join(
            [
                " 201 /usr/bin/python3 /home/egza/.local/bin/marius dashboard --port 8766",
                " 202 python3 -m marius.channels.dashboard --port 8768 --no-open",
                " 203 /usr/bin/python3 /home/egza/.local/bin/marius web --agent main --port 8765",
                " 204 python3 -m some.other.dashboard --port 9999",
            ]
        )

    monkeypatch.setattr("subprocess.run", lambda *_args, **_kwargs: _Result())

    assert _find_marius_dashboard_pids() == [201, 202]
