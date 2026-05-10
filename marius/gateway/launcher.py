"""Démarrage et arrêt du gateway Marius."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from .protocol import PingEvent, decode, encode
from .workspace import pid_path, socket_path

_STARTUP_TIMEOUT = 8.0   # secondes max pour que le socket apparaisse
_PING_TIMEOUT    = 2.0   # secondes pour le ping


def is_running(agent_name: str) -> bool:
    """Vérifie si le gateway répond au ping."""
    return _ping(agent_name)


def start(agent_name: str, *, web_port: int = 0) -> bool:
    """Lance le gateway en arrière-plan. Retourne True si démarré ou déjà actif."""
    if is_running(agent_name):
        return True

    # Nettoie un socket fantôme
    sp = socket_path(agent_name)
    if sp.exists():
        sp.unlink()

    cmd = [sys.executable, "-m", "marius.gateway", "--agent", agent_name]
    if web_port > 0:
        cmd += ["--web-port", str(web_port)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Attend l'apparition du socket
    deadline = time.monotonic() + _STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if sp.exists() and _ping(agent_name):
            return True
        time.sleep(0.1)

    # Timeout — tue le processus s'il est encore en vie
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    return False


def stop(agent_name: str) -> bool:
    """Arrête le gateway via SIGTERM. Retourne True si le processus existait."""
    pp = pid_path(agent_name)
    if not pp.exists():
        return False
    try:
        pid = int(pp.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
        # Attend disparition du socket (max 3s)
        deadline = time.monotonic() + 3.0
        sp = socket_path(agent_name)
        while time.monotonic() < deadline:
            if not sp.exists():
                return True
            time.sleep(0.1)
        return True
    except (ValueError, ProcessLookupError, OSError):
        return False


def _ping(agent_name: str) -> bool:
    """Envoie un ping au gateway. Retourne True si pong reçu."""
    sp = socket_path(agent_name)
    if not sp.exists():
        return False
    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(_PING_TIMEOUT)
        conn.connect(str(sp))
        # Read welcome
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(512)
            if not chunk:
                break
            buf += chunk
        # Send ping
        conn.sendall(encode(PingEvent()))
        # Read pong
        buf2 = b""
        while b"\n" not in buf2:
            chunk = conn.recv(512)
            if not chunk:
                break
            buf2 += chunk
        line = buf2.decode(errors="replace").split("\n")[0]
        event = decode(line)
        return event.get("type") == "pong"
    except (OSError, ValueError):
        return False
    finally:
        try:
            conn.close()
        except OSError:
            pass
