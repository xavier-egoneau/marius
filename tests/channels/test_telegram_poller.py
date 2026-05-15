"""Tests du dispatcher de commandes Telegram.

On teste _handle_command et _is_allowed en isolation :
- send_message est mocké → pas d'appel réseau
- Le gateway est un SimpleNamespace → pas de GatewayServer réel
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from marius.channels.telegram.config import TelegramChannelConfig
from marius.channels.telegram.poller import TelegramPoller, _build_command_list


TOKEN = "test-token"
CHAT  = 100
USER  = 42


def _cfg(**kwargs) -> TelegramChannelConfig:
    defaults = dict(token=TOKEN, agent_name="main", allowed_users=[], allowed_chats=[])
    defaults.update(kwargs)
    return TelegramChannelConfig(**defaults)


def _gw(**kwargs) -> SimpleNamespace:
    defaults = dict(
        session=SimpleNamespace(state=SimpleNamespace(turns=[])),
        agent_name="main",
        skill_commands={},
        telegram_chat_id=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _poller(cfg=None, gw=None, tmp_path: Path | None = None) -> TelegramPoller:
    return TelegramPoller(
        cfg=cfg or _cfg(),
        gateway=gw or _gw(),
        offset_path=Path("/tmp/test_offset.txt"),
    )


# ── _is_allowed ───────────────────────────────────────────────────────────────


def test_all_users_allowed_when_list_empty() -> None:
    p = _poller(_cfg(allowed_users=[]))
    assert p._is_allowed(user_id=999, chat_id=CHAT) is True


def test_user_blocked_when_not_in_list() -> None:
    p = _poller(_cfg(allowed_users=[1, 2, 3]))
    assert p._is_allowed(user_id=999, chat_id=CHAT) is False


def test_user_allowed_when_in_list() -> None:
    p = _poller(_cfg(allowed_users=[USER]))
    assert p._is_allowed(user_id=USER, chat_id=CHAT) is True


# ── /start ────────────────────────────────────────────────────────────────────


def test_start_sends_welcome() -> None:
    gw = _gw()
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message") as mock_send:
        p._handle_command(CHAT, "/start")
    mock_send.assert_called_once()
    _, chat_id, text = mock_send.call_args.args
    assert chat_id == CHAT
    assert "Marius" in text or "assistant" in text.lower()
    assert gw.telegram_chat_id == CHAT


# ── /help ─────────────────────────────────────────────────────────────────────


def test_help_sends_command_list() -> None:
    p = _poller()
    with patch("marius.channels.telegram.poller.send_message") as mock_send:
        p._handle_command(CHAT, "/help")
    mock_send.assert_called_once()
    _, _, text = mock_send.call_args.args
    assert "/start" in text
    assert "/status" in text


# ── /new ─────────────────────────────────────────────────────────────────────


def test_new_calls_gateway_new_conversation() -> None:
    gw = _gw()
    gw.new_conversation = MagicMock()
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message"):
        p._handle_command(CHAT, "/new")
    gw.new_conversation.assert_called_once()


# ── /status ───────────────────────────────────────────────────────────────────


def test_status_reports_turn_count() -> None:
    gw = _gw()
    gw.session.state.turns = [object(), object()]   # 2 tours
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message") as mock_send:
        p._handle_command(CHAT, "/status")
    _, _, text = mock_send.call_args.args
    assert "2" in text


# ── /model ────────────────────────────────────────────────────────────────────


def test_model_lists_available_models() -> None:
    gw = _gw()
    gw.list_models = MagicMock(return_value=["gpt-4o", "gpt-4-turbo"])
    gw.entry = SimpleNamespace(model="gpt-4o")
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message") as mock_send:
        p._handle_command(CHAT, "/model")
    _, _, text = mock_send.call_args.args
    assert "gpt-4o" in text
    assert "gpt-4-turbo" in text


def test_model_switches_by_name() -> None:
    gw = _gw()
    gw.list_models = MagicMock(return_value=["gpt-4o", "gpt-4-turbo"])
    gw.entry = SimpleNamespace(model="gpt-4o")
    gw.set_model = MagicMock(return_value=True)
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message") as mock_send:
        p._handle_command(CHAT, "/model gpt-4-turbo")
    gw.set_model.assert_called_once_with("gpt-4-turbo")


def test_model_switches_by_number() -> None:
    gw = _gw()
    gw.list_models = MagicMock(return_value=["gpt-4o", "gpt-4-turbo"])
    gw.entry = SimpleNamespace(model="gpt-4o")
    gw.set_model = MagicMock(return_value=True)
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message"):
        p._handle_command(CHAT, "/model 2")
    gw.set_model.assert_called_once_with("gpt-4-turbo")


def test_model_noop_if_already_current() -> None:
    gw = _gw()
    gw.list_models = MagicMock(return_value=["gpt-4o"])
    gw.entry = SimpleNamespace(model="gpt-4o")
    gw.set_model = MagicMock()
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message") as mock_send:
        p._handle_command(CHAT, "/model gpt-4o")
    gw.set_model.assert_not_called()
    _, _, text = mock_send.call_args.args
    assert "Déjà" in text


# ── /doctor ───────────────────────────────────────────────────────────────────


def test_doctor_sends_report() -> None:
    p = _poller()
    fake_sections: list = []
    with (
        patch("marius.channels.telegram.poller.send_message") as mock_send,
        patch("marius.config.doctor.run_doctor", return_value=fake_sections),
        patch("marius.config.doctor.format_report_text", return_value=("rapport ok", 0)),
    ):
        p._handle_command(CHAT, "/doctor")
    mock_send.assert_called_once()
    _, _, text = mock_send.call_args.args
    assert text == "rapport ok"


# ── commande inconnue → forwarded comme message ───────────────────────────────


def test_unknown_command_forwarded_as_message() -> None:
    gw = _gw()
    gw.run_turn_for_telegram = MagicMock(return_value="réponse")
    gw.skill_commands = {}
    p = _poller(gw=gw)
    with patch("marius.channels.telegram.poller.send_message"):
        p._handle_command(CHAT, "/commande_inconnue")
    gw.run_turn_for_telegram.assert_called_once_with("/commande_inconnue")


def test_photo_message_is_downloaded_and_forwarded(tmp_path: Path) -> None:
    gw = _gw(workspace=tmp_path, run_turn_for_telegram=MagicMock(return_value="vu"))
    p = _poller(gw=gw)
    update = {
        "update_id": 1,
        "message": {
            "chat": {"id": CHAT},
            "from": {"id": USER},
            "caption": "regarde ça",
            "photo": [
                {"file_id": "small", "file_size": 10},
                {"file_id": "large", "file_size": 20},
            ],
        },
    }
    with (
        patch("marius.channels.telegram.poller.get_file", return_value={"file_path": "photos/file_1.jpg"}) as mock_get,
        patch("marius.channels.telegram.poller.download_file", return_value=b"jpg-bytes") as mock_download,
        patch("marius.channels.telegram.poller.send_chat_action"),
        patch("marius.channels.telegram.poller.send_message"),
    ):
        p._handle_update(update)

    mock_get.assert_called_once_with(TOKEN, "large")
    mock_download.assert_called_once_with(TOKEN, "photos/file_1.jpg", max_bytes=20 * 1024 * 1024)
    forwarded = gw.run_turn_for_telegram.call_args.args[0]
    assert forwarded.startswith("regarde ça")
    assert "[fichier joint : " in forwarded
    path = forwarded.split("[fichier joint : ", 1)[1].split("]", 1)[0]
    assert Path(path).read_bytes() == b"jpg-bytes"
    assert Path(path).parent == tmp_path / "uploads" / "telegram"


def test_image_document_message_is_downloaded_and_forwarded(tmp_path: Path) -> None:
    gw = _gw(workspace=tmp_path, run_turn_for_telegram=MagicMock(return_value="vu"))
    p = _poller(gw=gw)
    update = {
        "update_id": 1,
        "message": {
            "chat": {"id": CHAT},
            "from": {"id": USER},
            "document": {
                "file_id": "doc-image",
                "file_size": 12,
                "file_name": "capture.png",
                "mime_type": "image/png",
            },
        },
    }
    with (
        patch("marius.channels.telegram.poller.get_file", return_value={"file_path": "documents/capture"}),
        patch("marius.channels.telegram.poller.download_file", return_value=b"png-bytes"),
        patch("marius.channels.telegram.poller.send_chat_action"),
        patch("marius.channels.telegram.poller.send_message"),
    ):
        p._handle_update(update)

    forwarded = gw.run_turn_for_telegram.call_args.args[0]
    path = forwarded.split("[fichier joint : ", 1)[1].split("]", 1)[0]
    assert Path(path).suffix == ".png"
    assert Path(path).read_bytes() == b"png-bytes"


# ── _build_command_list ───────────────────────────────────────────────────────


def test_build_command_list_includes_builtins() -> None:
    cmds = _build_command_list({})
    names = {c["command"] for c in cmds}
    assert {"start", "help", "new", "status"} <= names
    assert "daily" not in names


def test_build_command_list_skill_commands_appended() -> None:
    from marius.kernel.skills import SkillCommand
    skill_cmds = {
        "plan": SkillCommand(
            name="plan",
            description="Planifier",
            skill_name="dev",
            prompt="",
        )
    }
    cmds = _build_command_list(skill_cmds)
    names = {c["command"] for c in cmds}
    assert "plan" in names


def test_build_command_list_reserved_names_not_overridden() -> None:
    from marius.kernel.skills import SkillCommand
    skill_cmds = {
        "help": SkillCommand(
            name="help",
            description="Aide skill (doit être ignoré)",
            skill_name="dev",
            prompt="",
        )
    }
    cmds = _build_command_list(skill_cmds)
    help_entries = [c for c in cmds if c["command"] == "help"]
    assert len(help_entries) == 1
    assert help_entries[0]["description"] == "Aide"   # built-in, pas le skill
