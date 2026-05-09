"""Wrapper minimaliste autour de l'API Bot Telegram.

Stdlib uniquement — aucune dépendance externe.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 12  # secondes pour les appels courts


# ── requêtes ─────────────────────────────────────────────────────────────────


def _get(token: str, method: str, params: dict[str, Any] | None = None) -> Any:
    url = _BASE.format(token=token, method=method)
    if params:
        url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
    try:
        with urlopen(url, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return data if data.get("ok") else None
    except (URLError, json.JSONDecodeError, OSError):
        return None


def _post(token: str, method: str, payload: dict[str, Any]) -> Any:
    url = _BASE.format(token=token, method=method)
    body = json.dumps(payload).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return data if data.get("ok") else None
    except (URLError, json.JSONDecodeError, OSError):
        return None


# ── API publique ──────────────────────────────────────────────────────────────


def get_me(token: str) -> dict[str, Any] | None:
    """Retourne les infos du bot. Sert à valider le token."""
    resp = _get(token, "getMe")
    return resp.get("result") if resp else None


def get_updates(
    token: str,
    *,
    offset: int | None = None,
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """Long polling. Retourne la liste des updates."""
    resp = _get(token, "getUpdates", {"offset": offset, "timeout": timeout})
    return resp.get("result", []) if resp else []


def send_message(token: str, chat_id: int, text: str) -> bool:
    """Envoie un message HTML. Retourne True si envoyé."""
    # Split si le texte dépasse la limite Telegram (4096 chars)
    chunks = _split_message(text)
    ok = True
    for chunk in chunks:
        html, mode = _md_to_html(chunk)
        resp = _post(token, "sendMessage", {
            "chat_id":    chat_id,
            "text":       html,
            "parse_mode": mode,
        })
        if not resp:
            ok = False
    return ok


def send_chat_action(token: str, chat_id: int, action: str = "typing") -> None:
    """Envoie une action (typing…). Silencieux en cas d'erreur."""
    _post(token, "sendChatAction", {"chat_id": chat_id, "action": action})


def set_my_commands(token: str, commands: list[dict[str, str]]) -> bool:
    """Enregistre les commandes affichées dans le menu Telegram."""
    resp = _post(token, "setMyCommands", {"commands": commands})
    return bool(resp)


# ── formatage ─────────────────────────────────────────────────────────────────


def _md_to_html(text: str) -> tuple[str, str]:
    """Convertit Markdown basique en HTML Telegram. Retourne (texte, parse_mode)."""
    # Code blocks avant le reste (évite les conversions internes)
    blocks: list[str] = []

    def _save_block(m: re.Match) -> str:
        blocks.append(m.group(1))
        return f"\x00CODE{len(blocks) - 1}\x00"

    text = re.sub(r"```[^\n]*\n(.*?)```", _save_block, text, flags=re.DOTALL)

    # Escape HTML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Restaure les blocs de code (avec escape interne)
    def _restore_block(m: re.Match) -> str:
        idx = int(m.group(1))
        code = blocks[idx].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<pre>{code}</pre>"

    text = re.sub(r"\x00CODE(\d+)\x00", _restore_block, text)

    # Inline code
    text = re.sub(r"`([^`\n]+)`", lambda m: f"<code>{m.group(1)}</code>", text)

    # Headers → bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)

    # Italic (seul)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)

    return text, "HTML"


def _split_message(text: str, limit: int = 4000) -> list[str]:
    """Découpe un texte en chunks ≤ limit caractères, sur des lignes entières si possible."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for line in text.splitlines(keepends=True):
        # Ligne seule trop longue : forcer la coupure en sous-chunks
        if not current and len(line) > limit:
            for i in range(0, len(line), limit):
                chunks.append(line[i:i + limit])
            continue
        if length + len(line) > limit and current:
            chunks.append("".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line)
    if current:
        chunks.append("".join(current))
    return chunks
