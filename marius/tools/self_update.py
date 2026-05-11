"""Self-update tools.

Markdown-first: proposal and bug tools record intentions, while apply/rollback
tools only act on explicit recorded proposals with confirmation.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_MARIUS_HOME = Path.home() / ".marius"
_DEFAULT_ROOT = _MARIUS_HOME / "self_updates"
_DEFAULT_REPO = Path(__file__).resolve().parents[2]
_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[a-z0-9][a-z0-9_-]{0,80}$")
_ALLOWED_TEST_PREFIXES = (
    ("pytest",),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("git", "diff", "--check"),
)


def make_self_update_tools(root: Path | None = None) -> dict[str, ToolEntry]:
    base = Path(root) if root is not None else _DEFAULT_ROOT

    def self_update_propose(arguments: dict[str, Any]) -> ToolResult:
        if bool(arguments.get("apply", False)) or bool(arguments.get("auto_apply", False)):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Self-update tools are proposal-only. Applying changes requires an explicit later workflow.",
                error="apply_not_supported",
            )

        title = _text(arguments.get("title"))
        summary = _text(arguments.get("summary") or arguments.get("goal") or arguments.get("problem"))
        if not title:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `title` missing.", error="missing_arg:title")
        if not summary:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `summary` missing.", error="missing_arg:summary")

        proposal_id = _make_id(title)
        path = base / "proposals" / f"{proposal_id}.md"
        patch = _text(arguments.get("patch") or arguments.get("diff"))
        markdown = _proposal_markdown(proposal_id, arguments, title=title, summary=summary, patch=patch)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")

        artifacts = [Artifact(type=ArtifactType.REPORT, path=str(path), data={"content": markdown})]
        if patch:
            artifacts.append(Artifact(type=ArtifactType.DIFF, path=f"{proposal_id}.diff", data={"patch": patch}))

        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Self-update proposal recorded: {proposal_id}. No changes were applied.",
            data={
                "id": proposal_id,
                "path": str(path),
                "kind": "proposal",
                "approval_required": True,
                "applied": False,
            },
            artifacts=artifacts,
        )

    def self_update_report_bug(arguments: dict[str, Any]) -> ToolResult:
        title = _text(arguments.get("title"))
        observed = _text(arguments.get("observed") or arguments.get("actual"))
        if not title:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `title` missing.", error="missing_arg:title")
        if not observed:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `observed` missing.", error="missing_arg:observed")

        report_id = _make_id(title)
        path = base / "bugs" / f"{report_id}.md"
        markdown = _bug_markdown(report_id, arguments, title=title, observed=observed)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Self-update bug report recorded: {report_id}.",
            data={"id": report_id, "path": str(path), "kind": "bug", "applied": False},
            artifacts=[Artifact(type=ArtifactType.REPORT, path=str(path), data={"content": markdown})],
        )

    def self_update_list(arguments: dict[str, Any]) -> ToolResult:
        kind = _text(arguments.get("kind") or "all")
        limit = _bounded_int(arguments.get("limit"), default=20, minimum=1, maximum=100)
        if kind not in ("all", "proposal", "bug"):
            return ToolResult(tool_call_id="", ok=False, summary="Invalid kind. Use all, proposal or bug.", error="invalid_kind")

        rows = _list_records(base, kind=kind, limit=limit)
        lines = [f"Self-update records: {len(rows)} entrie(s)."]
        for row in rows:
            lines.append(f"- {row['id']} [{row['kind']}] {row['title']}")
        return ToolResult(tool_call_id="", ok=True, summary="\n".join(lines), data={"records": rows})

    def self_update_show(arguments: dict[str, Any]) -> ToolResult:
        record_id = _text(arguments.get("id"))
        if not record_id:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `id` missing.", error="missing_arg:id")
        path = _find_record(base, record_id)
        if path is None:
            return ToolResult(tool_call_id="", ok=False, summary=f"Self-update record not found: {record_id}", error="record_not_found")
        content = path.read_text(encoding="utf-8", errors="replace")
        kind = path.parent.name.rstrip("s")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=content,
            data={"id": path.stem, "path": str(path), "kind": kind},
            artifacts=[Artifact(type=ArtifactType.REPORT, path=str(path), data={"content": content})],
        )

    def self_update_apply(arguments: dict[str, Any]) -> ToolResult:
        record_id = _text(arguments.get("id"))
        if not record_id:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `id` missing.", error="missing_arg:id")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Applying a self-update requires `confirm: true`.", error="confirmation_required")

        path = _find_record(base, record_id)
        if path is None or path.parent.name != "proposals":
            return ToolResult(tool_call_id="", ok=False, summary=f"Self-update proposal not found: {record_id}", error="proposal_not_found")
        content = path.read_text(encoding="utf-8", errors="replace")
        if _frontmatter_value(content, "applied") == "true":
            return ToolResult(tool_call_id="", ok=False, summary=f"Self-update proposal already applied: {record_id}", error="already_applied")
        patch = _extract_patch(content)
        if not patch:
            return ToolResult(tool_call_id="", ok=False, summary=f"Self-update proposal has no patch: {record_id}", error="missing_patch")

        repo = _repo_path(arguments.get("repo_path"))
        if not _is_git_repo(repo):
            return ToolResult(tool_call_id="", ok=False, summary=f"Not a git repository: {repo}", error="not_git_repo")
        dirty = _git_status(repo)
        allow_dirty = bool(arguments.get("allow_dirty", False))
        if dirty and not allow_dirty:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Repository has uncommitted changes. Pass `allow_dirty: true` only after documenting that risk.",
                error="dirty_worktree",
                data={"repo_path": str(repo), "status": dirty},
            )

        check = _run(["git", "apply", "--check", "-"], cwd=repo, stdin=patch)
        if check.returncode != 0:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Patch did not pass `git apply --check`.",
                error="patch_check_failed",
                data={"repo_path": str(repo), "stderr": check.stderr},
            )
        applied = _run(["git", "apply", "-"], cwd=repo, stdin=patch)
        if applied.returncode != 0:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Patch application failed.",
                error="patch_apply_failed",
                data={"repo_path": str(repo), "stderr": applied.stderr},
            )

        tests = _test_commands(arguments, content)
        test_results = [_run_test(command, cwd=repo) for command in tests]
        ok_tests = all(result["returncode"] == 0 for result in test_results)
        report = _application_report(
            record_id,
            repo=repo,
            patch=patch,
            dirty_before=dirty,
            test_results=test_results,
            status="applied" if ok_tests else "applied_with_test_failures",
        )
        report_path = base / "applied" / f"{record_id}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        path.write_text(_set_frontmatter_fields(content, {"status": "applied", "applied": "true"}), encoding="utf-8")
        return ToolResult(
            tool_call_id="",
            ok=ok_tests,
            summary=(
                f"Self-update applied: {record_id}. Tests passed."
                if ok_tests else
                f"Self-update applied: {record_id}, but at least one test command failed."
            ),
            data={
                "id": record_id,
                "repo_path": str(repo),
                "report_path": str(report_path),
                "tests": test_results,
                "dirty_before": dirty,
                "rollback_available": True,
            },
            error=None if ok_tests else "tests_failed",
            artifacts=[
                Artifact(type=ArtifactType.REPORT, path=str(report_path), data={"content": report}),
                Artifact(type=ArtifactType.DIFF, path=f"{record_id}.diff", data={"patch": patch}),
            ],
        )

    def self_update_rollback(arguments: dict[str, Any]) -> ToolResult:
        record_id = _text(arguments.get("id"))
        if not record_id:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `id` missing.", error="missing_arg:id")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Rollback requires `confirm: true`.", error="confirmation_required")
        report_path = base / "applied" / f"{record_id}.md"
        if not _ID_RE.fullmatch(record_id) or not report_path.exists():
            return ToolResult(tool_call_id="", ok=False, summary=f"Applied self-update not found: {record_id}", error="applied_record_not_found")
        report = report_path.read_text(encoding="utf-8", errors="replace")
        patch = _extract_patch(report)
        if not patch:
            return ToolResult(tool_call_id="", ok=False, summary=f"Applied self-update has no rollback patch: {record_id}", error="missing_patch")
        repo = _repo_path(arguments.get("repo_path"))
        check = _run(["git", "apply", "-R", "--check", "-"], cwd=repo, stdin=patch)
        if check.returncode != 0:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Rollback patch did not pass `git apply -R --check`.",
                error="rollback_check_failed",
                data={"repo_path": str(repo), "stderr": check.stderr},
            )
        rolled_back = _run(["git", "apply", "-R", "-"], cwd=repo, stdin=patch)
        if rolled_back.returncode != 0:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Rollback failed.",
                error="rollback_failed",
                data={"repo_path": str(repo), "stderr": rolled_back.stderr},
            )
        rollback_report = _rollback_report(record_id, repo=repo, patch=patch)
        rollback_path = base / "rollbacks" / f"{record_id}.md"
        rollback_path.parent.mkdir(parents=True, exist_ok=True)
        rollback_path.write_text(rollback_report, encoding="utf-8")
        proposal_path = base / "proposals" / f"{record_id}.md"
        if proposal_path.exists():
            proposal_content = proposal_path.read_text(encoding="utf-8", errors="replace")
            proposal_path.write_text(_set_frontmatter_fields(proposal_content, {"status": "rolled_back", "applied": "false"}), encoding="utf-8")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Self-update rolled back: {record_id}.",
            data={"id": record_id, "repo_path": str(repo), "report_path": str(rollback_path)},
            artifacts=[Artifact(type=ArtifactType.REPORT, path=str(rollback_path), data={"content": rollback_report})],
        )

    return {
        "self_update_propose": ToolEntry(
            definition=ToolDefinition(
                name="self_update_propose",
                description="Record a Markdown self-update proposal for Marius. Proposal-only: never applies changes.",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "problem": {"type": "string"},
                        "goal": {"type": "string"},
                        "rationale": {"type": "string"},
                        "changes": {"type": "array", "items": {"type": "string"}},
                        "files": {"type": "array", "items": {"type": "string"}},
                        "test_plan": {"type": "array", "items": {"type": "string"}},
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "rollback_plan": {"type": "string"},
                        "patch": {"type": "string", "description": "Optional unified diff to attach as an artifact."},
                        "source": {"type": "string"},
                    },
                    "required": ["title", "summary"],
                },
            ),
            handler=self_update_propose,
        ),
        "self_update_report_bug": ToolEntry(
            definition=ToolDefinition(
                name="self_update_report_bug",
                description="Record a Markdown bug report for a future Marius self-update proposal.",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "observed": {"type": "string"},
                        "expected": {"type": "string"},
                        "steps": {"type": "array", "items": {"type": "string"}},
                        "severity": {"type": "string"},
                        "context": {"type": "string"},
                        "related_files": {"type": "array", "items": {"type": "string"}},
                        "source": {"type": "string"},
                    },
                    "required": ["title", "observed"],
                },
            ),
            handler=self_update_report_bug,
        ),
        "self_update_list": ToolEntry(
            definition=ToolDefinition(
                name="self_update_list",
                description="List recorded self-update proposals and bug reports.",
                parameters={
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "description": "all, proposal or bug."},
                        "limit": {"type": "integer", "description": "Maximum records, default 20, max 100."},
                    },
                    "required": [],
                },
            ),
            handler=self_update_list,
        ),
        "self_update_show": ToolEntry(
            definition=ToolDefinition(
                name="self_update_show",
                description="Read a recorded self-update proposal or bug report by id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                    },
                    "required": ["id"],
                },
            ),
            handler=self_update_show,
        ),
        "self_update_apply": ToolEntry(
            definition=ToolDefinition(
                name="self_update_apply",
                description="Apply a recorded self-update proposal patch after explicit confirmation, then run bounded test commands.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "confirm": {"type": "boolean"},
                        "repo_path": {"type": "string"},
                        "allow_dirty": {"type": "boolean"},
                        "test_commands": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "confirm"],
                },
            ),
            handler=self_update_apply,
        ),
        "self_update_rollback": ToolEntry(
            definition=ToolDefinition(
                name="self_update_rollback",
                description="Rollback a previously applied self-update by reversing its recorded patch.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "confirm": {"type": "boolean"},
                        "repo_path": {"type": "string"},
                    },
                    "required": ["id", "confirm"],
                },
            ),
            handler=self_update_rollback,
        ),
    }


_DEFAULT_TOOLS = make_self_update_tools()
SELF_UPDATE_PROPOSE = _DEFAULT_TOOLS["self_update_propose"]
SELF_UPDATE_REPORT_BUG = _DEFAULT_TOOLS["self_update_report_bug"]
SELF_UPDATE_LIST = _DEFAULT_TOOLS["self_update_list"]
SELF_UPDATE_SHOW = _DEFAULT_TOOLS["self_update_show"]
SELF_UPDATE_APPLY = _DEFAULT_TOOLS["self_update_apply"]
SELF_UPDATE_ROLLBACK = _DEFAULT_TOOLS["self_update_rollback"]


def _proposal_markdown(
    proposal_id: str,
    arguments: dict[str, Any],
    *,
    title: str,
    summary: str,
    patch: str,
) -> str:
    return "\n".join(
        [
            "---",
            f"id: {proposal_id}",
            "kind: self_update_proposal",
            f"created_at: {_now()}",
            "status: proposed",
            "applied: false",
            "approval_required: true",
            "---",
            "",
            f"# {title}",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Problem",
            "",
            _text(arguments.get("problem")) or summary,
            "",
            "## Rationale",
            "",
            _text(arguments.get("rationale")) or "Not specified.",
            "",
            "## Proposed Changes",
            "",
            _markdown_list(arguments.get("changes"), fallback="Not specified."),
            "",
            "## Files",
            "",
            _markdown_list(arguments.get("files"), fallback="Not specified."),
            "",
            "## Test Plan",
            "",
            _markdown_list(arguments.get("test_plan"), fallback="Not specified."),
            "",
            "## Risks",
            "",
            _markdown_list(arguments.get("risks"), fallback="Not specified."),
            "",
            "## Rollback Plan",
            "",
            _text(arguments.get("rollback_plan")) or "Revert the eventual explicit patch or commit.",
            "",
            "## Patch",
            "",
            _diff_block(patch) if patch else "No patch attached.",
            "",
            "## Source",
            "",
            _text(arguments.get("source")) or "agent",
            "",
        ]
    )


def _bug_markdown(report_id: str, arguments: dict[str, Any], *, title: str, observed: str) -> str:
    return "\n".join(
        [
            "---",
            f"id: {report_id}",
            "kind: self_update_bug",
            f"created_at: {_now()}",
            "status: reported",
            "applied: false",
            "---",
            "",
            f"# {title}",
            "",
            "## Severity",
            "",
            _text(arguments.get("severity")) or "unknown",
            "",
            "## Observed",
            "",
            observed,
            "",
            "## Expected",
            "",
            _text(arguments.get("expected")) or "Not specified.",
            "",
            "## Reproduction Steps",
            "",
            _markdown_list(arguments.get("steps"), fallback="Not specified."),
            "",
            "## Context",
            "",
            _text(arguments.get("context")) or "Not specified.",
            "",
            "## Related Files",
            "",
            _markdown_list(arguments.get("related_files"), fallback="Not specified."),
            "",
            "## Source",
            "",
            _text(arguments.get("source")) or "agent",
            "",
        ]
    )


def _list_records(root: Path, *, kind: str, limit: int) -> list[dict[str, Any]]:
    paths: list[Path] = []
    if kind in ("all", "proposal"):
        paths.extend((root / "proposals").glob("*.md"))
    if kind in ("all", "bug"):
        paths.extend((root / "bugs").glob("*.md"))
    paths.sort(key=lambda path: path.name, reverse=True)
    return [_record_row(path) for path in paths[:limit]]


def _find_record(root: Path, record_id: str) -> Path | None:
    if not _ID_RE.fullmatch(record_id):
        return None
    for folder in ("proposals", "bugs"):
        path = root / folder / f"{record_id}.md"
        if path.exists() and path.is_file():
            return path
    return None


def _record_row(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    status = _frontmatter_value(content, "status") or ""
    applied = _frontmatter_value(content, "applied") == "true"
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return {
        "id": path.stem,
        "kind": path.parent.name.rstrip("s"),
        "title": title,
        "path": str(path),
        "status": status,
        "applied": applied,
    }


def _repo_path(value: object) -> Path:
    text = _text(value)
    return Path(text).expanduser().resolve() if text else _DEFAULT_REPO


def _is_git_repo(path: Path) -> bool:
    return _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path).returncode == 0


def _git_status(path: Path) -> list[str]:
    result = _run(["git", "status", "--short"], cwd=path)
    if result.returncode != 0:
        return [result.stderr.strip() or "git status failed"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def _run(command: list[str], *, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            input=stdin,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def _test_commands(arguments: dict[str, Any], proposal_content: str) -> list[str]:
    explicit = _string_list(arguments.get("test_commands"))
    candidates = explicit or _section_list(proposal_content, "Test Plan")
    commands: list[str] = []
    for command in candidates:
        if _allowed_test_command(command):
            commands.append(command)
    if not commands:
        commands.append("git diff --check")
    return commands[:5]


def _run_test(command: str, *, cwd: Path) -> dict[str, Any]:
    args = shlex.split(command)
    result = _run(args, cwd=cwd)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def _allowed_test_command(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    return any(tuple(parts[:len(prefix)]) == prefix for prefix in _ALLOWED_TEST_PREFIXES)


def _section_list(markdown: str, title: str) -> list[str]:
    section = _section_text(markdown, title)
    items: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _section_text(markdown: str, title: str) -> str:
    marker = f"## {title}"
    start = markdown.find(marker)
    if start < 0:
        return ""
    start = markdown.find("\n", start)
    if start < 0:
        return ""
    end = markdown.find("\n## ", start + 1)
    if end < 0:
        end = len(markdown)
    return markdown[start:end].strip()


def _extract_patch(markdown: str) -> str:
    section = _section_text(markdown, "Patch")
    match = re.search(r"^(`{3,})diff\n(.*?)\n\1\s*$", section, flags=re.DOTALL | re.MULTILINE)
    if not match:
        return ""
    patch = match.group(2)
    return patch if patch.endswith("\n") else f"{patch}\n"


def _frontmatter_value(markdown: str, key: str) -> str:
    if not markdown.startswith("---\n"):
        return ""
    end = markdown.find("\n---", 4)
    if end < 0:
        return ""
    for line in markdown[4:end].splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _set_frontmatter_fields(markdown: str, values: dict[str, str]) -> str:
    if not markdown.startswith("---\n"):
        return markdown
    end = markdown.find("\n---", 4)
    if end < 0:
        return markdown
    lines = markdown[4:end].splitlines()
    seen: set[str] = set()
    updated: list[str] = []
    for line in lines:
        key = line.split(":", 1)[0].strip()
        if key in values:
            updated.append(f"{key}: {values[key]}")
            seen.add(key)
        else:
            updated.append(line)
    for key, value in values.items():
        if key not in seen:
            updated.append(f"{key}: {value}")
    return "---\n" + "\n".join(updated) + markdown[end:]


def _application_report(
    record_id: str,
    *,
    repo: Path,
    patch: str,
    dirty_before: list[str],
    test_results: list[dict[str, Any]],
    status: str,
) -> str:
    lines = [
        "---",
        f"id: {record_id}",
        "kind: self_update_application",
        f"created_at: {_now()}",
        f"status: {status}",
        "---",
        "",
        f"# Self-update application: {record_id}",
        "",
        f"- Repo: `{repo}`",
        f"- Dirty before: {'yes' if dirty_before else 'no'}",
        "",
        "## Tests",
        "",
    ]
    if not test_results:
        lines.append("No tests were run.")
    for result in test_results:
        state = "passed" if result["returncode"] == 0 else "failed"
        lines.append(f"- `{result['command']}`: {state} ({result['returncode']})")
    lines.extend([
        "",
        "## Rollback",
        "",
        f"Run `self_update_rollback` with `id: {record_id}` and `confirm: true`.",
        "",
        "## Patch",
        "",
        _diff_block(patch),
        "",
    ])
    return "\n".join(lines)


def _rollback_report(record_id: str, *, repo: Path, patch: str) -> str:
    return "\n".join([
        "---",
        f"id: {record_id}",
        "kind: self_update_rollback",
        f"created_at: {_now()}",
        "status: rolled_back",
        "---",
        "",
        f"# Self-update rollback: {record_id}",
        "",
        f"- Repo: `{repo}`",
        "",
        "## Patch",
        "",
        _diff_block(patch),
        "",
    ])


def _make_id(title: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9_-]+", "-", title.lower()).strip("-_")[:56] or "proposal"
    suffix = uuid.uuid4().hex[:6]
    return f"{timestamp}_{slug}_{suffix}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _markdown_list(value: object, *, fallback: str) -> str:
    items = _string_list(value)
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.splitlines() if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _diff_block(patch: str) -> str:
    fence = "```"
    while fence in patch:
        fence += "`"
    return f"{fence}diff\n{patch}\n{fence}"


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))
