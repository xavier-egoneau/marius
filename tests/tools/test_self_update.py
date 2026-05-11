from __future__ import annotations

import subprocess

from marius.kernel.contracts import ArtifactType
from marius.tools.self_update import make_self_update_tools


def test_self_update_propose_writes_markdown_and_diff_artifact(tmp_path):
    tools = make_self_update_tools(root=tmp_path)

    result = tools["self_update_propose"].handler(
        {
            "title": "Improve update flow",
            "summary": "Create a proposal-only update flow.",
            "problem": "Updates are not tracked.",
            "changes": ["Add proposal records", "Keep apply explicit"],
            "files": ["marius/tools/self_update.py"],
            "test_plan": ["pytest tests/tools/test_self_update.py -q"],
            "risks": ["Proposal backlog may grow"],
            "patch": "@@ -1 +1 @@\n-old\n+new",
        }
    )

    path = tmp_path / "proposals" / f"{result.data['id']}.md"
    assert result.ok is True
    assert result.data["applied"] is False
    assert result.data["approval_required"] is True
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "status: proposed" in content
    assert "applied: false" in content
    assert "## Test Plan" in content
    assert any(artifact.type == ArtifactType.REPORT for artifact in result.artifacts)
    assert any(artifact.type == ArtifactType.DIFF for artifact in result.artifacts)


def test_self_update_propose_refuses_apply_flag(tmp_path):
    tools = make_self_update_tools(root=tmp_path)

    result = tools["self_update_propose"].handler(
        {"title": "Apply me", "summary": "Should not apply.", "apply": True}
    )

    assert result.ok is False
    assert result.error == "apply_not_supported"
    assert not (tmp_path / "proposals").exists()


def test_self_update_report_bug_writes_markdown(tmp_path):
    tools = make_self_update_tools(root=tmp_path)

    result = tools["self_update_report_bug"].handler(
        {
            "title": "Gateway final response missing",
            "observed": "Telegram got an empty final message.",
            "expected": "Final assistant message is sent.",
            "steps": ["Run gateway", "Send message"],
            "related_files": ["marius/gateway/server.py"],
        }
    )

    path = tmp_path / "bugs" / f"{result.data['id']}.md"
    assert result.ok is True
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "kind: self_update_bug" in content
    assert "Telegram got an empty final message." in content


def test_self_update_list_and_show_records(tmp_path):
    tools = make_self_update_tools(root=tmp_path)
    proposal = tools["self_update_propose"].handler(
        {"title": "One", "summary": "First proposal."}
    )
    bug = tools["self_update_report_bug"].handler(
        {"title": "Two", "observed": "Second record."}
    )

    listed = tools["self_update_list"].handler({"kind": "all"})
    shown = tools["self_update_show"].handler({"id": proposal.data["id"]})
    invalid = tools["self_update_show"].handler({"id": "../bad"})

    ids = {row["id"] for row in listed.data["records"]}
    assert proposal.data["id"] in ids
    assert bug.data["id"] in ids
    assert shown.ok is True
    assert "# One" in shown.summary
    assert invalid.ok is False
    assert invalid.error == "record_not_found"


def test_self_update_apply_requires_confirmation(tmp_path):
    tools = make_self_update_tools(root=tmp_path)
    proposal = tools["self_update_propose"].handler(
        {
            "title": "Patch readme",
            "summary": "Patch a file.",
            "patch": "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-old\n+new\n",
        }
    )

    result = tools["self_update_apply"].handler({"id": proposal.data["id"]})

    assert result.ok is False
    assert result.error == "confirmation_required"


def test_self_update_apply_and_rollback_patch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("old\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    (repo / "README.md").write_text("new\n", encoding="utf-8")
    patch = _git(repo, "diff", "--", "README.md").stdout
    (repo / "README.md").write_text("old\n", encoding="utf-8")
    tools = make_self_update_tools(root=tmp_path / "updates")
    proposal = tools["self_update_propose"].handler(
        {
            "title": "Patch readme",
            "summary": "Patch a file.",
            "test_plan": ["git diff --check"],
            "patch": patch,
        }
    )

    applied = tools["self_update_apply"].handler(
        {"id": proposal.data["id"], "confirm": True, "repo_path": str(repo)}
    )
    assert applied.ok is True
    assert (repo / "README.md").read_text(encoding="utf-8") == "new\n"

    rolled_back = tools["self_update_rollback"].handler(
        {"id": proposal.data["id"], "confirm": True, "repo_path": str(repo)}
    )

    assert (repo / "README.md").read_text(encoding="utf-8") == "old\n"
    assert rolled_back.ok is True
    assert applied.data["rollback_available"] is True
    assert (tmp_path / "updates" / "applied" / f"{proposal.data['id']}.md").exists()
    assert (tmp_path / "updates" / "rollbacks" / f"{proposal.data['id']}.md").exists()


def test_self_update_apply_refuses_dirty_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("old\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    (repo / "OTHER.md").write_text("dirty\n", encoding="utf-8")
    tools = make_self_update_tools(root=tmp_path / "updates")
    proposal = tools["self_update_propose"].handler(
        {
            "title": "Patch readme",
            "summary": "Patch a file.",
            "patch": "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-old\n+new\n",
        }
    )

    result = tools["self_update_apply"].handler(
        {"id": proposal.data["id"], "confirm": True, "repo_path": str(repo)}
    )

    assert result.ok is False
    assert result.error == "dirty_worktree"


def _git(cwd, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result
