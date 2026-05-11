from __future__ import annotations

from pathlib import Path

from marius.kernel.contracts import ToolCall
from marius.kernel.posture import (
    DEV_POSTURE,
    assistant_enabled,
    maybe_activate_dev_posture,
    tool_call_triggers_dev,
    uses_dev_posture,
)


def test_uses_dev_posture_by_default_without_assistant() -> None:
    assert uses_dev_posture([], {}) is True


def test_assistant_mode_starts_without_dev_posture() -> None:
    assert assistant_enabled(["assistant"]) is True
    assert uses_dev_posture(["assistant"], {}) is False


def test_tool_call_inside_project_triggers_dev(tmp_path: Path) -> None:
    call = ToolCall(id="c1", name="read_file", arguments={"path": "src/app.py"})

    assert tool_call_triggers_dev(call, tmp_path) is True


def test_tool_call_outside_project_does_not_trigger_dev(tmp_path: Path) -> None:
    outside = tmp_path.parent / "other" / "notes.txt"
    call = ToolCall(id="c1", name="read_file", arguments={"path": str(outside)})

    assert tool_call_triggers_dev(call, tmp_path) is False


def test_run_bash_without_cwd_triggers_dev(tmp_path: Path) -> None:
    call = ToolCall(id="c1", name="run_bash", arguments={"command": "pytest"})

    assert tool_call_triggers_dev(call, tmp_path) is True


def test_maybe_activate_dev_posture_only_when_assistant_enabled(tmp_path: Path) -> None:
    metadata: dict[str, str] = {}
    call = ToolCall(id="c1", name="list_dir", arguments={"path": "."})

    changed = maybe_activate_dev_posture(metadata, ["assistant"], call, tmp_path)

    assert changed is True
    assert metadata["posture"] == DEV_POSTURE


def test_maybe_activate_dev_posture_ignores_non_assistant(tmp_path: Path) -> None:
    metadata: dict[str, str] = {}
    call = ToolCall(id="c1", name="list_dir", arguments={"path": "."})

    changed = maybe_activate_dev_posture(metadata, [], call, tmp_path)

    assert changed is False
    assert metadata == {}
