"""Garde de permissions — évalue allow/ask/deny avant chaque appel d'outil.

Brique standalone, aucune dépendance externe.
Inspiré de Maurice kernel/permissions.py, simplifié pour Marius.

Trois modes :
  safe    → lecture seule dans CWD, écriture sur demande, shell interdit
  limited → lecture + écriture dans CWD, shell autorisé, sortie CWD sur demande
  power   → tout autorisé (hormis chemins système)

Le callback on_ask est fourni par le REPL pour les décisions interactives.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ── chemins système jamais accessibles ───────────────────────────────────────

_SYSTEM_PREFIXES = (
    "/bin", "/sbin", "/lib", "/lib64", "/usr", "/etc",
    "/var", "/sys", "/proc", "/dev", "/run", "/boot",
    "/System", "/Library",                         # macOS
)

_SENSITIVE_PATTERNS = (
    "**/.env", "**/.env.*", "**/secrets/**",
    "**/.ssh/**", "**/.gnupg/**",
    str(Path.home() / ".marius" / "marius_providers.json"),
)

# ── commandes shell destructrices ─────────────────────────────────────────────

_DANGEROUS_SHELL_RE = re.compile(
    r"(rm\s+(-[a-z]*r[a-z]*f|--force|--recursive).*/"
    r"|dd\s+if="
    r"|mkfs"
    r"|fdisk"
    r"|shred"
    r"|:()\s*\{.*\|.*&.*\}"     # fork bomb
    r"|>\s*/dev/(s?d[a-z]|nvme)" # écriture directe disque
    r")",
    re.IGNORECASE,
)


# ── décision ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PermissionDecision:
    verdict: str        # "allow" | "ask" | "deny"
    reason: str = ""


_ALLOW = PermissionDecision("allow")
_DENY_SYSTEM = PermissionDecision("deny", "Chemin système — accès interdit.")
_DENY_SHELL  = PermissionDecision("deny", "Shell désactivé en mode safe.")
_DENY_WRITE  = PermissionDecision("deny", "Écriture hors CWD interdite en mode safe.")


# ── guard ─────────────────────────────────────────────────────────────────────

@dataclass
class PermissionGuard:
    """Évalue les appels d'outils avant exécution."""

    mode: str           # "safe" | "limited" | "power"
    cwd: Path
    on_ask: Callable[[str, dict, str], bool] | None = None

    # Cache des approbations de la session (fingerprint → bool)
    _approvals: dict[str, bool] = field(default_factory=dict, repr=False)

    def check(self, tool_name: str, arguments: dict) -> bool:
        """Retourne True si l'appel est autorisé, False sinon."""
        decision = self._evaluate(tool_name, arguments)

        if decision.verdict == "allow":
            return True
        if decision.verdict == "deny":
            return False

        # ask — vérifie le cache d'abord
        fp = _fingerprint(tool_name, arguments)
        if fp in self._approvals:
            return self._approvals[fp]

        if self.on_ask is not None:
            approved = self.on_ask(tool_name, arguments, decision.reason)
            self._approvals[fp] = approved
            return approved

        return False  # pas de callback → deny par défaut

    def _evaluate(self, tool_name: str, arguments: dict) -> PermissionDecision:
        if self.mode == "power":
            return self._check_invariants(tool_name, arguments)

        if tool_name in ("web_fetch", "web_search", "memory"):
            return _ALLOW

        if tool_name == "run_bash":
            return self._check_shell(arguments)

        if tool_name in ("read_file", "list_dir", "vision"):
            return self._check_read(arguments)

        if tool_name == "write_file":
            return self._check_write(arguments)

        return _ALLOW

    # ── checks par outil ─────────────────────────────────────────────────────

    def _check_invariants(self, tool_name: str, arguments: dict) -> PermissionDecision:
        """Vérifications communes à tous les modes (chemins système)."""
        path = _extract_path(arguments)
        if path and _is_system_path(path):
            return _DENY_SYSTEM
        if tool_name == "run_bash":
            cmd = arguments.get("command", "")
            if _DANGEROUS_SHELL_RE.search(cmd):
                return PermissionDecision("ask", f"Commande potentiellement destructrice :\n  {cmd}")
        return _ALLOW

    def _check_read(self, arguments: dict) -> PermissionDecision:
        path = _extract_path(arguments)
        if not path:
            return _ALLOW
        if _is_system_path(path):
            return _DENY_SYSTEM
        if _is_sensitive(path):
            return PermissionDecision("ask", f"Fichier sensible : {path}")
        if self.mode == "safe" and not _is_under(path, self.cwd):
            return PermissionDecision("ask", f"Lecture hors du projet ({path})")
        if self.mode == "limited" and not _is_under(path, self.cwd):
            return PermissionDecision("ask", f"Lecture hors du projet ({path})")
        return _ALLOW

    def _check_write(self, arguments: dict) -> PermissionDecision:
        path = _extract_path(arguments)
        if not path:
            return _ALLOW
        if _is_system_path(path):
            return _DENY_SYSTEM
        if _is_sensitive(path):
            return PermissionDecision("ask", f"Fichier sensible : {path}")
        if self.mode == "safe":
            if _is_under(path, self.cwd):
                return PermissionDecision("ask", f"Écriture dans le projet : {path}")
            return _DENY_WRITE
        if self.mode == "limited" and not _is_under(path, self.cwd):
            return PermissionDecision("ask", f"Écriture hors du projet ({path})")
        return _ALLOW

    def _check_shell(self, arguments: dict) -> PermissionDecision:
        if self.mode == "safe":
            return _DENY_SHELL
        cmd = arguments.get("command", "")
        if _DANGEROUS_SHELL_RE.search(cmd):
            return PermissionDecision("ask", f"Commande potentiellement destructrice :\n  {cmd}")
        return _ALLOW


# ── helpers ───────────────────────────────────────────────────────────────────


def _extract_path(arguments: dict) -> str | None:
    for key in ("path", "file_path", "directory", "dest", "destination"):
        val = arguments.get(key)
        if val and isinstance(val, str):
            return val
    return None


def _is_under(path: str, root: Path) -> bool:
    try:
        resolved = Path(path).expanduser().resolve()
        root_resolved = root.expanduser().resolve()
        resolved.relative_to(root_resolved)
        return True
    except ValueError:
        return False


def _is_system_path(path: str) -> bool:
    try:
        resolved = str(Path(path).expanduser().resolve())
    except (OSError, RuntimeError):
        return False
    return any(resolved.startswith(prefix) for prefix in _SYSTEM_PREFIXES)


def _is_sensitive(path: str) -> bool:
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return any(
        fnmatch.fnmatch(str(resolved), pat.replace("**", "*"))
        for pat in _SENSITIVE_PATTERNS
    )


def _fingerprint(tool_name: str, arguments: dict) -> str:
    import hashlib, json
    data = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]
