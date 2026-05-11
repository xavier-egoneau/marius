from __future__ import annotations

from pathlib import Path

from marius.storage.log_store import clear_logs, log_event, preview, read_logs


def test_log_event_appends_jsonl_entries(tmp_path: Path) -> None:
    path = tmp_path / "marius.jsonl"

    log_event("turn_start", {"cwd": "/tmp/project", "model": "gpt"}, log_path=path)
    log_event("turn_done", {"assistant_preview": "ok"}, log_path=path)

    entries = read_logs(limit=10, log_path=path)

    assert [entry.event for entry in entries] == ["turn_start", "turn_done"]
    assert entries[0].data["cwd"] == "/tmp/project"
    assert entries[1].data["assistant_preview"] == "ok"


def test_read_logs_respects_limit(tmp_path: Path) -> None:
    path = tmp_path / "marius.jsonl"
    for i in range(5):
        log_event("event", {"i": i}, log_path=path)

    entries = read_logs(limit=2, log_path=path)

    assert [entry.data["i"] for entry in entries] == [3, 4]


def test_read_logs_ignores_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "marius.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    log_event("valid", {"ok": True}, log_path=path)

    entries = read_logs(limit=10, log_path=path)

    assert len(entries) == 1
    assert entries[0].event == "valid"


def test_clear_logs_empties_file(tmp_path: Path) -> None:
    path = tmp_path / "marius.jsonl"
    log_event("event", {}, log_path=path)

    clear_logs(log_path=path)

    assert read_logs(log_path=path) == []
    assert path.exists()


def test_preview_compacts_and_truncates() -> None:
    text = "hello\n\nworld " + ("x" * 400)
    result = preview(text, limit=20)

    assert "\n" not in result
    assert result.endswith("…")
    assert len(result) == 20
