from __future__ import annotations

from pathlib import Path

from marius.kernel.worker import WorkerResult
from marius.tools.spawn_agent import make_spawn_agent_tool


def test_spawn_agent_forwards_allowed_roots_to_workers(monkeypatch, tmp_path: Path) -> None:
    allowed = tmp_path / "active-project"
    dynamic = tmp_path / "dynamic-project"
    calls: list[dict] = []

    def fake_run_worker(*args, **kwargs) -> WorkerResult:
        calls.append(kwargs)
        return WorkerResult(
            task="audit",
            status="completed",
            summary="ok",
        )

    monkeypatch.setattr("marius.tools.spawn_agent.run_worker", fake_run_worker)

    tool = make_spawn_agent_tool(
        object(),
        [],
        cwd=tmp_path / "workspace",
        allowed_roots=(allowed,),
        allowed_roots_provider=lambda: (dynamic,),
    )

    result = tool.handler({"workers": [{"task": "audit"}]})

    assert result.ok is True
    assert calls[0]["allowed_roots"] == (allowed,)
    assert calls[0]["allowed_roots_provider"]() == (dynamic,)


def test_spawn_agent_summarizes_worker_permission_requests(monkeypatch, tmp_path: Path) -> None:
    def fake_run_worker(*args, **kwargs) -> WorkerResult:
        return WorkerResult(
            task="audit",
            status="blocked",
            summary="permission requise",
            permission_requests=[
                {
                    "tool": "read_file",
                    "arguments": {"path": str(tmp_path / "outside.txt")},
                    "reason": "Lecture hors du projet",
                }
            ],
        )

    monkeypatch.setattr("marius.tools.spawn_agent.run_worker", fake_run_worker)

    tool = make_spawn_agent_tool(object(), [], cwd=tmp_path / "workspace")
    result = tool.handler({"workers": [{"task": "audit"}]})

    assert result.ok is True
    assert "permission" in result.summary
    assert result.data["workers"][0]["permission_requests"][0]["tool"] == "read_file"


def test_spawn_agent_enforces_minimum_worker_timeout(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    def fake_run_worker(*args, **kwargs) -> WorkerResult:
        calls.append(kwargs)
        return WorkerResult(task="audit", status="completed", summary="ok")

    monkeypatch.setattr("marius.tools.spawn_agent.run_worker", fake_run_worker)

    tool = make_spawn_agent_tool(object(), [], cwd=tmp_path / "workspace")
    result = tool.handler({"workers": [{"task": "audit"}], "max_seconds": 5})

    assert result.ok is True
    assert calls[0]["max_seconds"] == 60
    assert result.data["max_seconds"] == 60


def test_spawn_agent_summarizes_timeouts(monkeypatch, tmp_path: Path) -> None:
    def fake_run_worker(*args, **kwargs) -> WorkerResult:
        return WorkerResult(
            task="audit",
            status="timeout",
            summary="Worker interrompu.",
        )

    monkeypatch.setattr("marius.tools.spawn_agent.run_worker", fake_run_worker)

    tool = make_spawn_agent_tool(object(), [], cwd=tmp_path / "workspace")
    result = tool.handler({"workers": [{"task": "audit"}], "max_seconds": 5})

    assert result.ok is True
    assert "1 expiré(s) après 60s" in result.summary
