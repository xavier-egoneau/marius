"""Wrapper minimaliste autour de l'API Bot Telegram.

Stdlib uniquement — aucune dépendance externe.
"""

from __future__ import annotations

import json
import re
from html import escape
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlencode
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


def get_file(token: str, file_id: str) -> dict[str, Any] | None:
    """Retourne les métadonnées d'un fichier Telegram."""
    resp = _get(token, "getFile", {"file_id": file_id})
    return resp.get("result") if resp else None


def download_file(token: str, file_path: str, *, max_bytes: int = 20 * 1024 * 1024) -> bytes | None:
    """Télécharge un fichier Telegram en mémoire, borné en taille."""
    safe_path = quote(file_path.lstrip("/"), safe="/")
    url = f"https://api.telegram.org/file/bot{token}/{safe_path}"
    try:
        with urlopen(url, timeout=_TIMEOUT) as resp:
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                return None
            data = resp.read(max_bytes + 1)
    except (URLError, OSError, ValueError):
        return None
    if len(data) > max_bytes:
        return None
    return data


def send_message(
    token: str,
    chat_id: int,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    """Envoie un message HTML. Retourne True si envoyé."""
    # Split si le texte dépasse la limite Telegram (4096 chars)
    chunks = _split_message(text)
    ok = True
    for index, chunk in enumerate(chunks):
        html, mode = _md_to_html(chunk)
        payload: dict[str, Any] = {
            "chat_id":    chat_id,
            "text":       html,
            "parse_mode": mode,
        }
        if reply_markup is not None and index == 0:
            payload["reply_markup"] = reply_markup
        resp = _post(token, "sendMessage", payload)
        if not resp:
            ok = False
    return ok


def answer_callback_query(token: str, callback_query_id: str, text: str = "") -> bool:
    """Répond à un clic de bouton inline Telegram."""
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return bool(_post(token, "answerCallbackQuery", payload))


def edit_message_text(
    token: str,
    chat_id: int,
    message_id: int,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    """Modifie un message Telegram existant."""
    html, mode = _md_to_html(text)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": html,
        "parse_mode": mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return bool(_post(token, "editMessageText", payload))


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
    # Code inline/blocs avant le reste pour éviter les conversions internes.
    blocks: list[str] = []
    inlines: list[str] = []

    def _save_block(m: re.Match) -> str:
        blocks.append(m.group(1))
        return f"\x00CODE{len(blocks) - 1}\x00"

    text = re.sub(r"```[^\n]*\n(.*?)```", _save_block, text, flags=re.DOTALL)

    def _save_inline(m: re.Match) -> str:
        inlines.append(m.group(1))
        return f"\x00INLINE{len(inlines) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", _save_inline, text)

    # Escape HTML hors code.
    text = _html_escape(text)

    # Headers → bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)

    # Italic (seul)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)

    # Restaure les blocs de code (avec escape interne)
    def _restore_block(m: re.Match) -> str:
        idx = int(m.group(1))
        code = _html_escape(blocks[idx])
        return f"<pre>{code}</pre>"

    text = re.sub(r"\x00CODE(\d+)\x00", _restore_block, text)

    def _restore_inline(m: re.Match) -> str:
        idx = int(m.group(1))
        return f"<code>{_html_escape(inlines[idx])}</code>"

    text = re.sub(r"\x00INLINE(\d+)\x00", _restore_inline, text)
    return text, "HTML"


def _split_message(text: str, limit: int = 4000) -> list[str]:
    """Découpe un texte en chunks ≤ limit caractères, sans casser les fences Markdown."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    in_code = False
    code_lang = ""

    def _open_fence() -> str:
        return f"```{code_lang}\n" if code_lang else "```\n"

    def _flush_preserving_code() -> None:
        nonlocal current, length
        if not current:
            return
        if in_code:
            current.append("```\n")
        chunks.append("".join(current))
        if in_code:
            current = [_open_fence()]
            length = len(current[0])
        else:
            current = []
            length = 0

    def _add_line(line: str) -> None:
        nonlocal current, length
        rest = line
        while rest:
            reserve = len("```\n") if in_code else 0
            if length + len(rest) + reserve <= limit:
                current.append(rest)
                length += len(rest)
                return
            if current:
                room = limit - length - reserve
                if room > 0:
                    current.append(rest[:room])
                    length += room
                    rest = rest[room:]
                _flush_preserving_code()
                continue
            max_len = max(1, limit - reserve)
            chunks.append(rest[:max_len])
            rest = rest[max_len:]

    for line in text.splitlines(keepends=True):
        fence = re.match(r"^\s*```([^\n`]*)\s*$", line.rstrip("\r\n"))
        _add_line(line)
        if fence:
            if in_code:
                in_code = False
                code_lang = ""
            else:
                in_code = True
                code_lang = fence.group(1).strip()
    if current:
        if in_code:
            current.append("```\n")
        chunks.append("".join(current))
    return chunks


def _html_escape(text: str) -> str:
    return escape(text, quote=True)
