from __future__ import annotations

import json

from marius.storage.approval_store import ApprovalStore
from marius.tools.security_admin import make_security_admin_tools


def test_approval_tools_list_and_decide(tmp_path):
    approval_path = tmp_path / "approvals.json"
    store = ApprovalStore(path=approval_path)
    record = store.record(
        fingerprint="abc",
        tool_name="write_file",
        arguments={"path": "/tmp/x"},
        reason="outside",
        mode="limited",
        cwd="/tmp/project",
        approved=True,
    )
    tools = make_security_admin_tools(approval_path=approval_path)

    listed = tools["approval_list"].handler({})
    decided = tools["approval_decide"].handler({"id": record.id, "approved": False, "confirm": True})

    assert listed.ok is True
    assert listed.data["records"][0]["id"] == record.id
    assert decided.ok is True
    assert ApprovalStore(path=approval_path).lookup("abc") is False


def test_approval_decide_requires_confirmation(tmp_path):
    approval_path = tmp_path / "approvals.json"
    record = ApprovalStore(path=approval_path).record(
        fingerprint="abc",
        tool_name="write_file",
        arguments={},
        reason="outside",
        mode="limited",
        cwd="/tmp/project",
        approved=True,
    )
    tools = make_security_admin_tools(approval_path=approval_path)

    result = tools["approval_decide"].handler({"id": record.id, "approved": True})

    assert result.ok is False
    assert result.error == "confirmation_required"


def test_secret_ref_tools_refuse_raw_secret_and_save_reference(tmp_path):
    secret_path = tmp_path / "secret_refs.json"
    tools = make_security_admin_tools(secret_ref_path=secret_path)

    refused = tools["secret_ref_save"].handler({"name": "telegram", "secret": "123456:secret"})
    saved = tools["secret_ref_save"].handler({"name": "telegram", "ref": "env:BOT_TOKEN"})
    listed = tools["secret_ref_list"].handler({})

    raw = json.loads(secret_path.read_text(encoding="utf-8"))
    assert refused.ok is False
    assert refused.error == "raw_secret_refused"
    assert saved.ok is True
    assert raw[0]["ref"] == "env:BOT_TOKEN"
    assert listed.data["secrets"][0]["name"] == "telegram"


def test_secret_ref_delete_requires_confirmation(tmp_path):
    secret_path = tmp_path / "secret_refs.json"
    tools = make_security_admin_tools(secret_ref_path=secret_path)
    tools["secret_ref_save"].handler({"name": "telegram", "ref": "env:BOT_TOKEN"})

    refused = tools["secret_ref_delete"].handler({"name": "telegram"})
    deleted = tools["secret_ref_delete"].handler({"name": "telegram", "confirm": True})

    assert refused.error == "confirmation_required"
    assert deleted.ok is True


def test_secret_ref_prepare_file_registers_private_file_reference(tmp_path):
    secret_path = tmp_path / "secret_refs.json"
    tools = make_security_admin_tools(secret_ref_path=secret_path)

    result = tools["secret_ref_prepare_file"].handler(
        {"name": "telegram", "description": "Bot token"}
    )

    prepared = tmp_path / "secrets" / "telegram.secret"
    raw = json.loads(secret_path.read_text(encoding="utf-8"))
    assert result.ok is True
    assert prepared.exists()
    assert oct(prepared.stat().st_mode & 0o777) == "0o600"
    assert raw[0]["ref"] == f"file:{prepared}"
    assert result.data["secret"]["kind"] == "file"


def test_secret_ref_prepare_file_refuses_raw_secret(tmp_path):
    tools = make_security_admin_tools(secret_ref_path=tmp_path / "secret_refs.json")

    result = tools["secret_ref_prepare_file"].handler({"name": "telegram", "value": "secret"})

    assert result.ok is False
    assert result.error == "raw_secret_refused"
