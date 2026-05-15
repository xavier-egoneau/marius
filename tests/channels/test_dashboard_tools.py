from __future__ import annotations

from marius.channels.dashboard.server import _api_tools


def test_api_tools_exposes_backend_tool_groups() -> None:
    data = _api_tools()
    groups = {group["id"]: group for group in data["groups"]}

    assert "tools" in data
    assert "admin_only" in data
    assert "core" in data
    assert groups["tasks_routines"]["tools"] == [
        "task_create",
        "task_list",
        "task_update",
    ]
