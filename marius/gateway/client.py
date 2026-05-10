"""Client gateway Marius — terminal Rich connecté au socket Unix."""

from __future__ import annotations

import random
import socket
import threading
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from .protocol import (
    CommandEvent, InputEvent, PermissionResponseEvent, PingEvent,
    decode, encode,
)
from .workspace import socket_path

_THEME = Theme({
    "prompt":      "bold white",
    "tool.bullet": "bold dim",
    "tool.verb":   "bold",
    "tool.target": "dim",
    "tool.ok":     "dim green",
    "tool.err":    "dim red",
    "error":       "bold red",
    "info.key":    "dim",
    "info.val":    "white",
    "cmd.name":    "bold color(208)",
    "cmd.desc":    "dim",
})

_console = Console(theme=_THEME, highlight=False)

_SPINNER_WORDS = [
    "Réflexion", "Analyse", "Traitement",
    "Exploration", "Synthèse", "Recherche",
]

_TOOL_VERBS: dict[str, str] = {
    "read_file":  "Lecture",
    "list_dir":   "Exploration",
    "write_file": "Écriture",
    "run_bash":   "Exécution",
    "web_fetch":  "Fetch",
    "web_search": "Recherche web",
    "vision":     "Vision",
    "skill_view": "Skill",
    "open_marius_web": "Web",
}

_GATEWAY_COMMANDS: dict[str, str] = {
    "/stop":     "interrompre le tour en cours",
    "/new":      "nouvelle conversation",
    "/shutdown": "arrêter le gateway",
    "/help":     "afficher les commandes",
    "/exit":     "se déconnecter (gateway reste actif)",
}


class _LineReader:
    def __init__(self, conn: socket.socket) -> None:
        self._conn = conn
        self._buf = ""

    def readline(self) -> str | None:
        while "\n" not in self._buf:
            try:
                chunk = self._conn.recv(4096)
            except OSError:
                return None
            if not chunk:
                return None
            self._buf += chunk.decode(errors="replace")
        line, self._buf = self._buf.split("\n", 1)
        return line


def _send(conn: socket.socket, event: Any) -> None:
    try:
        conn.sendall(encode(event))
    except OSError:
        pass


