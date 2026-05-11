from __future__ import annotations

from marius.tools.shell import RUN_BASH


def test_run_bash_success():
    result = RUN_BASH.handler({"command": "echo hello"})
    assert result.ok is True
    assert "hello" in result.summary


def test_run_bash_captures_stderr_on_failure():
    result = RUN_BASH.handler({"command": "ls /nonexistent_path_xyz 2>&1; exit 1"})
    assert result.ok is False


def test_run_bash_missing_command_arg():
    result = RUN_BASH.handler({})
    assert result.ok is False
    assert "command" in result.summary


def test_run_bash_with_cwd(tmp_path):
    result = RUN_BASH.handler({"command": "pwd", "cwd": str(tmp_path)})
    assert result.ok is True
    assert str(tmp_path) in result.summary


def test_run_bash_multiline_output():
    result = RUN_BASH.handler({"command": "printf 'a\nb\nc'"})
    assert result.ok is True
    assert "a" in result.summary
