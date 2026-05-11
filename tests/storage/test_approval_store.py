from __future__ import annotations

from marius.storage.approval_store import ApprovalStore


def test_approval_store_records_sanitized_arguments(tmp_path):
    store = ApprovalStore(path=tmp_path / "approvals.json")

    record = store.record(
        fingerprint="abc",
        tool_name="host_telegram_configure",
        arguments={"token": "secret", "path": "/tmp/x"},
        reason="test",
        mode="limited",
        cwd="/tmp",
        approved=True,
    )

    assert record.arguments["token"] == "<redacted>"
    assert record.arguments["path"] == "/tmp/x"


def test_approval_store_lookup_uses_remembered_decision(tmp_path):
    store = ApprovalStore(path=tmp_path / "approvals.json")
    record = store.record(
        fingerprint="abc",
        tool_name="write_file",
        arguments={"path": "/tmp/x"},
        reason="outside",
        mode="limited",
        cwd="/tmp/project",
        approved=True,
    )

    assert store.lookup("abc") is None
    store.decide(record.id, approved=False, remember=True)

    assert store.lookup("abc") is False


def test_approval_store_forget_disables_remembered_decision(tmp_path):
    store = ApprovalStore(path=tmp_path / "approvals.json")
    record = store.record(
        fingerprint="abc",
        tool_name="write_file",
        arguments={},
        reason="outside",
        mode="limited",
        cwd="/tmp/project",
        approved=True,
        remembered=True,
    )

    store.forget(record.id)

    assert store.lookup("abc") is None
