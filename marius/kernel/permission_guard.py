"""Garde de permissions — évalue allow/ask/deny avant chaque appel d'outil.

Brique standalone, aucune dépendance externe.
Inspiré de Maurice kernel/permissions.py, simplifié pour Marius.

Trois modes :
  safe    → lecture seule dans CWD, écriture sur demande, shell interdit
  limited → lecture + écriture dans CWD et racines autorisées, shell autorisé,
            sortie zone autorisée sur demande
  power   → tout autorisé (hormis chemins système)

Le callback on_ask est fourni par le REPL pour les décisions interactives.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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
_SKILLS_DIR = Path.home() / ".marius" / "skills"
_MARIUS_CONFIG_PATH = Path.home() / ".marius" / "config.json"
_TELEGRAM_CONFIG_PATH = Path.home() / ".marius" / "telegram.json"
_SELF_UPDATE_DIR = Path.home() / ".marius" / "self_updates"
_RAG_DIR = Path.home() / ".marius" / "workspace"
_PROJECTS_PATH = Path.home() / ".marius" / "projects.json"
_ACTIVE_PROJECT_PATH = Path.home() / ".marius" / "active_project.json"
_APPROVALS_PATH = Path.home() / ".marius" / "approvals.json"
_SECRET_REFS_PATH = Path.home() / ".marius" / "secret_refs.json"
_SECRET_FILES_DIR = Path.home() / ".marius" / "secrets"
_PROVIDERS_PATH = Path.home() / ".marius" / "marius_providers.json"
_DREAMS_DIR = Path.home() / ".marius" / "dreams"
_WORKSPACE_ROOT = Path.home() / ".marius" / "workspace"

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
    approval_lookup: Callable[[str], bool | None] | None = None
    approval_recorder: Callable[[dict[str, Any]], None] | None = None
    allowed_roots: tuple[Path, ...] = field(default_factory=tuple)
    allowed_roots_provider: Callable[[], tuple[Path, ...]] | None = None

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

        if self.approval_lookup is not None:
            remembered = self.approval_lookup(fp)
            if remembered is not None:
                self._approvals[fp] = remembered
                return remembered

        if self.on_ask is not None:
            approved = self.on_ask(tool_name, arguments, decision.reason)
            self._approvals[fp] = approved
            self._record_approval(
                fingerprint=fp,
                tool_name=tool_name,
                arguments=arguments,
                reason=decision.reason,
                approved=approved,
            )
            return approved

        return False  # pas de callback → deny par défaut

    def _record_approval(
        self,
        *,
        fingerprint: str,
        tool_name: str,
        arguments: dict,
        reason: str,
        approved: bool,
    ) -> None:
        if self.approval_recorder is None:
            return
        try:
            self.approval_recorder({
                "fingerprint": fingerprint,
                "tool_name": tool_name,
                "arguments": arguments,
                "reason": reason,
                "mode": self.mode,
                "cwd": str(self.cwd),
                "allowed_roots": [str(root) for root in self._current_allowed_roots()],
                "approved": bool(approved),
            })
        except Exception:
            return

    def _evaluate(self, tool_name: str, arguments: dict) -> PermissionDecision:
        if self.mode == "power":
            return self._check_invariants(tool_name, arguments)

        if tool_name in (
            "web_fetch", "web_search", "memory",
            "host_status", "host_doctor", "host_logs", "host_agent_list",
            "project_list", "approval_list", "secret_ref_list", "provider_list",
            "caldav_doctor",
            "caldav_agenda", "sentinelle_scan",
            "rag_source_list", "rag_search", "rag_get",
        ):
            return _ALLOW

        if tool_name == "run_bash":
            return self._check_shell(arguments)

        if tool_name in ("read_file", "list_dir", "vision", "explore_tree", "explore_grep", "explore_summary"):
            return self._check_read(arguments)

        if tool_name in ("write_file", "make_dir"):
            return self._check_write(arguments)
        if tool_name == "move_path":
            return self._check_move(arguments)
        if tool_name in ("skill_list", "skill_reload"):
            return self._check_read({"path": str(_SKILLS_DIR)})
        if tool_name == "skill_create":
            name = str(arguments.get("name") or "_new_skill")
            return self._check_write({"path": str(_SKILLS_DIR / name / "SKILL.md")})
        if tool_name in ("host_agent_save", "host_agent_delete"):
            return self._check_write({"path": str(_MARIUS_CONFIG_PATH)})
        if tool_name == "host_gateway_restart":
            return PermissionDecision("ask", "Redémarrage du gateway demandé.")
        if tool_name == "host_telegram_configure":
            decisions: list[PermissionDecision] = []
            token_ref = str(arguments.get("token_ref") or "")
            if token_ref.startswith("file:"):
                decisions.append(self._check_read({"path": token_ref[5:].strip()}))
            if token_ref.startswith("secret:"):
                decisions.append(self._check_read({"path": str(_SECRET_REFS_PATH)}))
            decisions.append(self._check_write({"path": str(_TELEGRAM_CONFIG_PATH)}))
            return _combine_decisions(decisions)
        if tool_name in ("self_update_list", "self_update_show"):
            return self._check_read({"path": str(_SELF_UPDATE_DIR)})
        if tool_name in ("self_update_propose", "self_update_report_bug"):
            return self._check_write({"path": str(_SELF_UPDATE_DIR)})
        if tool_name in ("self_update_apply", "self_update_rollback"):
            repo_path = str(arguments.get("repo_path") or Path.cwd())
            return _combine_decisions([
                self._check_write({"path": repo_path}),
                self._check_write({"path": str(_SELF_UPDATE_DIR)}),
            ])
        if tool_name == "rag_source_add":
            decisions = [self._check_write({"path": str(_RAG_DIR)})]
            source_path = str(arguments.get("path") or arguments.get("uri") or "")
            if source_path:
                decisions.append(self._check_read({"path": source_path}))
            return _combine_decisions(decisions)
        if tool_name == "rag_source_sync":
            return self._check_write({"path": str(_RAG_DIR)})
        if tool_name == "rag_promote_to_memory":
            return _ALLOW
        if tool_name == "rag_checklist_add":
            path = str(arguments.get("path") or "")
            if path:
                return self._check_write({"path": path})
            return self._check_write({"path": str(_RAG_DIR)})
        if tool_name == "caldav_maintenance":
            return PermissionDecision("ask", "Maintenance CalDAV demandée (discover/sync/verify).")
        if tool_name == "project_set_active":
            decisions = [
                self._check_write({"path": str(_PROJECTS_PATH)}),
                self._check_write({"path": str(_ACTIVE_PROJECT_PATH)}),
            ]
            requested = arguments.get("path")
            if isinstance(requested, str) and requested.strip():
                if bool(arguments.get("create", False)):
                    decisions.append(self._check_write({"path": requested}))
                else:
                    decisions.append(self._check_read({"path": requested}))
            return _combine_decisions(decisions)
        if tool_name in ("approval_decide", "approval_forget"):
            return self._check_write({"path": str(_APPROVALS_PATH)})
        if tool_name in ("secret_ref_save", "secret_ref_delete"):
            decisions = [self._check_write({"path": str(_SECRET_REFS_PATH)})]
            ref = str(arguments.get("ref") or "")
            if ref.startswith("file:"):
                decisions.append(self._check_read({"path": ref[5:].strip()}))
            return _combine_decisions(decisions)
        if tool_name == "secret_ref_prepare_file":
            return _combine_decisions([
                self._check_write({"path": str(_SECRET_REFS_PATH)}),
                self._check_write({"path": str(_SECRET_FILES_DIR)}),
            ])
        if tool_name in ("provider_save", "provider_delete"):
            decisions = [self._check_write({"path": str(_PROVIDERS_PATH)})]
            api_key_ref = str(arguments.get("api_key_ref") or "")
            if api_key_ref.startswith("file:"):
                decisions.append(self._check_read({"path": api_key_ref[5:].strip()}))
            if api_key_ref.startswith("secret:"):
                decisions.append(self._check_read({"path": str(_SECRET_REFS_PATH)}))
            return _combine_decisions(decisions)
        if tool_name == "provider_models":
            return self._check_read({"path": str(_PROVIDERS_PATH)})
        if tool_name == "dreaming_run":
            return self._check_write({"path": str(_DREAMS_DIR)})

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
        if self.mode == "limited" and not self._is_allowed_path(path):
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
        if self.mode == "limited" and not self._is_allowed_path(path):
            return PermissionDecision("ask", f"Écriture hors du projet ({path})")
        return _ALLOW

    def _check_move(self, arguments: dict) -> PermissionDecision:
        source = arguments.get("source")
        destination = arguments.get("destination")
        for path in (source, destination):
            if path:
                decision = self._check_write({"path": path})
                if decision.verdict != "allow":
                    return decision
        return _ALLOW

    def _check_shell(self, arguments: dict) -> PermissionDecision:
        if self.mode == "safe":
            return _DENY_SHELL
        cmd = arguments.get("command", "")
        if _DANGEROUS_SHELL_RE.search(cmd):
            return PermissionDecision("ask", f"Commande potentiellement destructrice :\n  {cmd}")
        return _ALLOW

    def _is_allowed_path(self, path: str) -> bool:
        if _is_under(path, self.cwd):
            return True
        return any(_is_under(path, root) for root in self._current_allowed_roots())

    def _current_allowed_roots(self) -> tuple[Path, ...]:
        roots = tuple(self.allowed_roots)
        if self.allowed_roots_provider is None:
            return roots
        try:
            dynamic_roots = tuple(self.allowed_roots_provider())
        except Exception:
            return roots
        return roots + tuple(root for root in dynamic_roots if root not in roots)


# ── helpers ───────────────────────────────────────────────────────────────────


def _extract_path(arguments: dict) -> str | None:
    for key in ("path", "file_path", "directory", "source", "dest", "destination"):
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


def _combine_decisions(decisions: list[PermissionDecision]) -> PermissionDecision:
    denies = [decision for decision in decisions if decision.verdict == "deny"]
    if denies:
        return denies[0]
    asks = [decision for decision in decisions if decision.verdict == "ask"]
    if asks:
        reasons = [decision.reason for decision in asks if decision.reason]
        return PermissionDecision("ask", "\n".join(reasons))
    return _ALLOW
