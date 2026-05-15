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
    assert g.check("browser_open", {"url": "https://example.com"}) is True
    assert g.check("browser_extract", {}) is True
    assert g.check("browser_close", {}) is True


def test_browser_interactions_ask_for_confirmation(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or False)

    assert g.check("browser_click", {"text": "Delete"}) is False
    assert g.check("browser_type", {"selector": "input", "text": "secret"}) is False
    assert [call[0] for call in asked] == ["browser_click", "browser_type"]


def test_safe_allows_memory(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("memory", {"action": "add", "target": "agent", "content": "test"}) is True


def test_safe_allows_readonly_host_diagnostics(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("host_status", {}) is True
    assert g.check("host_doctor", {}) is True
    assert g.check("host_logs", {"limit": 5}) is True
    assert g.check("host_agent_list", {}) is True
    assert g.check("project_list", {}) is True
    assert g.check("approval_list", {}) is True
    assert g.check("secret_ref_list", {}) is True
    assert g.check("provider_list", {}) is True


def test_host_config_writes_are_guarded(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or False)

    assert g.check("host_agent_save", {"name": "worker"}) is False
    assert g.check("host_agent_delete", {"name": "worker", "confirm": True}) is False
    assert g.check("host_gateway_restart", {"agent": "main", "confirm": True}) is False
    assert [call[0] for call in asked] == [
        "host_agent_save",
        "host_agent_delete",
        "host_gateway_restart",
    ]


def test_host_telegram_configure_reads_token_ref_and_writes_config(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or True)

    result = g.check("host_telegram_configure", {"token_ref": f"file:{tmp_path / 'token.txt'}"})

    assert result is True
    assert [call[0] for call in asked] == ["host_telegram_configure"]
    assert "Lecture hors du projet" in asked[0][1]
    assert "Écriture hors du projet" in asked[0][1]


def test_safe_denies_host_config_writes_outside_cwd(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("host_agent_save", {"name": "worker"}) is False
    assert g.check("host_telegram_configure", {"token_ref": "env:BOT_TOKEN"}) is False


def test_project_set_active_is_guarded_as_runtime_write(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or True)

    assert g.check("project_set_active", {"path": str(tmp_path / "other")}) is True

    assert [call[0] for call in asked] == ["project_set_active"]
    assert "Écriture hors du projet" in asked[0][1]
    assert "Lecture hors du projet" in asked[0][1]


def test_project_set_active_create_checks_requested_path_as_write(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or True)

    target = tmp_path / "new-project"

    assert g.check("project_set_active", {"path": str(target), "create": True}) is True

    assert [call[0] for call in asked] == ["project_set_active"]
    assert "Écriture hors du projet" in asked[0][1]
    assert str(target) in asked[0][1]
    assert "Lecture hors du projet" not in asked[0][1]


def test_security_admin_writes_are_guarded(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or True)

    assert g.check("approval_decide", {"id": "x", "approved": True, "confirm": True}) is True
    assert g.check("approval_forget", {"id": "x", "confirm": True}) is True
    assert g.check("secret_ref_save", {"name": "bot", "ref": f"file:{tmp_path / 'token'}"}) is True
    assert g.check("secret_ref_delete", {"name": "bot", "confirm": True}) is True
    assert g.check("secret_ref_prepare_file", {"name": "bot"}) is True

    assert [call[0] for call in asked] == [
        "approval_decide",
        "approval_forget",
        "secret_ref_save",
        "secret_ref_delete",
        "secret_ref_prepare_file",
    ]


def test_provider_admin_writes_are_guarded(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or True)

    assert g.check("provider_save", {"name": "openai", "api_key_ref": f"file:{tmp_path / 'key'}"}) is True
    assert g.check("provider_delete", {"id": "p1", "confirm": True}) is True
    assert g.check("provider_models", {"id": "p1"}) is True

    assert [call[0] for call in asked] == ["provider_save", "provider_delete", "provider_models"]


def test_dreaming_run_is_guarded_as_runtime_write(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or True)

    assert g.check("dreaming_run", {}) is True

    assert [call[0] for call in asked] == ["dreaming_run"]


def test_safe_denies_project_set_active_outside_cwd(cwd: Path, tmp_path: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("project_set_active", {"path": str(tmp_path / "other")}) is False


def test_self_update_records_are_guarded_as_runtime_files(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or True)

    assert g.check("self_update_propose", {"title": "x"}) is True
    assert g.check("self_update_report_bug", {"title": "x"}) is True
    assert g.check("self_update_list", {}) is True
    assert g.check("self_update_show", {"id": "20260510T120000Z_demo"}) is True
    assert g.check("self_update_apply", {"id": "20260510T120000Z_demo", "confirm": True, "repo_path": str(cwd)}) is True
    assert g.check("self_update_rollback", {"id": "20260510T120000Z_demo", "confirm": True, "repo_path": str(cwd)}) is True

    assert [call[0] for call in asked] == [
        "self_update_propose",
        "self_update_report_bug",
        "self_update_list",
        "self_update_show",
        "self_update_apply",
        "self_update_rollback",
    ]


def test_safe_denies_self_update_writes_outside_cwd(cwd: Path) -> None:
    g = _guard("safe", cwd)
    assert g.check("self_update_propose", {"title": "x"}) is False
    assert g.check("self_update_report_bug", {"title": "x"}) is False
    assert g.check("self_update_apply", {"id": "x", "confirm": True}) is False


def test_skill_create_is_guarded_as_runtime_write(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or False)

    result = g.check("skill_create", {"name": "demo"})

    assert result is False
    assert asked
    assert asked[0][0] == "skill_create"


def test_skill_list_and_reload_are_guarded_as_runtime_read(cwd: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append(t) or True)

    assert g.check("skill_list", {}) is True
    assert g.check("skill_reload", {}) is True
    assert asked == ["skill_list", "skill_reload"]


# ── limited mode ──────────────────────────────────────────────────────────────


def test_limited_allows_read_inside_cwd(cwd: Path) -> None:
    g = _guard("limited", cwd)
    assert g.check("read_file", {"path": str(cwd / "src" / "main.py")}) is True


def test_limited_treats_vision_as_file_read(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or False)

    assert g.check("vision", {"path": str(cwd / "image.png")}) is True
    assert g.check("vision", {"path": str(tmp_path / "outside.png")}) is False
    assert asked


def test_limited_treats_explore_tools_as_file_read(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append((t, r)) or False)

    assert g.check("explore_tree", {"path": str(cwd)}) is True
    assert g.check("explore_grep", {"path": str(tmp_path / "outside"), "pattern": "x"}) is False
    assert g.check("explore_summary", {"path": str(tmp_path / "outside")}) is False
    assert [call[0] for call in asked] == ["explore_grep", "explore_summary"]


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
    assert g.check("make_dir", {"path": str(cwd / "nested")}) is True


def test_limited_allows_read_and_write_inside_allowed_roots(cwd: Path, tmp_path: Path) -> None:
    trusted = tmp_path / "trusted-project"
    asked = []
    g = PermissionGuard(
        mode="limited",
        cwd=cwd,
        allowed_roots=(trusted,),
        on_ask=lambda t, a, r: asked.append(r) or False,
    )

    assert g.check("read_file", {"path": str(trusted / "README.md")}) is True
    assert g.check("write_file", {"path": str(trusted / "out.txt")}) is True
    assert g.check("make_dir", {"path": str(trusted / "nested")}) is True
    assert asked == []


def test_limited_refreshes_dynamic_allowed_roots(cwd: Path, tmp_path: Path) -> None:
    dynamic_root = tmp_path / "active-project"
    asked = []
    g = PermissionGuard(
        mode="limited",
        cwd=cwd,
        allowed_roots_provider=lambda: (dynamic_root,),
        on_ask=lambda t, a, r: asked.append(r) or False,
    )

    assert g.check("write_file", {"path": str(dynamic_root / "out.txt")}) is True
    assert asked == []


def test_limited_checks_move_source_and_destination(cwd: Path, tmp_path: Path) -> None:
    asked = []
    g = PermissionGuard(mode="limited", cwd=cwd, on_ask=lambda t, a, r: asked.append(r) or False)

    result = g.check(
        "move_path",
        {
            "source": str(cwd / "inside.txt"),
            "destination": str(tmp_path / "outside.txt"),
        },
    )

    assert result is False
    assert asked


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


def test_approval_lookup_can_skip_prompt(cwd: Path, tmp_path: Path) -> None:
    calls = []
    g = PermissionGuard(
        mode="limited",
        cwd=cwd,
        on_ask=lambda t, a, r: calls.append(1) or False,
        approval_lookup=lambda fingerprint: True,
    )

    assert g.check("write_file", {"path": str(tmp_path / "outside.txt")}) is True
    assert calls == []


def test_approval_recorder_receives_user_decision(cwd: Path, tmp_path: Path) -> None:
    events = []
    g = PermissionGuard(
        mode="limited",
        cwd=cwd,
        on_ask=lambda t, a, r: True,
        approval_recorder=events.append,
    )

    assert g.check("write_file", {"path": str(tmp_path / "outside.txt")}) is True

    assert events
    assert events[0]["tool_name"] == "write_file"
    assert events[0]["approved"] is True
