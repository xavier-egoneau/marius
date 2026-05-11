"""Helpers git read-only pour le panneau de diff web.

Adapté de Maurice/maurice/host/git_status.py.
Standalone — stdlib uniquement.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def git_changes(root: str | Path, *, max_files: int = 200) -> dict[str, Any]:
    """Retourne la liste des fichiers modifiés avec stats insertions/deletions."""
    base = Path(root).expanduser().resolve()
    git_root = _git_root(base)
    if git_root is None:
        return {"ok": True, "available": False, "files": [], "total_files": 0,
                "insertions": 0, "deletions": 0}

    status = _git(git_root, "status", "--porcelain=v1", "-z")
    if status.returncode != 0:
        return {"ok": False, "available": False, "files": [], "total_files": 0,
                "insertions": 0, "deletions": 0, "error": status.stderr.strip()}

    stat = _git(git_root, "diff", "--numstat", "HEAD", "--")
    stat_by_path = _parse_numstat(stat.stdout if stat.returncode == 0 else "")
    files = _parse_porcelain(status.stdout, stat_by_path)

    ins = sum(f["insertions"] for f in files)
    dels = sum(f["deletions"] for f in files)
    return {
        "ok": True,
        "available": True,
        "root": str(git_root),
        "files": files[:max_files],
        "total_files": len(files),
        "insertions": ins,
        "deletions": dels,
    }


def git_diff(root: str | Path, file_path: str, *, max_chars: int = 40_000) -> dict[str, Any]:
    """Retourne le diff d'un fichier (unstaged puis staged puis untracked)."""
    base = Path(root).expanduser().resolve()
    git_root = _git_root(base)
    if git_root is None:
        return {"ok": False, "diff": "", "error": "not_git_repository"}

    path = _safe_path(file_path)
    if path is None:
        return {"ok": False, "diff": "", "error": "invalid_path"}

    diff = _git(git_root, "diff", "--", path).stdout
    if not diff:
        diff = _git(git_root, "diff", "--cached", "--", path).stdout
    if not diff and (git_root / path).is_file():
        content = (git_root / path).read_text(encoding="utf-8", errors="replace")
        diff = "\n".join(f"+{l}" for l in content.splitlines())

    truncated = len(diff) > max_chars
    if truncated:
        diff = diff[:max_chars].rstrip() + "\n... diff tronqué ..."

    return {"ok": True, "path": path, "diff": diff, "truncated": truncated}


# ── helpers ───────────────────────────────────────────────────────────────────

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=False, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def _git_root(path: Path) -> Path | None:
    r = _git(path, "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        return None
    v = r.stdout.strip()
    return Path(v).resolve() if v else None


def _parse_numstat(output: str) -> dict[str, tuple[int, int]]:
    stats: dict[str, tuple[int, int]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins  = 0 if parts[0] == "-" else int(parts[0] or 0)
        dels = 0 if parts[1] == "-" else int(parts[1] or 0)
        stats[parts[-1]] = (ins, dels)
    return stats


def _parse_porcelain(output: str, stats: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    entries = [e for e in output.split("\0") if e]
    i = 0
    while i < len(entries):
        entry = entries[i]
        code = entry[:2]
        path = entry[3:]
        if code[:1] in ("R", "C"):
            i += 1
            if i < len(entries):
                path = entries[i]
        ins, dels = stats.get(path, (0, 0))
        files.append({"path": path, "status": code, "label": _label(code),
                      "insertions": ins, "deletions": dels})
        i += 1
    return files


def _label(code: str) -> str:
    if code == "??": return "untracked"
    if "D" in code:  return "deleted"
    if "R" in code:  return "renamed"
    if "A" in code:  return "added"
    if "M" in code:  return "modified"
    return code.strip() or "changed"


def _safe_path(value: str) -> str | None:
    p = str(value or "").strip()
    if not p or p.startswith("/") or "\\" in p:
        return None
    if any(part == ".." for part in Path(p).parts):
        return None
    if re.match(r"^[A-Za-z]:", p):
        return None
    return p