def _recv_turn(reader: _LineReader, conn: socket.socket) -> None:
    """Reçoit et affiche les events d'un tour jusqu'à DoneEvent ou ErrorEvent."""
    word = random.choice(_SPINNER_WORDS)
    status = Status(f"[dim]{word}…[/]", spinner="dots", spinner_style="color(208)", console=_console)
    status.start()
    streaming_started = False

    while True:
        line = reader.readline()
        if line is None:
            status.stop()
            return

        event = decode(line)
        etype = event.get("type")

        if etype == "delta":
            if not streaming_started:
                status.stop()
                _console.print()
                streaming_started = True
            print(event.get("text", ""), end="", flush=True)

        elif etype == "tool_start":
            status.stop()
            streaming_started = False
            name = event.get("name", "")
            target = event.get("target", "")
            verb = _TOOL_VERBS.get(name, name)
            if target:
                _console.print(f"\n  [tool.bullet]●[/] [tool.verb]{verb}[/]  [tool.target]{target}[/]")
            else:
                _console.print(f"\n  [tool.bullet]●[/] [tool.verb]{verb}[/]")

        elif etype == "tool_result":
            ok = event.get("ok", True)
            style = "tool.ok" if ok else "tool.err"
            label = "ok" if ok else "erreur"
            _console.print(f"    [{style}]{label}[/]")

        elif etype == "permission_request":
            status.stop()
            req_id = event.get("request_id", "")
            tool_name = event.get("tool_name", "")
            reason = event.get("reason", "")
            _console.print(f"\n  [bold color(208)]Permission requise[/]  [dim]{tool_name}[/]")
            _console.print(f"  [dim]{reason}[/]")
            try:
                raw = _console.input("  Autoriser ? [[dim]o/N[/]]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                raw = "n"
            approved = raw in ("o", "oui", "y", "yes")
            if not approved:
                _console.print("  [dim]Refusé.[/]")
            _send(conn, PermissionResponseEvent(request_id=req_id, approved=approved))
            if not streaming_started:
                status.start()

        elif etype == "status":
            status.stop()
            _console.print(f"\n  [dim]{event.get('message', '')}[/]\n")
            return

        elif etype == "error":
            status.stop()
            _console.print(f"\n[error]  {event.get('message', 'Erreur inconnue.')}[/]\n")
            return

        elif etype == "done":
            status.stop()
            if streaming_started:
                _console.print("\n")
            return


def connect_and_run(agent_name: str) -> None:
    """Connecte au gateway de l'agent et lance la boucle interactive."""
    sock_path = socket_path(agent_name)
    if not sock_path.exists():
        _console.print(
            f"\n[bold color(208)]Gateway '{agent_name}' non actif.[/]\n"
            f"  Lancez [bold]marius gateway start --agent {agent_name}[/]\n"
        )
        return

    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(str(sock_path))
    except OSError as exc:
        _console.print(f"\n[error]Connexion impossible : {exc}[/]\n")
        return

    reader = _LineReader(conn)

    # Welcome
    line = reader.readline()
    if line is None:
        _console.print("\n[error]Gateway fermé prématurément.[/]\n")
        return

    welcome = decode(line)
    if welcome.get("type") != "welcome":
        _console.print("\n[error]Handshake inattendu.[/]\n")
        return

    model = welcome.get("model", "")
    provider = welcome.get("provider", "")
    loaded = welcome.get("loaded_context", [])
    context_label = " · ".join(loaded) if loaded else "(aucun)"

    info = Table.grid(padding=(0, 1))
    info.add_column(style="info.key", no_wrap=True)
    info.add_column(style="info.val", no_wrap=True)
    info.add_row("agent",    agent_name)
    info.add_row("provider", f"{provider} · {model}")
    info.add_row("contexte", context_label)
    info.add_row("mode",     "gateway (session persistante)")

    _console.print()
    _console.print(Panel(info, border_style="dim", padding=(1, 2)))
    _console.print("[dim]  /exit pour se déconnecter  ·  /shutdown pour arrêter le gateway[/]\n")

    try:
        while True:
            try:
                message = _console.input("[prompt]>[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                _console.print()
                break

            if not message:
                continue

            if message.startswith("/"):
                cmd = message.split()[0].lower()
                if cmd == "/exit":
                    break
                if cmd == "/shutdown":
                    _send(conn, CommandEvent(cmd="/shutdown"))
                    _console.print("\n  [dim]Gateway arrêté.[/]\n")
                    break
                if cmd == "/help":
                    _console.print()
                    t = Table.grid(padding=(0, 2))
                    t.add_column(style="cmd.name", no_wrap=True)
                    t.add_column(style="cmd.desc")
                    for name, desc in _GATEWAY_COMMANDS.items():
                        t.add_row(name, desc)
                    _console.print(t)
                    _console.print()
                    continue
                if cmd == "/stop":
                    _send(conn, CommandEvent(cmd="/stop"))
                    continue
                if cmd == "/new":
                    _send(conn, CommandEvent(cmd="/new"))
                    # Status response will be received in next recv_turn
                    _recv_turn(reader, conn)
                    continue
                _console.print(f"[dim]Commande inconnue : {cmd}. /help pour la liste.[/]\n")
                continue

            _send(conn, InputEvent(text=message))

            # Receive turn events — handle Ctrl-C as /stop
            try:
                _recv_turn(reader, conn)
            except KeyboardInterrupt:
                _send(conn, CommandEvent(cmd="/stop"))
                _recv_turn(reader, conn)

    finally:
        try:
            conn.close()
        except OSError:
            pass
