"""Politique minimale du gardien pour les extensions de zone allow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from marius.kernel.project_context import PermissionMode


class AllowExpansionReason(str, Enum):
    ACTIVATE_PROJECT = "activate_project"


class AllowExpansionStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class AllowExpansionCode(str, Enum):
    ALREADY_ALLOWED = "already_allowed"
    POWER_MODE_NO_MUTATION = "power_mode_no_mutation"
    SAFE_MODE_FORBIDS_EXPANSION = "safe_mode_forbids_expansion"
    NO_ALLOW_ZONE_DECLARED = "no_allow_zone_declared"
    EXPLICIT_USER_REQUEST_REQUIRED = "explicit_user_request_required"
    REQUESTED_ROOT_TOO_BROAD = "requested_root_too_broad"
    REQUESTED_ROOT_ALLOWED = "requested_root_allowed"


@dataclass(slots=True, frozen=True)
class AllowExpansionRequest:
    permission_mode: PermissionMode
    workspace_root: Path | None
    current_allowed_roots: tuple[Path, ...]
    requested_root: Path
    reason: AllowExpansionReason
    explicit_user_request: bool = False


@dataclass(slots=True, frozen=True)
class AllowExpansionDecision:
    status: AllowExpansionStatus
    code: AllowExpansionCode
    roots_to_add: tuple[Path, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class GuardianPolicy(Protocol):
    def review_allow_expansion(self, request: AllowExpansionRequest) -> AllowExpansionDecision:
        ...


class DefaultGuardianPolicy:
    def review_allow_expansion(self, request: AllowExpansionRequest) -> AllowExpansionDecision:
        requested_root = request.requested_root
        allowed_roots = request.current_allowed_roots

        if self._is_allowed(requested_root, allowed_roots):
            return AllowExpansionDecision(
                status=AllowExpansionStatus.NOT_REQUIRED,
                code=AllowExpansionCode.ALREADY_ALLOWED,
            )

        if request.permission_mode is PermissionMode.POWER:
            return AllowExpansionDecision(
                status=AllowExpansionStatus.NOT_REQUIRED,
                code=AllowExpansionCode.POWER_MODE_NO_MUTATION,
            )

        if request.permission_mode is PermissionMode.SAFE:
            return AllowExpansionDecision(
                status=AllowExpansionStatus.DENY,
                code=AllowExpansionCode.SAFE_MODE_FORBIDS_EXPANSION,
            )

        if not request.current_allowed_roots and request.workspace_root is None:
            return AllowExpansionDecision(
                status=AllowExpansionStatus.NOT_REQUIRED,
                code=AllowExpansionCode.NO_ALLOW_ZONE_DECLARED,
            )

        if not request.explicit_user_request:
            return AllowExpansionDecision(
                status=AllowExpansionStatus.ASK,
                code=AllowExpansionCode.EXPLICIT_USER_REQUEST_REQUIRED,
            )

        if self._is_too_broad(requested_root, allowed_roots, request.workspace_root):
            return AllowExpansionDecision(
                status=AllowExpansionStatus.DENY,
                code=AllowExpansionCode.REQUESTED_ROOT_TOO_BROAD,
            )

        return AllowExpansionDecision(
            status=AllowExpansionStatus.ALLOW,
            code=AllowExpansionCode.REQUESTED_ROOT_ALLOWED,
            roots_to_add=(requested_root,),
        )

    def _is_allowed(self, candidate: Path, allowed_roots: tuple[Path, ...]) -> bool:
        for root in allowed_roots:
            if candidate == root or root in candidate.parents:
                return True
        return False

    def _is_too_broad(
        self,
        requested_root: Path,
        allowed_roots: tuple[Path, ...],
        workspace_root: Path | None = None,
    ) -> bool:
        normalized_requested_root = self._normalize_path(requested_root)
        if workspace_root is not None:
            normalized_workspace_root = self._normalize_path(workspace_root)
            if normalized_requested_root in normalized_workspace_root.parents:
                return True

        for root in allowed_roots:
            normalized_root = self._normalize_path(root)
            if normalized_requested_root in normalized_root.parents:
                return True
        return False

    def _normalize_path(self, path: Path) -> Path:
        return path.expanduser().resolve(strict=False)
