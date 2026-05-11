"""CalDAV calendar tools backed by local vdirsyncer and khal."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_DEFAULT_DAYS = 7
_DEFAULT_TIMEOUT = 30
_VDIRSYNCER_CONFIG = Path.home() / ".config" / "vdirsyncer" / "config"
_KHAL_CONFIG = Path.home() / ".config" / "khal" / "config"


def _doctor(arguments: dict[str, Any]) -> ToolResult:
    del arguments
    status = _setup_status()
    summary = "CalDAV calendar access looks ready." if status["ready"] else "CalDAV setup incomplete: " + "; ".join(status["missing"])
    return ToolResult(tool_call_id="", ok=True, summary=summary, data=status)


def _agenda(arguments: dict[str, Any]) -> ToolResult:
    days = _positive_int(arguments.get("days"), _DEFAULT_DAYS)
    timeout = _positive_int(arguments.get("timeout_seconds"), _DEFAULT_TIMEOUT)
    sync = bool(arguments.get("sync", True))
    status = _setup_status()
    if not status["ready"]:
        return ToolResult(tool_call_id="", ok=False, summary="CalDAV setup incomplete: " + "; ".join(status["missing"]), data=status, error="setup_incomplete")

    sync_error = ""
    if sync:
        sync_result = _run(["vdirsyncer", "sync"], timeout=timeout)
        if sync_result["returncode"] != 0:
            sync_error = _compact_error(sync_result)

    read = _read_agenda(days=days, timeout=timeout)
    if read["returncode"] != 0:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Calendar read failed: {_compact_error(read)}",
            data={"stderr": read["stderr"][:1000], "sync_error": sync_error},
            error="khal_failed",
        )
    events = _event_lines(read["stdout"])
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary=_agenda_summary(events, days=days, sync_error=sync_error),
        data={"days": days, "events": events, "sync_error": sync_error},
    )


def _maintenance(arguments: dict[str, Any]) -> ToolResult:
    operation = str(arguments.get("operation") or "refresh").strip().lower()
    if operation not in {"refresh", "discover", "sync", "verify"}:
        return ToolResult(tool_call_id="", ok=False, summary=f"Unknown operation: {operation}", error="invalid_operation")
    days = _positive_int(arguments.get("days"), _DEFAULT_DAYS)
    timeout = _positive_int(arguments.get("timeout_seconds"), _DEFAULT_TIMEOUT)
    status = _setup_status()
    if not status["ready"]:
        return ToolResult(tool_call_id="", ok=False, summary="CalDAV setup incomplete: " + "; ".join(status["missing"]), data=status, error="setup_incomplete")

    steps: list[dict[str, Any]] = []
    if operation in {"refresh", "discover"}:
        steps.append(_step(["vdirsyncer", "discover"], timeout=timeout))
    if operation in {"refresh", "sync"}:
        steps.append(_step(["vdirsyncer", "sync"], timeout=timeout))
    if operation in {"refresh", "sync", "verify"}:
        read = _read_agenda(days=days, timeout=timeout)
        steps.append({
            "command": f"khal list today {days}d",
            "returncode": read["returncode"],
            "ok": read["returncode"] == 0,
            "summary": _agenda_summary(_event_lines(read["stdout"]), days=days, sync_error="")
            if read["returncode"] == 0 else _compact_error(read),
            "stderr": read["stderr"][:1000],
        })

    failed = [step for step in steps if not step["ok"]]
    return ToolResult(
        tool_call_id="",
        ok=not failed,
        summary=("CalDAV maintenance failed: " if failed else "CalDAV maintenance completed: ")
        + "; ".join(step["summary"] for step in (failed or steps)),
        data={"operation": operation, "steps": steps},
        error="maintenance_failed" if failed else None,
    )


CALDAV_DOCTOR = ToolEntry(
    ToolDefinition(
        name="caldav_doctor",
        description="Check whether local CalDAV access through vdirsyncer and khal is installed and configured.",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    _doctor,
)

CALDAV_AGENDA = ToolEntry(
    ToolDefinition(
        name="caldav_agenda",
        description="Read local calendar events for today and the next few days through khal.",
        parameters={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "minimum": 1},
                "sync": {"type": "boolean"},
                "timeout_seconds": {"type": "integer", "minimum": 1},
            },
            "required": [],
        },
    ),
    _agenda,
)

CALDAV_MAINTENANCE = ToolEntry(
    ToolDefinition(
        name="caldav_maintenance",
        description="Run CalDAV maintenance: discover, sync, verify, or refresh.",
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["refresh", "discover", "sync", "verify"]},
                "days": {"type": "integer", "minimum": 1},
                "timeout_seconds": {"type": "integer", "minimum": 1},
            },
            "required": [],
        },
    ),
    _maintenance,
)


def _setup_status() -> dict[str, Any]:
    bins = {"vdirsyncer": shutil.which("vdirsyncer"), "khal": shutil.which("khal")}
    files = {"vdirsyncer_config": _VDIRSYNCER_CONFIG.exists(), "khal_config": _KHAL_CONFIG.exists()}
    missing: list[str] = []
    for name, path in bins.items():
        if not path:
            missing.append(f"missing binary `{name}`")
    for name, exists in files.items():
        if not exists:
            missing.append(f"missing {name.replace('_', ' ')}")
    return {"ready": not missing, "missing": missing, "binaries": bins, "files": files}


def _read_agenda(*, days: int, timeout: int) -> dict[str, Any]:
    return _run(["khal", "list", "today", f"{days}d"], timeout=timeout)


def _run(command: list[str], *, timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        return {"command": command, "returncode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {"command": command, "returncode": 124, "stdout": exc.stdout or "", "stderr": "timeout"}
    return {"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _step(command: list[str], *, timeout: int) -> dict[str, Any]:
    result = _run(command, timeout=timeout)
    return {
        "command": " ".join(command),
        "returncode": result["returncode"],
        "ok": result["returncode"] == 0,
        "summary": "ok" if result["returncode"] == 0 else _compact_error(result),
        "stderr": result["stderr"][:1000],
    }


def _event_lines(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if line.strip()][:50]


def _agenda_summary(events: list[str], *, days: int, sync_error: str) -> str:
    parts = [f"{len(events)} calendar event(s) over {days} day(s)."]
    if events:
        parts.append("; ".join(events[:5]))
    if sync_error:
        parts.append(f"Sync warning: {sync_error}")
    return " ".join(parts)


def _compact_error(result: dict[str, Any]) -> str:
    stderr = str(result.get("stderr") or "").strip()
    stdout = str(result.get("stdout") or "").strip()
    return (stderr or stdout or f"exit {result.get('returncode')}")[:500]


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default

