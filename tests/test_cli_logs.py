from __future__ import annotations

from marius.cli import _format_log_data, _short_time


def test_short_time_extracts_iso_time() -> None:
    assert _short_time("2026-05-09T12:34:56.123+00:00") == "12:34:56"


def test_format_log_data_prefers_useful_fields() -> None:
    rendered = _format_log_data({
        "provider": "chatgpt",
        "model": "gpt-5.4",
        "user_preview": "hey",
        "ignored": "nope",
    })

    assert "provider=chatgpt" in rendered
    assert "model=gpt-5.4" in rendered
    assert "user_preview=hey" in rendered
    assert "ignored" not in rendered
