"""Poller Telegram — thread intégré dans le gateway.

Partage la session et l'orchestrateur du GatewayServer via le turn_lock.
Offset persisté sur disque pour reprendre après redémarrage.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .api import get_updates, send_chat_action, send_message, set_my_commands
from .config import TelegramChannelConfig

_POLL_INTERVAL = 1.0   # secondes entre deux polls
_LONG_POLL_TIMEOUT = 10  # secondes de long polling

# Commandes built-in (toujours enregistrées en premier)
_BUILTIN_COMMANDS: list[dict[str, str]] = [
    {"command": "start",  "description": "Démarrer"},
    {"command": "help",   "description": "Aide"},
    {"command": "new",    "description": "Nouvelle conversation"},
    {"command": "daily",  "description": "Briefing du jour"},
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

    # ── boucle de polling ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.wait(_POLL_INTERVAL):
            try:
                self._poll_once()
            except Exception:
                pass

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
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = int(msg["chat"]["id"])
        user_id = int(msg.get("from", {}).get("id", 0))
        text    = (msg.get("text") or "").strip()
        if not text:
            return

        if not self._is_allowed(user_id, chat_id):
            return

        if text.startswith("/"):
            self._handle_command(chat_id, text)
        else:
            self._handle_message(chat_id, text)

    def _is_allowed(self, user_id: int, chat_id: int) -> bool:
        if self._cfg.allowed_users and user_id not in self._cfg.allowed_users:
            return False
        if self._cfg.allowed_chats and chat_id not in self._cfg.allowed_chats:
            return False
        return True

    def _handle_command(self, chat_id: int, text: str) -> None:
        cmd = text.split()[0].lower().lstrip("/").split("@")[0]

        if cmd == "start":
            send_message(self._cfg.token, chat_id,
                "Bonjour — je suis ton assistant Marius. Envoie-moi un message.")
            return

        if cmd == "help":
            lines = [f"/{c['command']} — {c['description']}" for c in _BUILTIN_COMMANDS]
            send_message(self._cfg.token, chat_id, "\n".join(lines))
            return

        if cmd == "new":
            self._gw.new_conversation()
            send_message(self._cfg.token, chat_id, "Nouvelle conversation démarrée.")
            return

        if cmd == "daily":
            self._handle_message(chat_id, "/daily")
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
        # Mémorise le chat_id pour les pushs non-sollicités (daily)
        self._gw.telegram_chat_id = chat_id

        # Typing indicator
        stop_typing = _start_typing(self._cfg.token, chat_id)
        response = ""
        try:
            response = self._gw.run_turn_for_telegram(text)
        finally:
            stop_typing()

        if response:
            send_message(self._cfg.token, chat_id, response)

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
