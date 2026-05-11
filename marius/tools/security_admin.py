"""Security administration tools.

Approvals and secret references are exposed as observations/actions for the LLM,
but the final answer still belongs to the model and secret values are never
accepted or returned.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.storage.approval_store import ApprovalRecord, ApprovalStore
from marius.storage.secret_ref_store import SecretRef, SecretRefStore, public_secret_data

_RAW_SECRET_KEYS = ("token", "raw_token", "secret", "secret_value", "value", "password", "api_key")
_SECRET_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


def make_security_admin_tools(
    *,
    approval_path: Path | None = None,
    secret_ref_path: Path | None = None,
) -> dict[str, ToolEntry]:
    approvals = ApprovalStore(path=approval_path)
    secrets = SecretRefStore(path=secret_ref_path)
    secrets_dir = (Path(secret_ref_path).parent / "secrets") if secret_ref_path is not None else Path.home() / ".marius" / "secrets"

    def approval_list(arguments: dict[str, Any]) -> ToolResult:
        limit = _bounded_int(arguments.get("limit"), default=30, minimum=1, maximum=200)
        remembered_only = bool(arguments.get("remembered_only", False))
        records = approvals.list(limit=limit, remembered_only=remembered_only)
        lines = [f"Approvals: {len(records)} record(s)."]
        for record in records:
            status = "approved" if record.approved else "denied"
            memory = "remembered" if record.remembered else "audit"
            lines.append(f"- {record.id}: {status}, {memory}, {record.tool_name}")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={
                "records": [_approval_data(record) for record in records],
                "remembered_only": remembered_only,
            },
        )

    def approval_decide(arguments: dict[str, Any]) -> ToolResult:
        record_id = _optional_text(arguments.get("id"))
        if not record_id:
            return ToolResult(tool_call_id="", ok=False, summary="`id` is required.", error="missing_id")
        if "approved" not in arguments:
            return ToolResult(tool_call_id="", ok=False, summary="`approved` is required.", error="missing_approved")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Decision requires `confirm: true`.", error="confirmation_required")
        remember = _optional_bool(arguments.get("remember"), True)
        record = approvals.decide(record_id, approved=bool(arguments.get("approved")), remember=remember)
        if record is None:
            return ToolResult(tool_call_id="", ok=False, summary=f"Approval not found: {record_id}", error="approval_not_found")
        status = "approved" if record.approved else "denied"
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Approval {status}: {record.id}; remembered={record.remembered}.",
            data={"record": _approval_data(record)},
        )

    def approval_forget(arguments: dict[str, Any]) -> ToolResult:
        record_id = _optional_text(arguments.get("id"))
        if not record_id:
            return ToolResult(tool_call_id="", ok=False, summary="`id` is required.", error="missing_id")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Forgetting requires `confirm: true`.", error="confirmation_required")
        record = approvals.forget(record_id)
        if record is None:
            return ToolResult(tool_call_id="", ok=False, summary=f"Approval not found: {record_id}", error="approval_not_found")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Approval forgotten: {record.id}.",
            data={"record": _approval_data(record)},
        )

    def secret_ref_list(arguments: dict[str, Any]) -> ToolResult:
        refs = secrets.list()
        lines = [f"Secret references: {len(refs)} registered."]
        for ref in refs:
            desc = f" — {ref.description}" if ref.description else ""
            lines.append(f"- {ref.name}: {ref.ref}{desc}")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={"secrets": [_secret_data(ref) for ref in refs]},
        )

    def secret_ref_save(arguments: dict[str, Any]) -> ToolResult:
        if any(key in arguments for key in _RAW_SECRET_KEYS):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Raw secret values are refused. Register only `ref` as env:NAME or file:/path.",
                error="raw_secret_refused",
            )
        name = _optional_text(arguments.get("name"))
        ref = _optional_text(arguments.get("ref"))
        if not name or not ref:
            return ToolResult(tool_call_id="", ok=False, summary="`name` and `ref` are required.", error="missing_secret_ref")
        description = _optional_text(arguments.get("description")) or ""
        try:
            secret = secrets.save(name=name, ref=ref, description=description)
        except ValueError as exc:
            return ToolResult(tool_call_id="", ok=False, summary=str(exc), error=str(exc))
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Secret reference saved: {secret.name} ({secret.kind}).",
            data={"secret": _secret_data(secret)},
        )

    def secret_ref_delete(arguments: dict[str, Any]) -> ToolResult:
        name = _optional_text(arguments.get("name"))
        if not name:
            return ToolResult(tool_call_id="", ok=False, summary="`name` is required.", error="missing_name")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Deletion requires `confirm: true`.", error="confirmation_required")
        if not secrets.delete(name):
            return ToolResult(tool_call_id="", ok=False, summary=f"Secret reference not found: {name}", error="secret_ref_not_found")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Secret reference deleted: {name}.",
            data={"deleted": name},
        )

    def secret_ref_prepare_file(arguments: dict[str, Any]) -> ToolResult:
        if any(key in arguments for key in _RAW_SECRET_KEYS):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Raw secret values are refused. This tool only prepares a local secret file reference.",
                error="raw_secret_refused",
            )
        name = _optional_text(arguments.get("name"))
        if not name:
            return ToolResult(tool_call_id="", ok=False, summary="`name` is required.", error="missing_name")
        description = _optional_text(arguments.get("description")) or ""
        try:
            path = _prepare_secret_file(name, base_dir=secrets_dir)
            secret = secrets.save(name=name, ref=f"file:{path}", description=description)
        except ValueError as exc:
            return ToolResult(tool_call_id="", ok=False, summary=str(exc), error=str(exc))
        except OSError as exc:
            return ToolResult(tool_call_id="", ok=False, summary=f"Cannot prepare secret file: {exc}", error="secret_file_prepare_failed")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=(
                f"Secret file prepared for {secret.name}. Put the secret value in `{path}` "
                "outside the chat; Marius stores only the file reference."
            ),
            data={
                "secret": _secret_data(secret),
                "path": str(path),
                "ref": f"file:{path}",
                "mode": "0600",
            },
        )

    return {
        "approval_list": ToolEntry(
            definition=ToolDefinition(
                name="approval_list",
                description="List recent permission approval records and remembered decisions.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                        "remembered_only": {"type": "boolean"},
                    },
                    "required": [],
                },
            ),
            handler=approval_list,
        ),
        "approval_decide": ToolEntry(
            definition=ToolDefinition(
                name="approval_decide",
                description="Remember an approval or denial for a previous permission record.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "remember": {"type": "boolean"},
                        "confirm": {"type": "boolean"},
                    },
                    "required": ["id", "approved", "confirm"],
                },
            ),
            handler=approval_decide,
        ),
        "approval_forget": ToolEntry(
            definition=ToolDefinition(
                name="approval_forget",
                description="Disable a remembered approval or denial.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "confirm": {"type": "boolean"},
                    },
                    "required": ["id", "confirm"],
                },
            ),
            handler=approval_forget,
        ),
        "secret_ref_list": ToolEntry(
            definition=ToolDefinition(
                name="secret_ref_list",
                description="List named secret references without resolving their values.",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            handler=secret_ref_list,
        ),
        "secret_ref_save": ToolEntry(
            definition=ToolDefinition(
                name="secret_ref_save",
                description="Register a named secret reference as env:NAME or file:/path, never a raw value.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "ref": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "ref"],
                },
            ),
            handler=secret_ref_save,
        ),
        "secret_ref_delete": ToolEntry(
            definition=ToolDefinition(
                name="secret_ref_delete",
                description="Delete a named secret reference after explicit confirmation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "confirm": {"type": "boolean"},
                    },
                    "required": ["name", "confirm"],
                },
            ),
            handler=secret_ref_delete,
        ),
        "secret_ref_prepare_file": ToolEntry(
            definition=ToolDefinition(
                name="secret_ref_prepare_file",
                description="Prepare a chmod 0600 local file and register it as a named secret reference without receiving the secret value.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name"],
                },
            ),
            handler=secret_ref_prepare_file,
        ),
    }


_DEFAULT_TOOLS = make_security_admin_tools()
APPROVAL_LIST = _DEFAULT_TOOLS["approval_list"]
APPROVAL_DECIDE = _DEFAULT_TOOLS["approval_decide"]
APPROVAL_FORGET = _DEFAULT_TOOLS["approval_forget"]
SECRET_REF_LIST = _DEFAULT_TOOLS["secret_ref_list"]
SECRET_REF_SAVE = _DEFAULT_TOOLS["secret_ref_save"]
SECRET_REF_DELETE = _DEFAULT_TOOLS["secret_ref_delete"]
SECRET_REF_PREPARE_FILE = _DEFAULT_TOOLS["secret_ref_prepare_file"]


def _approval_data(record: ApprovalRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "created_at": record.created_at,
        "fingerprint": record.fingerprint,
        "tool_name": record.tool_name,
        "arguments": record.arguments,
        "reason": record.reason,
        "mode": record.mode,
        "cwd": record.cwd,
        "approved": record.approved,
        "remembered": record.remembered,
        "decided_at": record.decided_at,
    }


def _secret_data(secret: SecretRef) -> dict[str, Any]:
    return public_secret_data(secret)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "oui", "o", "on")
    return bool(value)


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _prepare_secret_file(name: str, *, base_dir: Path) -> Path:
    normalized = name.strip()
    if not _SECRET_NAME_RE.fullmatch(normalized):
        raise ValueError("invalid_secret_name")
    path = base_dir / f"{normalized}.secret"
    base_dir.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    path.chmod(0o600)
    return path
