from __future__ import annotations

from marius.config.contracts import ALL_TOOLS, resolved_tool_groups


def test_resolved_tool_groups_classify_all_tools_once() -> None:
    groups = resolved_tool_groups()
    grouped = [tool for group in groups for tool in group["tools"]]

    assert [tool for tool in ALL_TOOLS if tool not in grouped] == []
    assert sorted({tool for tool in grouped if grouped.count(tool) > 1}) == []


def test_task_tools_are_grouped_as_tasks_routines() -> None:
    groups = {group["id"]: group for group in resolved_tool_groups()}

    assert groups["tasks_routines"]["tools"] == [
        "task_create",
        "task_list",
        "task_update",
    ]


def test_browser_tools_are_grouped_as_browser() -> None:
    groups = {group["id"]: group for group in resolved_tool_groups()}

    assert groups["browser"]["tools"] == [
        "browser_open",
        "browser_extract",
        "browser_screenshot",
        "browser_click",
        "browser_type",
        "browser_close",
    ]


def test_unknown_tools_fall_back_to_other_group() -> None:
    groups = resolved_tool_groups(["custom_tool"])

    assert groups == [{
        "id": "other",
        "label": "Other",
        "description": "Outils non classés explicitement",
        "tools": ["custom_tool"],
    }]
