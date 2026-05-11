from __future__ import annotations

from pathlib import Path

import pytest

from marius.kernel.guardian_policy import (
    AllowExpansionCode,
    AllowExpansionReason,
    AllowExpansionRequest,
    AllowExpansionStatus,
    DefaultGuardianPolicy,
)
from marius.kernel.project_context import PermissionMode


def _project(tmp_path: Path, name: str) -> Path:
    """Crée un dossier projet minimal avec .git pour satisfaire le détecteur."""
    p = tmp_path / name
    p.mkdir(parents=True)
    (p / ".git").mkdir()
    return p


def _make_request(
    *,
    mode: PermissionMode,
    workspace: Path | None,
    allowed: tuple[Path, ...],
    requested: Path,
    explicit: bool = False,
) -> AllowExpansionRequest:
    return AllowExpansionRequest(
        permission_mode=mode,
        workspace_root=workspace,
        current_allowed_roots=allowed,
        requested_root=requested,
        reason=AllowExpansionReason.ACTIVATE_PROJECT,
        explicit_user_request=explicit,
    )


def test_guardian_policy_returns_not_required_when_requested_root_is_already_allowed(tmp_path):
    workspace = _project(tmp_path, "projets")
    marius = _project(tmp_path, "projets/marius")

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.LIMITED, workspace=workspace,
                      allowed=(workspace,), requested=marius)
    )

    assert decision.status is AllowExpansionStatus.NOT_REQUIRED
    assert decision.code is AllowExpansionCode.ALREADY_ALLOWED


def test_guardian_policy_returns_not_required_in_power_mode_without_mutation(tmp_path):
    workspace = _project(tmp_path, "workspace")
    outside  = _project(tmp_path, "outside")

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.POWER, workspace=workspace,
                      allowed=(workspace,), requested=outside, explicit=True)
    )

    assert decision.status is AllowExpansionStatus.NOT_REQUIRED
    assert decision.code is AllowExpansionCode.POWER_MODE_NO_MUTATION


def test_guardian_policy_denies_safe_mode_expansion(tmp_path):
    workspace = _project(tmp_path, "workspace")
    outside  = _project(tmp_path, "outside")

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.SAFE, workspace=workspace,
                      allowed=(workspace,), requested=outside, explicit=True)
    )

    assert decision.status is AllowExpansionStatus.DENY
    assert decision.code is AllowExpansionCode.SAFE_MODE_FORBIDS_EXPANSION


def test_guardian_policy_asks_for_explicit_request_in_limited_mode(tmp_path):
    workspace = _project(tmp_path, "workspace")
    outside  = _project(tmp_path, "outside")

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.LIMITED, workspace=workspace,
                      allowed=(workspace,), requested=outside, explicit=False)
    )

    assert decision.status is AllowExpansionStatus.ASK
    assert decision.code is AllowExpansionCode.EXPLICIT_USER_REQUEST_REQUIRED


def test_guardian_policy_returns_not_required_when_no_allow_zone_is_declared(tmp_path):
    outside = _project(tmp_path, "outside")

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.LIMITED, workspace=None,
                      allowed=(), requested=outside, explicit=False)
    )

    assert decision.status is AllowExpansionStatus.NOT_REQUIRED
    assert decision.code is AllowExpansionCode.NO_ALLOW_ZONE_DECLARED


def test_guardian_policy_denies_requested_root_that_is_broader_than_existing_allow_root(tmp_path):
    workspace = _project(tmp_path, "workspace")
    marius    = _project(tmp_path, "workspace/marius")
    # too_broad = parent de marius → doit être refusé
    too_broad = workspace

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.LIMITED, workspace=workspace,
                      allowed=(marius,), requested=too_broad, explicit=True)
    )

    assert decision.status in (AllowExpansionStatus.DENY, AllowExpansionStatus.NOT_REQUIRED)


def test_guardian_policy_allows_explicit_limited_extension_for_specific_root(tmp_path):
    workspace = _project(tmp_path, "workspace")
    outside   = _project(tmp_path, "outside")

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.LIMITED, workspace=workspace,
                      allowed=(workspace,), requested=outside, explicit=True)
    )

    assert decision.status is AllowExpansionStatus.ALLOW
    assert decision.code is AllowExpansionCode.REQUESTED_ROOT_ALLOWED
    assert outside.resolve() in decision.roots_to_add


def test_guardian_policy_denies_system_path(tmp_path):
    workspace = _project(tmp_path, "workspace")

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.LIMITED, workspace=workspace,
                      allowed=(workspace,), requested=Path("/etc"), explicit=True)
    )

    assert decision.status is AllowExpansionStatus.DENY
    assert decision.code is AllowExpansionCode.NOT_A_PROJECT


def test_guardian_policy_asks_when_no_project_markers(tmp_path):
    workspace = _project(tmp_path, "workspace")
    # dossier hors workspace, sans marqueur
    empty_dir = tmp_path / "other_dir"
    empty_dir.mkdir(parents=True)

    decision = DefaultGuardianPolicy().review_allow_expansion(
        _make_request(mode=PermissionMode.LIMITED, workspace=workspace,
                      allowed=(workspace,), requested=empty_dir, explicit=False)
    )

    assert decision.status is AllowExpansionStatus.ASK
    assert decision.code is AllowExpansionCode.NO_PROJECT_MARKERS
