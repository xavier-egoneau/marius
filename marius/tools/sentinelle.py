"""Low-noise local system hygiene scan.

This is the Marius-native shape of the old Sentinelle skill: a standalone tool
that returns observations and persists reports, without taking over the final
chat response.
"""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_DEFAULT_ROOT = Path.home() / ".marius" / "workspace" / "main" / "sentinelle"


def make_sentinelle_tool(root: Path | None = None) -> ToolEntry:
    base = Path(root) if root is not None else _DEFAULT_ROOT

    def scan(arguments: dict[str, Any]) -> ToolResult:
        include_raw = bool(arguments.get("include_raw", False))
        previous = _read_json(base / "last_scan.json")
        snapshot = _collect_snapshot()
        findings = _findings(snapshot, previous if isinstance(previous, dict) else None)
        verdict = "alert" if any(item["severity"] == "high" for item in findings) else "watch" if findings else "ok"
        summary = _summary(verdict, findings)
        paths = _write_report(base, snapshot=snapshot, findings=findings, verdict=verdict, include_raw=include_raw)
        data: dict[str, Any] = {
            "verdict": verdict,
            "findings": findings,
            "paths": {key: str(value) for key, value in paths.items()},
        }
        if include_raw:
            data["snapshot"] = snapshot
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=summary,
            data=data,
            artifacts=[
                Artifact(type=ArtifactType.REPORT, path=str(paths["report"]), data={"content": paths["report"].read_text(encoding="utf-8")}),
                Artifact(type=ArtifactType.FILE, path=str(paths["scan"])),
            ],
        )

    return ToolEntry(
        ToolDefinition(
            name="sentinelle_scan",
            description="Run a low-noise local hygiene audit for listeners, services, autostart, Docker exposure and drift.",
            parameters={
                "type": "object",
                "properties": {
                    "include_raw": {"type": "boolean", "description": "Include the raw snapshot in tool data."},
                },
                "required": [],
            },
        ),
        scan,
    )


SENTINELLE_SCAN = make_sentinelle_tool()


def _collect_snapshot() -> dict[str, Any]:
    system = platform.system().lower()
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system": system,
        "listeners": _listeners(),
        "services": _services(),
        "autostart": _autostart(),
        "docker_ports": _docker_ports(),
    }


def _listeners() -> list[dict[str, str]]:
    result = _run(["ss", "-tulpen"])
    rows: list[dict[str, str]] = []
    for line in result["stdout"].splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[4]
        rows.append({
            "proto": parts[0],
            "state": parts[1],
            "local": local,
            "exposed": str(_is_exposed_address(local)).lower(),
            "process": " ".join(parts[6:]) if len(parts) > 6 else "",
        })
    return rows[:200]


def _services() -> list[str]:
    result = _run(["systemctl", "list-unit-files", "--type=service", "--state=enabled", "--no-pager", "--no-legend"])
    services = []
    for line in result["stdout"].splitlines():
        parts = line.split()
        if parts:
            services.append(parts[0])
    return services[:300]


def _autostart() -> list[str]:
    roots = [
        Path.home() / ".config" / "autostart",
        Path("/etc/xdg/autostart"),
    ]
    entries: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.desktop")):
            entries.append(str(path))
    return entries[:300]


def _docker_ports() -> list[str]:
    result = _run(["docker", "ps", "--format", "{{.Names}} {{.Ports}}"])
    if result["returncode"] != 0:
        return []
    return [line.strip() for line in result["stdout"].splitlines() if line.strip()][:200]


def _findings(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    exposed = [
        item for item in snapshot.get("listeners", [])
        if isinstance(item, dict) and item.get("exposed") == "true"
    ]
    for item in exposed[:20]:
        findings.append({
            "severity": "medium",
            "type": "exposed_listener",
            "title": f"Exposed listener: {item.get('local')}",
            "detail": item.get("process") or "",
        })

    docker_exposed = [
        row for row in snapshot.get("docker_ports", [])
        if isinstance(row, str) and ("0.0.0.0:" in row or ":::" in row)
    ]
    for row in docker_exposed[:20]:
        findings.append({
            "severity": "high",
            "type": "docker_exposed_port",
            "title": f"Docker port exposed outside localhost: {row}",
            "detail": "Review whether this container should bind publicly.",
        })

    if previous:
        previous_services = set(previous.get("services") or [])
        current_services = set(snapshot.get("services") or [])
        for service in sorted(current_services - previous_services)[:20]:
            findings.append({
                "severity": "low",
                "type": "new_enabled_service",
                "title": f"New enabled service: {service}",
                "detail": "First scan after install may include expected inventory.",
            })
        previous_autostart = set(previous.get("autostart") or [])
        current_autostart = set(snapshot.get("autostart") or [])
        for entry in sorted(current_autostart - previous_autostart)[:20]:
            findings.append({
                "severity": "low",
                "type": "new_autostart",
                "title": f"New autostart entry: {entry}",
                "detail": "",
            })

    return findings


def _write_report(
    root: Path,
    *,
    snapshot: dict[str, Any],
    findings: list[dict[str, Any]],
    verdict: str,
    include_raw: bool,
) -> dict[str, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scan_path = root / "scans" / f"{stamp}.json"
    report_path = root / "reports" / f"{stamp}.md"
    root.mkdir(parents=True, exist_ok=True)
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"verdict": verdict, "findings": findings, **snapshot}
    scan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "last_scan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_report_markdown(snapshot, findings, verdict, include_raw=include_raw), encoding="utf-8")
    return {"scan": scan_path, "report": report_path, "latest": root / "last_scan.json"}


def _report_markdown(snapshot: dict[str, Any], findings: list[dict[str, Any]], verdict: str, *, include_raw: bool) -> str:
    lines = [
        "# Sentinelle",
        "",
        f"- Generated: {snapshot.get('generated_at')}",
        f"- Verdict: `{verdict}`",
        "",
    ]
    if not findings:
        lines.append("Tout est ok.")
    else:
        lines.extend(["## Findings", ""])
        for item in findings:
            lines.append(f"- **{item['severity']}** `{item['type']}` — {item['title']}")
            if item.get("detail"):
                lines.append(f"  {item['detail']}")
    if include_raw:
        lines.extend(["", "## Snapshot", "", "```json", json.dumps(snapshot, ensure_ascii=False, indent=2), "```"])
    return "\n".join(lines).rstrip() + "\n"


def _summary(verdict: str, findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "Tout est ok."
    titles = "; ".join(item["title"] for item in findings[:5])
    return f"Sentinelle verdict `{verdict}`: {titles}"


def _run(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
    except FileNotFoundError:
        return {"returncode": 127, "stdout": "", "stderr": f"missing binary: {command[0]}"}
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "stdout": "", "stderr": "timeout"}
    return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _is_exposed_address(local: str) -> bool:
    host = local.rsplit(":", 1)[0].strip("[]")
    return host in {"0.0.0.0", "::", "*"} or host.startswith("*")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

