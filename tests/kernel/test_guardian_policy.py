from __future__ import annotations

from pathlib import Path

from marius.kernel.guardian_policy import (
    AllowExpansionCode,
    AllowExpansionReason,
    AllowExpansionRequest,
    AllowExpansionStatus,
    DefaultGuardianPolicy,
)
from marius.kernel.project_context import PermissionMode


WORKSPACE_ROOT = Path("/home/egza/Documents/projets")
MARIUS_ROOT = Path("/home/egza/Documents/projets/marius")
OUTSIDE_ROOT = Path("/opt/outside-project")
TOO_BROAD_ROOT = Path("/home/egza/Documents")


def test_guardian_policy_returns_not_required_when_requested_root_is_already_allowed() -> None:
    policy = DefaultGuardianPolicy()

    decision = policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=PermissionMode.LIMITED,
            workspace_root=WORKSPACE_ROOT,
            current_allowed_roots=(WORKSPACE_ROOT,),
            requested_root=MARIUS_ROOT,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=False,
        )
    )

    assert decision.status is AllowExpansionStatus.NOT_REQUIRED
    assert decision.code is AllowExpansionCode.ALREADY_ALLOWED
    assert decision.roots_to_add == ()



def test_guardian_policy_returns_not_required_in_power_mode_without_mutation() -> None:
    policy = DefaultGuardianPolicy()

    decision = policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=PermissionMode.POWER,
            workspace_root=WORKSPACE_ROOT,
            current_allowed_roots=(WORKSPACE_ROOT,),
            requested_root=OUTSIDE_ROOT,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=True,
        )
    )

    assert decision.status is AllowExpansionStatus.NOT_REQUIRED
    assert decision.code is AllowExpansionCode.POWER_MODE_NO_MUTATION
    assert decision.roots_to_add == ()



def test_guardian_policy_denies_safe_mode_expansion() -> None:
    policy = DefaultGuardianPolicy()

    decision = policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=PermissionMode.SAFE,
            workspace_root=WORKSPACE_ROOT,
            current_allowed_roots=(WORKSPACE_ROOT,),
            requested_root=OUTSIDE_ROOT,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=True,
        )
    )

    assert decision.status is AllowExpansionStatus.DENY
    assert decision.code is AllowExpansionCode.SAFE_MODE_FORBIDS_EXPANSION
    assert decision.roots_to_add == ()



def test_guardian_policy_asks_for_explicit_request_in_limited_mode() -> None:
    policy = DefaultGuardianPolicy()

    decision = policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=PermissionMode.LIMITED,
            workspace_root=WORKSPACE_ROOT,
            current_allowed_roots=(WORKSPACE_ROOT,),
            requested_root=OUTSIDE_ROOT,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=False,
        )
    )

    assert decision.status is AllowExpansionStatus.ASK
    assert decision.code is AllowExpansionCode.EXPLICIT_USER_REQUEST_REQUIRED
    assert decision.roots_to_add == ()



def test_guardian_policy_returns_not_required_when_no_allow_zone_is_declared() -> None:
    policy = DefaultGuardianPolicy()

    decision = policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=PermissionMode.LIMITED,
            workspace_root=None,
            current_allowed_roots=(),
            requested_root=OUTSIDE_ROOT,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=False,
        )
    )

    assert decision.status is AllowExpansionStatus.NOT_REQUIRED
    assert decision.code is AllowExpansionCode.NO_ALLOW_ZONE_DECLARED
    assert decision.roots_to_add == ()



def test_guardian_policy_denies_requested_root_that_is_broader_than_existing_allow_root() -> None:
    policy = DefaultGuardianPolicy()

    decision = policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=PermissionMode.LIMITED,
            workspace_root=WORKSPACE_ROOT,
            current_allowed_roots=(MARIUS_ROOT,),
            requested_root=TOO_BROAD_ROOT,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=True,
        )
    )

    assert decision.status is AllowExpansionStatus.DENY
    assert decision.code is AllowExpansionCode.REQUESTED_ROOT_TOO_BROAD
    assert decision.roots_to_add == ()



def test_guardian_policy_allows_explicit_limited_extension_for_specific_root() -> None:
    policy = DefaultGuardianPolicy()

    decision = policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=PermissionMode.LIMITED,
            workspace_root=WORKSPACE_ROOT,
            current_allowed_roots=(WORKSPACE_ROOT,),
            requested_root=OUTSIDE_ROOT,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=True,
        )
    )

    assert decision.status is AllowExpansionStatus.ALLOW
    assert decision.code is AllowExpansionCode.REQUESTED_ROOT_ALLOWED
    assert decision.roots_to_add == (OUTSIDE_ROOT,)
