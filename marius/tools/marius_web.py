"""Outil de contrôle local pour ouvrir l'interface web Marius."""

from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_DEFAULT_PORT = 8765
_STARTUP_TIMEOUT_SECONDS = 8.0


def _open_marius_web(arguments: dict[str, Any]) -> ToolResult:
    port = _parse_port(arguments.get("port", _DEFAULT_PORT))
    if port is None:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary="Port invalide. Utilise un entier entre 1 et 65535.",
            error="invalid_port",
        )

    agent_name = str(arguments.get("agent") or "").strip() or _default_agent_name()
    if not agent_name:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary="Aucun agent configuré. Lance `marius setup` d'abord.",
            error="missing_agent",
        )

    open_browser = bool(arguments.get("open_browser", True))
    url = f"http://localhost:{port}"

    if _web_is_available(port):
        browser_opened = _open_browser(url) if open_browser else False
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Interface web déjà disponible : {url}",
            data={
                "agent": agent_name,
                "port": port,
                "url": url,
                "already_running": True,
                "browser_opened": browser_opened,
            },
        )

    from marius.gateway.launcher import is_running, start

    if not is_running(agent_name) and not start(agent_name):
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Impossible de démarrer le gateway pour l'agent `{agent_name}`.",
            error="gateway_start_failed",
            data={"agent": agent_name, "port": port, "url": url},
        )

    try:
        subprocess.Popen(
            _web_command(agent_name, port),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Impossible de lancer l'interface web : {exc}",
            error=str(exc),
            data={"agent": agent_name, "port": port, "url": url},
        )

    if not _wait_for_web(port):
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Le serveur web ne répond pas encore sur {url}.",
            error="web_start_timeout",
            data={"agent": agent_name, "port": port, "url": url},
        )

    browser_opened = _open_browser(url) if open_browser else False
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary=f"Interface web ouverte : {url}",
        data={
            "agent": agent_name,
            "port": port,
            "url": url,
            "already_running": False,
            "browser_opened": browser_opened,
        },
    )


def _default_agent_name() -> str:
    from marius.config.store import ConfigStore

    config = ConfigStore().load()
    return config.main_agent if config is not None else ""


def _parse_port(raw: Any) -> int | None:
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return None
    if port < 1 or port > 65535:
        return None
    return port


def _web_command(agent_name: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-c",
        "from marius.cli import main; main()",
        "web",
        "--agent",
        agent_name,
        "--port",
        str(port),
    ]


def _web_is_available(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
            return 200 <= int(response.status) < 500
    except (OSError, URLError, TimeoutError, ValueError):
        return False


def _wait_for_web(port: int) -> bool:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _web_is_available(port):
            return True
        time.sleep(0.1)
    return False


def _open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


OPEN_MARIUS_WEB = ToolEntry(
    definition=ToolDefinition(
        name="open_marius_web",
        description=(
            "Démarre l'interface web locale de Marius en arrière-plan et retourne son URL."
        ),
        parameters={
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Nom de l'agent à exposer (défaut : agent principal configuré).",
                },
                "port": {
                    "type": "integer",
                    "description": "Port HTTP local (défaut : 8765).",
                },
                "open_browser": {
                    "type": "boolean",
                    "description": "Ouvre aussi l'URL dans le navigateur local si possible.",
                },
            },
            "required": [],
        },
    ),
    handler=_open_marius_web,
)
