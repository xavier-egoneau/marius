"""Poller Telegram — thread intégré dans le gateway.

Partage la session et l'orchestrateur du GatewayServer via le turn_lock.
Offset persisté sur disque pour reprendre après redémarrage.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .api import (
    answer_callback_query,
    download_file,
    edit_message_text,
    get_file,
    get_updates,
    send_chat_action,
    send_message,
    set_my_commands,
)
from .config import TelegramChannelConfig

_POLL_INTERVAL = 1.0   # secondes entre deux polls
_LONG_POLL_TIMEOUT = 10  # secondes de long polling
_MAX_MEDIA_BYTES = 20 * 1024 * 1024
_IMAGE_MIME_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}

# Commandes built-in (toujours enregistrées en premier)
_BUILTIN_COMMANDS: list[dict[str, str]] = [
    {"command": "start",  "description": "Démarrer"},
    {"command": "help",   "description": "Aide"},
    {"command": "new",    "description": "Nouvelle conversation"},
    {"command": "model",  "description": "Afficher ou changer le modèle"},
    {"command": "doctor", "description": "Diagnostic de l'installation"},
    {"command": "status", "description": "Statut du gateway"},
]

# Noms built-in réservés — les skill commands ne peuvent pas les écraser
_RESERVED = {c["command"] for c in _BUILTIN_COMMANDS}


def _build_command_list(skill_commands: dict) -> list[dict[str, str]]:
    """Fusionne built-ins + skill commands. Valide les noms (a-z0-9_)."""
    commands = list(_BUILTIN_COMMANDS)
    for name, sc in sorted(skill_commands.items()):
        if name in _RESERVED:
            continue
        # Telegram: nom 1-32 chars a-z0-9_
        safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]
        if not safe_name:
            continue
        desc = (sc.description or sc.name)[:256]
        commands.append({"command": safe_name, "description": desc})
    return commands[:100]  # limite Telegram


class TelegramPoller:
    """Thread de polling Telegram, intégré dans le GatewayServer."""

    def __init__(
        self,
        cfg: TelegramChannelConfig,
        gateway: Any,        # GatewayServer — évite import circulaire
        offset_path: Path,
    ) -> None:
        self._cfg    = cfg
        self._gw     = gateway
        self._offset_path = offset_path
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None
        self._turn_threads: set[threading.Thread] = set()
        self._turn_threads_lock = threading.Lock()

    # ── cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        skill_cmds = getattr(self._gw, "skill_commands", {})
        set_my_commands(self._cfg.token, _build_command_list(skill_cmds))
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="telegram-poller",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)
        with self._turn_threads_lock:
            turns = list(self._turn_threads)
        for thread in turns:
            thread.join(timeout=2)

    # ── boucle de polling ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.wait(_POLL_INTERVAL):
            try:
                self._poll_once()
            except Exception as exc:
                from marius.storage.log_store import log_event
                log_event("telegram_poll_error", {"error": str(exc)})

    def _poll_once(self) -> None:
        offset = self._read_offset()
        updates = get_updates(
            self._cfg.token,
            offset=offset,
            timeout=_LONG_POLL_TIMEOUT,
        )
        for update in updates:
            uid = int(update.get("update_id", 0))
            self._handle_update(update)
            self._write_offset(uid + 1)

    # ── dispatch ──────────────────────────────────────────────────────────────

    def _handle_update(self, update: dict) -> None:
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            self._handle_callback_query(callback_query)
            return

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = int(msg["chat"]["id"])
        user_id = int(msg.get("from", {}).get("id", 0))

        if not self._is_allowed(user_id, chat_id):
            return

        text = self._text_from_message(msg)
        if not text:
            return

        if text.startswith("/"):
            self._handle_command(chat_id, text)
        else:
            self._handle_message(chat_id, text)

    def _handle_callback_query(self, query: dict) -> None:
        query_id = str(query.get("id") or "")
        user_id = int(query.get("from", {}).get("id", 0))
        message = query.get("message") if isinstance(query.get("message"), dict) else {}
        chat_id = int(message.get("chat", {}).get("id", 0) or 0)
        message_id = int(message.get("message_id", 0) or 0)

        if not self._is_allowed(user_id, chat_id):
            if query_id:
                answer_callback_query(self._cfg.token, query_id, "Non autorisé.")
            return

        data = str(query.get("data") or "")
        parsed = _parse_permission_callback(data)
        if parsed is None:
            if query_id:
                answer_callback_query(self._cfg.token, query_id)
            return

        request_id, approved = parsed
        responder = getattr(self._gw, "respond_permission_request", None)
        ok = bool(responder(request_id, approved)) if callable(responder) else False
        if ok:
            status = "Permission autorisée." if approved else "Permission refusée."
        else:
            status = "Demande expirée ou déjà traitée."
        if query_id:
            answer_callback_query(self._cfg.token, query_id, status)
        if chat_id and message_id:
            edit_message_text(
                self._cfg.token,
                chat_id,
                message_id,
                f"{status}\n\nDemande : `{request_id}`",
                reply_markup={"inline_keyboard": []},
            )

    def _text_from_message(self, msg: dict) -> str:
        text = (msg.get("text") or "").strip()
        if text:
            return text
        caption = (msg.get("caption") or "").strip()
        attachment = self._download_image_attachment(msg)
        if not attachment:
            return caption
        marker = f"[fichier joint : {attachment}]"
        return f"{caption}\n\n{marker}".strip() if caption else marker

    def _download_image_attachment(self, msg: dict) -> str:
        media = _extract_image_media(msg)
        if media is None:
            return ""
        file_size = media.get("file_size")
        if isinstance(file_size, int) and file_size > _MAX_MEDIA_BYTES:
            return ""
        file_id = str(media.get("file_id") or "")
        if not file_id:
            return ""
        info = get_file(self._cfg.token, file_id)
        if not info:
            return ""
        file_path = str(info.get("file_path") or "")
        if not file_path:
            return ""
        data = download_file(self._cfg.token, file_path, max_bytes=_MAX_MEDIA_BYTES)
        if not data:
            return ""
        uploads_dir = _telegram_uploads_dir(self._gw)
        uploads_dir.mkdir(parents=True, exist_ok=True)
        suffix = _image_suffix(msg, file_path)
        filename = uploads_dir / f"{uuid.uuid4().hex[:8]}_telegram{suffix}"
        filename.write_bytes(data)
        return str(filename)

    def _is_allowed(self, user_id: int, chat_id: int) -> bool:
        if self._cfg.allowed_users and user_id not in self._cfg.allowed_users:
            return False
        if self._cfg.allowed_chats and chat_id not in self._cfg.allowed_chats:
            return False
        return True

    def _handle_command(self, chat_id: int, text: str) -> None:
        cmd = text.split()[0].lower().lstrip("/").split("@")[0]
        self._remember_chat(chat_id)

        if cmd == "start":
            send_message(self._cfg.token, chat_id,
                "Bonjour — je suis ton assistant Marius. Envoie-moi un message.")
            return

        if cmd == "help":
            lines = [f"/{c['command']} — {c['description']}" for c in _BUILTIN_COMMANDS]
            send_message(self._cfg.token, chat_id, "\n".join(lines))
            return

        if cmd == "new":
            self._gw.new_conversation(channel="telegram", reason="command")
            send_message(self._cfg.token, chat_id, "Nouvelle conversation démarrée.")
            return

        if cmd == "status":
            turns = len(self._gw.session.state.turns)
            send_message(self._cfg.token, chat_id,
                f"Gateway actif — {turns} tour(s) en session.")
            return

        if cmd == "model":
            self._handle_model(chat_id, text)
            return

        if cmd == "doctor":
            from marius.config.doctor import format_report_text, run_doctor
            agent = getattr(self._gw, "agent_name", None)
            sections = run_doctor(agent)
            report, _ = format_report_text(sections)
            send_message(self._cfg.token, chat_id, report)
            return

        # Commande inconnue → forwarder comme texte
        self._handle_message(chat_id, text)

    def _handle_model(self, chat_id: int, text: str) -> None:
        """Affiche les modèles disponibles ou en applique un directement."""
        parts = text.split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else ""

        models = getattr(self._gw, "list_models", lambda: [])()
        current = getattr(self._gw.entry, "model", "?")

        if not arg:
            if not models:
                send_message(self._cfg.token, chat_id,
                    f"Modèle actuel : `{current}`\n(liste indisponible)")
                return
            lines = [f"Modèle actuel : `{current}`\n"]
            for i, m in enumerate(models, 1):
                marker = "✓" if m == current else " "
                lines.append(f"{marker} `{i}. {m}`")
            lines.append("\n`/model <nom>` ou `/model <numéro>`")
            send_message(self._cfg.token, chat_id, "\n".join(lines))
            return

        # Résolution par numéro
        target = arg
        if arg.isdigit() and models:
            idx = int(arg) - 1
            if 0 <= idx < len(models):
                target = models[idx]
            else:
                send_message(self._cfg.token, chat_id, f"Numéro invalide : {arg}")
                return

        if target == current:
            send_message(self._cfg.token, chat_id, f"Déjà sur `{current}`.")
            return

        ok = getattr(self._gw, "set_model", lambda m: False)(target)
        if ok:
            send_message(self._cfg.token, chat_id, f"Modèle → `{target}`")
        else:
            send_message(self._cfg.token, chat_id, "Échec du changement de modèle.")

    def _handle_message(self, chat_id: int, text: str) -> None:
        # Mémorise le chat_id pour les notifications non sollicitées
        self._remember_chat(chat_id)

        if hasattr(self._gw, "_turn_lock"):
            thread = threading.Thread(
                target=self._run_message_turn,
                args=(chat_id, text),
                daemon=True,
                name="telegram-turn",
            )
            with self._turn_threads_lock:
                self._turn_threads.add(thread)
            thread.start()
            return

        self._run_message_turn(chat_id, text)

    def _run_message_turn(self, chat_id: int, text: str) -> None:
        # Typing indicator
        stop_typing = _start_typing(self._cfg.token, chat_id)
        response = ""
        try:
            response = self._gw.run_turn_for_telegram(text)
        finally:
            stop_typing()
            current = threading.current_thread()
            with self._turn_threads_lock:
                self._turn_threads.discard(current)

        if response:
            send_message(self._cfg.token, chat_id, response)

    def _remember_chat(self, chat_id: int) -> None:
        self._gw.telegram_chat_id = chat_id
        remember = getattr(self._gw, "remember_telegram_chat_id", None)
        if callable(remember):
            remember(chat_id)

    # ── offset ────────────────────────────────────────────────────────────────

    def _read_offset(self) -> int | None:
        try:
            return int(self._offset_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _write_offset(self, offset: int) -> None:
        try:
            self._offset_path.parent.mkdir(parents=True, exist_ok=True)
            self._offset_path.write_text(str(offset), encoding="utf-8")
        except OSError:
            pass


# ── typing indicator ──────────────────────────────────────────────────────────


def _start_typing(token: str, chat_id: int):
    """Lance le typing indicator en boucle. Retourne une fonction stop."""
    stop = threading.Event()
    send_chat_action(token, chat_id)  # immédiatement

    def _loop() -> None:
        while not stop.wait(4.0):
            send_chat_action(token, chat_id)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return stop.set


def _extract_image_media(msg: dict) -> dict[str, Any] | None:
    photos = msg.get("photo")
    if isinstance(photos, list) and photos:
        candidates = [p for p in photos if isinstance(p, dict) and p.get("file_id")]
        if candidates:
            return max(candidates, key=lambda p: int(p.get("file_size") or 0))
    document = msg.get("document")
    if isinstance(document, dict) and str(document.get("mime_type") or "").startswith("image/"):
        return document
    return None


def _parse_permission_callback(data: str) -> tuple[str, bool] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "perm":
        return None
    request_id = parts[1].strip()
    action = parts[2].strip().lower()
    if not request_id:
        return None
    if action == "allow":
        return request_id, True
    if action == "deny":
        return request_id, False
    return None


def _image_suffix(msg: dict, file_path: str) -> str:
    document = msg.get("document")
    if isinstance(document, dict):
        name = str(document.get("file_name") or "")
        suffix = Path(name).suffix.lower()
        if suffix:
            return suffix
        mime_type = str(document.get("mime_type") or "")
        if mime_type in _IMAGE_MIME_EXT:
            return _IMAGE_MIME_EXT[mime_type]
    suffix = Path(file_path).suffix.lower()
    return suffix if suffix else ".jpg"


def _telegram_uploads_dir(gateway: Any) -> Path:
    workspace = getattr(gateway, "workspace", None)
    if workspace:
        return Path(workspace).expanduser() / "uploads" / "telegram"
    agent_name = str(getattr(gateway, "agent_name", "main") or "main")
    return Path.home() / ".marius" / "workspace" / agent_name / "uploads" / "telegram"
