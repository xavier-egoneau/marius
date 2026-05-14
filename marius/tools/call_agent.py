"""Outil call_agent — déléguer une tâche à un agent nommé via son gateway.

Permet à l'agent orchestrateur de router une tâche vers un agent persistant
(ex. "codeur") et de récupérer sa réponse complète.

Contraintes :
  - L'agent cible doit avoir un gateway actif (socket Unix existant)
  - Timeout par défaut 120s, max 300s
  - Les permission_request de l'agent cible sont auto-refusées
    (pas d'interactivité dans un appel outil)
"""

from __future__ import annotations

import json
import socket
from dataclasses import asdict
from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 300


def make_call_agent_tool() -> ToolEntry:
    """Fabrique l'outil call_agent."""

    def _handler(arguments: dict[str, Any]) -> ToolResult:
        from marius.gateway.protocol import InputEvent, PermissionResponseEvent, encode
        from marius.gateway.workspace import socket_path

        agent_name = str(arguments.get("agent", "")).strip()
        task = str(arguments.get("task", "")).strip()
        timeout = min(int(arguments.get("timeout_seconds", _DEFAULT_TIMEOUT)), _MAX_TIMEOUT)

        if not agent_name:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Argument `agent` manquant.",
                error="missing_arg:agent",
            )
        if not task:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Argument `task` manquant.",
                error="missing_arg:task",
            )

        sock_path = socket_path(agent_name)
        if not sock_path.exists():
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Gateway de l'agent '{agent_name}' non actif. Lancez son gateway d'abord.",
                error=f"gateway_not_running:{agent_name}",
            )

        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(timeout)
            conn.connect(str(sock_path))
        except OSError as exc:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Connexion au gateway '{agent_name}' impossible : {exc}",
                error=f"connection_failed:{exc}",
            )

        buf = ""
        text_parts: list[str] = []
        error_msg: str | None = None

        def _readline() -> str | None:
            nonlocal buf
            while "\n" not in buf:
                try:
                    chunk = conn.recv(4096)
                except (OSError, socket.timeout):
                    return None
                if not chunk:
                    return None
                buf += chunk.decode(errors="replace")
            line, buf = buf.split("\n", 1)
            return line

        def _send(event: Any) -> None:
            try:
                conn.sendall(encode(event))
            except OSError:
                pass

        try:
            # Lire le WelcomeEvent
            line = _readline()
            if line is None:
                return ToolResult(
                    tool_call_id="",
                    ok=False,
                    summary=f"Gateway '{agent_name}' a fermé la connexion prématurément.",
                    error="premature_close",
                )
            welcome = json.loads(line)
            if welcome.get("type") != "welcome":
                return ToolResult(
                    tool_call_id="",
                    ok=False,
                    summary=f"Handshake inattendu depuis '{agent_name}'.",
                    error="bad_handshake",
                )

            # Envoyer la tâche
            _send(InputEvent(text=task))

            # Collecter les événements jusqu'à DoneEvent ou ErrorEvent
            while True:
                line = _readline()
                if line is None:
                    break
                event = json.loads(line)
                etype = event.get("type")

                if etype == "delta":
                    text_parts.append(event.get("text", ""))

                elif etype == "permission_request":
                    # Auto-refus : pas d'interactivité dans un appel outil
                    _send(PermissionResponseEvent(
                        request_id=event.get("request_id", ""),
                        approved=False,
                    ))

                elif etype == "error":
                    error_msg = event.get("message", "Erreur inconnue.")
                    break

                elif etype in ("done", "status"):
                    break

        except socket.timeout:
            error_msg = f"Timeout ({timeout}s) en attendant la réponse de '{agent_name}'."
        finally:
            try:
                conn.close()
            except OSError:
                pass

        full_response = "".join(text_parts).strip()

        if error_msg and not full_response:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Erreur de l'agent '{agent_name}' : {error_msg}",
                error=error_msg,
            )

        if not full_response:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Aucune réponse reçue de l'agent '{agent_name}'.",
                error="empty_response",
            )

        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Réponse de '{agent_name}' reçue ({len(full_response)} caractères).",
            data={"agent": agent_name, "response": full_response},
        )

    return ToolEntry(
        definition=ToolDefinition(
            name="call_agent",
            description=(
                "Déléguer une tâche à un agent nommé persistant via son gateway. "
                "L'agent cible doit avoir son gateway actif. "
                "Utilise pour sous-traiter une tâche spécialisée à un agent expert "
                "(ex. 'codeur', 'analyste') et récupérer sa réponse complète. "
                "Différent de spawn_agent : route vers un agent existant et persistant, "
                "ne crée pas d'agent éphémère."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Nom de l'agent cible (doit avoir un gateway actif).",
                    },
                    "task": {
                        "type": "string",
                        "description": "Description complète de la tâche à confier à l'agent.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": (
                            f"Timeout en secondes (défaut {_DEFAULT_TIMEOUT}, max {_MAX_TIMEOUT}). "
                            "Augmenter pour les tâches longues."
                        ),
                    },
                },
                "required": ["agent", "task"],
            },
        ),
        handler=_handler,
    )
