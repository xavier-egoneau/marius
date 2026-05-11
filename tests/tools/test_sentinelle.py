from __future__ import annotations

from marius.tools import sentinelle
from marius.tools.sentinelle import make_sentinelle_tool


def test_sentinelle_scan_persists_report_and_detects_exposed_docker(monkeypatch, tmp_path):
    def fake_run(command):
        if command[0] == "ss":
            return {"returncode": 0, "stdout": "Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n", "stderr": ""}
        if command[0] == "systemctl":
            return {"returncode": 0, "stdout": "marius.service enabled\n", "stderr": ""}
        if command[0] == "docker":
            return {"returncode": 0, "stdout": "app 0.0.0.0:8080->80/tcp\n", "stderr": ""}
        return {"returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(sentinelle, "_run", fake_run)
    tool = make_sentinelle_tool(tmp_path)

    result = tool.handler({})

    assert result.ok is True
    assert result.data["verdict"] == "alert"
    assert result.data["findings"][0]["type"] == "docker_exposed_port"
    assert (tmp_path / "last_scan.json").exists()
    assert result.artifacts[0].path.endswith(".md")


def test_sentinelle_scan_reports_ok_when_no_findings(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sentinelle,
        "_run",
        lambda _command: {"returncode": 0, "stdout": "", "stderr": ""},
    )
    tool = make_sentinelle_tool(tmp_path)

    result = tool.handler({})

    assert result.ok is True
    assert result.summary == "Tout est ok."
    assert result.data["findings"] == []
