from __future__ import annotations

from pathlib import Path

import pytest

from marius.kernel.permission_guard import PermissionGuard


@pytest.fixture()
def cwd(tmp_path: Path) -> Path:
    return tmp_path / "project"


def _guard(mode: str, cwd: Path, *, approve: bool = True) -> PermissionGuard:
    return PermissionGuard(mode=mode, cwd=cwd, on_ask=lambda *_: approve)


# ── safe mode ─────────────────────────────────────────────────────────────────


def test_safe_allows_read_inside_cwd(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("read_file", {"path": str(cwd / "main.py")}) is True


def test_safe_asks_read_outside_cwd(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="safe", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or False)
    result = g.check("read_file", {"path": str(tmp_path / "other" / "file.py")})
    assert result is False
    assert asked  # on_ask was called


def test_safe_denies_shell(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("run_bash", {"command": "ls"}) is False


def test_safe_asks_write_inside_cwd(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="safe", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or True)
    result = g.check("write_file", {"path": str(cwd / "out.txt"), "content": "x"})
    assert result is True
    assert asked


def test_safe_denies_write_outside_cwd(cwd: Path, tmp_path: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("write_file", {"path": str(tmp_path / "other.txt")}) is False


def test_safe_allows_web(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("web_search", {"query": "python"}) is True
    assert g.check("web_fetch", {"url": "https://example.com"}) is True


def test_safe_allows_memory(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("memory", {"action": "add", "target": "agent", "content": "test"}) is True


# ── limited mode ──────────────────────────────────────────────────────────────


def test_limited_allows_read_inside_cwd(cwd: Path) -> None:
    g = _guard("limited", cwd)
    assert g.check("read_file", {"path": str(cwd / "src" / "main.py")}) is True


def test_limited_asks_read_outside_cwd(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or False)
    g.check("read_file", {"path": str(tmp_path / "other.py")})
    assert asked


def test_limited_allows_shell(cwd: Path) -> None:
    g = _guard("limited", cwd)
    assert g.check("run_bash", {"command": "pytest"}) is True


def test_limited_asks_dangerous_shell(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or False)
    result = g.check("run_bash", {"command": "rm -rf /tmp/something"})
    assert result is False
    assert asked


def test_limited_allows_write_inside_cwd(cwd: Path) -> None:
    g = _guard("limited", cwd)
    assert g.check("write_file", {"path": str(cwd / "output.txt")}) is True


def test_limited_asks_write_outside_cwd(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or False)
    g.check("write_file", {"path": str(tmp_path / "outside.txt")})
    assert asked


# ── power mode ────────────────────────────────────────────────────────────────


def test_power_allows_everything(cwd: Path, tmp_path: Path) -> None:
    g = _guard("power", cwd)
    assert g.check("run_bash", {"command": "ls"}) is True
    assert g.check("write_file", {"path": str(tmp_path / "anywhere.txt")}) is True
    assert g.check("read_file", {"path": str(tmp_path / "other" / "file.py")}) is True


def test_power_still_asks_dangerous_shell(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="power", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or False)
    result = g.check("run_bash", {"command": "rm -rf /var/important"})
    assert result is False
    assert asked


# ── chemins système toujours refusés ─────────────────────────────────────────


def test_system_path_denied_in_limited(cwd: Path) -> None:
    g = _guard("limited", cwd, approve=True)
    assert g.check("read_file", {"path": "/etc/passwd"}) is False


def test_system_path_denied_in_power(cwd: Path) -> None:
    g = _guard("power", cwd, approve=True)
    assert g.check("write_file", {"path": "/usr/local/bin/exploit"}) is False


# ── cache d'approbation ───────────────────────────────────────────────────────


def test_approval_cached_in_session(cwd: Path, tmp_path: Path) -> None:
    calls = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: calls.append(1) or True)
    path = str(tmp_path / "outside.txt")
    g.check("write_file", {"path": path})
    g.check("write_file", {"path": path})
    assert len(calls) == 1  # deuxième appel utilise le cache
