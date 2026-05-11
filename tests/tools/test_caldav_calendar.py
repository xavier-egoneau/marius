from __future__ import annotations

import shutil

from marius.tools import caldav_calendar
from marius.tools.caldav_calendar import CALDAV_AGENDA, CALDAV_DOCTOR, CALDAV_MAINTENANCE


def test_caldav_doctor_reports_missing_dependencies(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(caldav_calendar, "_VDIRSYNCER_CONFIG", tmp_path / "vdirsyncer")
    monkeypatch.setattr(caldav_calendar, "_KHAL_CONFIG", tmp_path / "khal")

    result = CALDAV_DOCTOR.handler({})

    assert result.ok is True
    assert result.data["ready"] is False
    assert "missing binary" in result.summary


def test_caldav_agenda_returns_events(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    vdir = tmp_path / "vdirsyncer"
    khal = tmp_path / "khal"
    vdir.write_text("ok", encoding="utf-8")
    khal.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(caldav_calendar, "_VDIRSYNCER_CONFIG", vdir)
    monkeypatch.setattr(caldav_calendar, "_KHAL_CONFIG", khal)

    def fake_run(command, *, timeout):
        if command[:2] == ["vdirsyncer", "sync"]:
            return {"returncode": 0, "stdout": "", "stderr": ""}
        return {"returncode": 0, "stdout": "2026-05-11 10:00 Standup\n", "stderr": ""}

    monkeypatch.setattr(caldav_calendar, "_run", fake_run)

    result = CALDAV_AGENDA.handler({"days": 2})

    assert result.ok is True
    assert result.data["events"] == ["2026-05-11 10:00 Standup"]


def test_caldav_maintenance_validates_operation():
    result = CALDAV_MAINTENANCE.handler({"operation": "delete-world"})

    assert result.ok is False
    assert result.error == "invalid_operation"
