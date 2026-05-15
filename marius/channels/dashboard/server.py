"""Serveur HTTP du dashboard Marius.

Routes statiques :
  GET /                        → index.html
  GET /style.css, /app.js      → fichiers statiques

API REST :
  GET  /api/health
  GET  /api/agents
  PUT  /api/agents/:name
  DELETE /api/agents/:name
  GET  /api/providers
  GET  /api/providers/:id/models
  GET  /api/skills
  GET  /api/skills/:name
  POST /api/skills
  PUT  /api/skills/:name
  DELETE /api/skills/:name
  GET  /api/tasks
  POST /api/tasks
  PATCH /api/tasks/:id
  DELETE /api/tasks/:id
  GET  /api/routines
  GET  /api/sessions
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_MARIUS_HOME = Path.home() / ".marius"
_WORKSPACE_ROOT = _MARIUS_HOME / "workspace"
_RUN_DIR = _MARIUS_HOME / "run"
_NEW_PROJECT_MARKER = "nouveau"
_DEFAULT_PROJECTS_ROOT = Path.home() / "Documents" / "projets"

# ── helpers ───────────────────────────────────────────────────────────────────

def _is_running(agent_name: str) -> bool:
    pid_path = _RUN_DIR / f"{agent_name}.pid"
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False




def _sessions_for_agent(agent_name: str, limit: int = 30) -> list[dict]:
    sd = _WORKSPACE_ROOT / agent_name / "sessions"
    if not sd.exists():
        return []
    files = sorted(sd.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            fm = _parse_session_frontmatter(text)
            # extract first user message directly from conversation body
            first_user = _extract_first_user(text)
            out.append({
                "agent":               agent_name,
                "file":                f.name,
                "started_at":          fm.get("opened_at", ""),
                "ended_at":            fm.get("closed_at", ""),
                "turns":               int(fm.get("turns", 0)),
                "project":             fm.get("project", ""),
                "cwd":                 fm.get("cwd", ""),
                "first_user_preview":  first_user,
                "token_series":        [],
                "total_tokens":        0,
                "is_running":          False,
                "is_live":             False,
                "kind":                "session",
            })
        except OSError:
            continue
    return out


def _parse_session_frontmatter(text: str) -> dict:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def _extract_first_user(text: str) -> str:
    """Extract first user message from session file markdown content."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**User**") or stripped.startswith("**Utilisateur**"):
            if ":" in stripped:
                msg = stripped.split(":", 1)[1].strip()
                if msg:
                    return msg[:120]
    return ""


def _relative_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        s = int(diff.total_seconds())
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except (ValueError, TypeError):
        return "—"


def _tail_lines(path: Path, n: int) -> list[str]:
    """Read the last n lines of a file efficiently."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            chunk, data = 8192, b""
            pos = size
            while pos > 0 and data.count(b"\n") < n + 1:
                read = min(chunk, pos)
                pos -= read
                f.seek(pos)
                data = f.read(read) + data
            lines = data.decode(errors="replace").splitlines()
            return [l for l in lines[-n:] if l.strip()]
    except OSError:
        return []


def _api_activity(agent_names: list[str]) -> dict:
    """Reconstruct recent per-agent turn activity from the event log."""
    log_path = _MARIUS_HOME / "logs" / "marius.jsonl"
    empty = lambda: {"active": False, "current_tool": None, "turns": [], "active_turn": None}
    state: dict[str, dict] = {name: {**empty(), "_open": None} for name in agent_names}

    for raw in _tail_lines(log_path, 1500):
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        event = entry.get("event", "")
        data  = entry.get("data", {})
        ts    = entry.get("timestamp", "")

        # Resolve agent — gateway session_id == agent_name
        agent = data.get("agent") or data.get("session_id", "")
        if agent not in state:
            continue

        s = state[agent]

        if event == "turn_start":
            s["_open"] = {
                "at":               ts,
                "user_preview":     data.get("user_preview", ""),
                "tools":            [],
                "assistant_preview": None,
                "input_tokens":     0,
            }
            s["active"] = True
            s["current_tool"] = None

        elif event == "tool_start" and s["_open"] is not None:
            s["_open"]["tools"].append({
                "name":   data.get("tool", ""),
                "target": data.get("target", ""),
                "ok":     None,
            })
            s["current_tool"] = data.get("tool", "")

        elif event == "tool_result" and s["_open"] is not None:
            for t in reversed(s["_open"]["tools"]):
                if t["name"] == data.get("tool") and t["ok"] is None:
                    t["ok"]      = data.get("ok", True)
                    t["summary"] = data.get("summary_preview", "")
                    break
            s["current_tool"] = None

        elif event in ("turn_done", "turn_unexpected_error", "turn_empty_response"):
            if s["_open"] is not None:
                turn = s["_open"]
                turn["assistant_preview"] = data.get("assistant_preview", "")
                turn["input_tokens"]      = data.get("input_tokens", 0)
                turn["ok"]                = event == "turn_done"
                s["turns"].append(turn)
                if len(s["turns"]) > 6:
                    s["turns"] = s["turns"][-6:]
                s["_open"] = None
            s["active"]       = False
            s["current_tool"] = None

    # Build output — most recent turns first, expose open turn if active
    result = {}
    for name, s in state.items():
        turns = list(reversed(s["turns"]))
        result[name] = {
            "active":       s["active"],
            "current_tool": s["current_tool"],
            "active_turn":  s["_open"],
            "turns":        turns,
        }
    return result


# ── DashboardServer ───────────────────────────────────────────────────────────


class DashboardServer:
    def __init__(
        self,
        static_dir: Path,
        *,
        port: int = 8766,
        host: str = "127.0.0.1",
    ) -> None:
        self.static_dir = Path(static_dir)
        self.port = port
        self.host = host
        self._httpd: ThreadingHTTPServer | None = None

        from marius.storage.task_store import TaskStore
        self._tasks = TaskStore()

    def serve(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
                pass

            def do_OPTIONS(self) -> None:
                self._cors_preflight()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/api/health":
                    self._json({"ok": True, "host": server.host, "port": server.port})
                elif path == "/api/config":
                    self._json(_api_config_get())
                elif path == "/api/tools":
                    self._json(_api_tools())
                elif path == "/api/telegram":
                    self._json(_api_telegram_get())
                elif path == "/api/agents":
                    self._json(_api_agents())
                elif path == "/api/providers":
                    self._json(_api_providers())
                elif path == "/api/skills":
                    self._json(_api_skills())
                elif path.startswith("/api/docs/"):
                    name = path[len("/api/docs/"):]
                    result = _api_doc_get(name)
                    if result is None: self._json({"error": "not found"}, 404)
                    else: self._json(result)
                elif path == "/api/routines":
                    self._json(_api_routines())
                elif path == "/api/sessions":
                    qs = parse_qs(parsed.query)
                    limit = int(qs.get("limit", [10])[0])
                    self._json(_api_sessions(limit))
                elif path == "/api/activity":
                    from marius.config.store import ConfigStore
                    cfg = ConfigStore().load()
                    names = list(cfg.agents.keys()) if cfg else []
                    self._json({"activity": _api_activity(names)})
                elif path == "/api/missions":
                    qs = parse_qs(parsed.query)
                    limit = int(qs.get("limit", [60])[0])
                    self._json(_api_missions(limit))
                elif path == "/api/tasks":
                    qs = parse_qs(parsed.query)
                    project       = qs.get("project",       [None])[0]
                    agent         = qs.get("agent",         [None])[0]
                    recurring_only   = "recurring" in qs
                    non_recurring_only = "non_recurring" in qs
                    tasks = server._tasks.list_all(
                        project=project,
                        agent=agent,
                        recurring_only=recurring_only,
                        non_recurring_only=non_recurring_only,
                    )
                    self._json({"tasks": _task_payloads(tasks)})
                elif path == "/api/projects":
                    self._json(_api_projects())
                else:
                    m = re.match(r"^/api/providers/([^/]+)/models$", path)
                    if m:
                        self._json(_api_provider_models(m.group(1)))
                        return
                    m = re.match(r"^/api/agents/([^/]+)/docs/([^/]+)$", path)
                    if m:
                        result = _api_agent_doc_get(m.group(1), m.group(2))
                        if result is None:
                            self._json({"error": "not found"}, 404)
                        else:
                            self._json(result)
                        return
                    m = re.match(r"^/api/agents/([^/]+)/web$", path)
                    if m:
                        self._json(_api_agent_web(m.group(1)))
                        return
                    m = re.match(r"^/api/skills/([^/]+)$", path)
                    if m:
                        result = _api_skill_get(m.group(1))
                        if result is None:
                            self._json({"error": "not found"}, 404)
                        else:
                            self._json(result)
                        return
                    m = re.match(r"^/api/sessions/([^/]+)/([^/]+\.md)$", path)
                    if m:
                        result = _api_session_get(m.group(1), m.group(2))
                        if result is None:
                            self._json({"error": "not found"}, 404)
                        else:
                            self._json(result)
                        return

                    self._serve_static(path)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                body = self._read_json()
                if body is None:
                    return

                m = re.match(r"^/api/agents/([^/]+)/web$", parsed.path)
                if m:
                    self._json(_start_agent_web(m.group(1)))
                    return

                m = re.match(r"^/api/agents/([^/]+)/send$", parsed.path)
                if m:
                    agent_name = m.group(1)
                    msg_text   = str(body.get("message", "")).strip()
                    task_id    = str(body.get("task_id", "")).strip()
                    event_kind = str(body.get("event_kind", "launched")).strip()
                    if not msg_text:
                        self._json({"ok": False, "error": "message required"}, 400)
                        return
                    result = _send_to_agent(agent_name, msg_text)
                    if result.get("ok") and task_id:
                        if event_kind not in {"launched", "planning_requested"}:
                            event_kind = "launched"
                        server._tasks.add_event(task_id, {
                            "kind":    event_kind,
                            "agent":   agent_name,
                            "cmd":     msg_text[:200],
                        })
                    self._json(result)
                    return

                if parsed.path == "/api/agents":
                    ok, msg = _create_agent(body)
                    self._json({"ok": ok, "message": msg}, 201 if ok else 400)
                elif parsed.path == "/api/skills":
                    ok, msg = _create_skill(body)
                    self._json({"ok": ok, "message": msg}, 201 if ok else 400)
                elif parsed.path == "/api/providers":
                    ok, msg = _create_provider(body)
                    self._json({"ok": ok, "message": msg}, 201 if ok else 400)
                elif parsed.path == "/api/providers/probe":
                    self._json(_probe_provider_models(body))
                elif parsed.path == "/api/projects":
                    ok, msg = _api_projects_add(body)
                    self._json({"ok": ok, "message": msg}, 201 if ok else 400)
                else:
                    m = re.match(r"^/api/tasks/([^/]+)/launch$", parsed.path)
                    if m:
                        status, payload = _launch_task(server._tasks, m.group(1))
                        self._json(payload, status)
                        return
                    if parsed.path == "/api/tasks":
                        task = server._tasks.create(body)
                        self._json({"task": asdict(task)}, 201)
                    else:
                        self._json({"error": "not found"}, 404)

            def do_PUT(self) -> None:
                parsed = urlparse(self.path)
                body = self._read_json()
                if body is None:
                    return

                m = re.match(r"^/api/agents/([^/]+)$", parsed.path)
                if m:
                    name = m.group(1)
                    ok, msg = _update_agent(name, body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                m = re.match(r"^/api/skills/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _update_skill(m.group(1), body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                m = re.match(r"^/api/providers/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _update_provider(m.group(1), body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                m = re.match(r"^/api/agents/([^/]+)/docs/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _api_agent_doc_put(m.group(1), m.group(2), body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                m = re.match(r"^/api/docs/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _api_doc_put(m.group(1), body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                if parsed.path == "/api/projects":
                    ok, msg = _api_projects_patch(body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                self._json({"error": "not found"}, 404)

            def do_PATCH(self) -> None:
                parsed = urlparse(self.path)
                body = self._read_json()
                if body is None:
                    return

                if parsed.path == "/api/config":
                    ok, msg = _api_config_patch(body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return

                if parsed.path == "/api/telegram":
                    ok, msg = _api_telegram_patch(body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return

                m = re.match(r"^/api/tasks/([^/]+)$", parsed.path)
                if m:
                    task_id = m.group(1)
                    task = server._tasks.update(task_id, body)
                    if task is None:
                        self._json({"error": "not found"}, 404)
                    else:
                        self._json({"task": asdict(task)})
                    return

                m = re.match(r"^/api/routines/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _patch_routine(m.group(1), body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 404)
                    return

                self._json({"error": "not found"}, 404)

            def do_DELETE(self) -> None:
                parsed = urlparse(self.path)

                m = re.match(r"^/api/tasks/([^/]+)$", parsed.path)
                if m:
                    ok = server._tasks.delete(m.group(1))
                    self._json({"ok": ok}, 200 if ok else 404)
                    return

                m = re.match(r"^/api/routines/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _delete_routine(m.group(1))
                    self._json({"ok": ok, "message": msg}, 200 if ok else 404)
                    return

                if parsed.path == "/api/projects":
                    body = self._read_json()
                    if body is None: return
                    ok, msg = _api_projects_remove(body)
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                m = re.match(r"^/api/skills/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _delete_skill(m.group(1))
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return
                m = re.match(r"^/api/agents/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _delete_agent(m.group(1))
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return

                m = re.match(r"^/api/providers/([^/]+)$", parsed.path)
                if m:
                    ok, msg = _delete_provider(m.group(1))
                    self._json({"ok": ok, "message": msg}, 200 if ok else 400)
                    return

                self._json({"error": "not found"}, 404)

            # ── utils ─────────────────────────────────────────────────────────

            def _cors_preflight(self) -> None:
                self.send_response(204)
                self._cors_headers()
                self.end_headers()

            def _cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def _json(self, data: Any, status: int = 200) -> None:
                body = json.dumps(data, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict | None:
                length = int(self.headers.get("Content-Length", 0))
                if not length:
                    self._json({"error": "empty body"}, 400)
                    return None
                try:
                    return json.loads(self.rfile.read(length).decode())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._json({"error": "invalid json"}, 400)
                    return None

            def _serve_static(self, path: str) -> None:
                if path == "/" or path == "":
                    path = "/index.html"
                safe = path.lstrip("/").replace("..", "")
                full = server.static_dir / safe
                if not full.exists() or not full.is_file():
                    # SPA fallback
                    full = server.static_dir / "index.html"
                    if not full.exists():
                        self._json({"error": "not found"}, 404)
                        return
                mime = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
                body = full.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        print(f"Dashboard → http://{self.host}:{self.port}")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._httpd.server_close()


# ── API handlers ──────────────────────────────────────────────────────────────


def _api_agents() -> dict:
    from marius.config.store import ConfigStore
    from marius.provider_config.store import ProviderStore

    cfg = ConfigStore().load()
    providers = {p.id: p for p in ProviderStore().load()}

    if cfg is None:
        return {"agents": []}

    agents = []
    for name, ac in cfg.agents.items():
        prov = providers.get(ac.provider_id)
        agents.append({
            "name": name,
            "role": ac.role,
            "is_admin": ac.is_admin,
            "provider_id": ac.provider_id,
            "provider_name": prov.name if prov else ac.provider_id,
            "model": ac.model,
            "skills": ac.skills,
            "tools": list(ac.tools),
            "disabled_tools": list(ac.disabled_tools or []),
            "tools_count": len(ac.tools),
            "scheduler_enabled": ac.scheduler_enabled,
            "permission_mode": ac.permission_mode,
            "running": _is_running(name),
            "last_session": _last_session_time(name),
        })
    return {"agents": agents, "permission_mode": cfg.permission_mode}


def _task_payloads(tasks: list[Any]) -> list[dict[str, Any]]:
    running_cache: dict[str, bool] = {}
    permissions_by_agent = _pending_permissions_by_agent(
        sorted({str(getattr(task, "agent", "") or "") for task in tasks if getattr(task, "agent", "")})
    )
    rows: list[dict[str, Any]] = []
    for task in tasks:
        row = asdict(task)
        agent = str(getattr(task, "agent", "") or "")
        if agent and agent not in running_cache:
            running_cache[agent] = _is_running(agent)
        row["running_agent"] = bool(agent and running_cache.get(agent))
        pending = permissions_by_agent.get(agent, [])
        row["pending_permissions"] = pending
        row["permission_pending"] = bool(pending and row.get("status") == "running")
        row["permission_reason"] = pending[0].get("reason", "") if pending else ""
        rows.append(row)
    return rows


def _pending_permissions_by_agent(agent_names: list[str]) -> dict[str, list[dict[str, Any]]]:
    from urllib.request import urlopen

    result: dict[str, list[dict[str, Any]]] = {}
    for agent in agent_names:
        web = _api_agent_web(agent)
        port = web.get("port")
        if not web.get("running") or not port:
            continue
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/permissions", timeout=0.35) as resp:
                data = json.loads(resp.read().decode("utf-8") or "{}")
            permissions = data.get("permissions") if isinstance(data, dict) else []
            if isinstance(permissions, list) and permissions:
                result[agent] = [
                    {
                        "request_id": str(p.get("request_id") or ""),
                        "tool": str(p.get("tool") or ""),
                        "reason": str(p.get("reason") or ""),
                        "created_at": str(p.get("created_at") or ""),
                    }
                    for p in permissions
                    if isinstance(p, dict)
                ]
        except Exception:
            continue
    return result


def _last_session_time(agent_name: str) -> str:
    sd = _WORKSPACE_ROOT / agent_name / "sessions"
    if not sd.exists():
        return ""
    files = list(sd.glob("*.json"))
    if not files:
        return ""
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return _relative_time(
        datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat()
    )


def _update_agent(name: str, data: dict) -> tuple[bool, str]:
    from marius.config.store import ConfigStore
    from marius.config.contracts import (
        disabled_tools_for_active_tools,
        effective_tools_for_agent,
        normalize_disabled_tools,
    )
    store = ConfigStore()
    cfg = store.load()
    if cfg is None:
        return False, "config unavailable"
    if name not in cfg.agents:
        return False, f"agent '{name}' not found"
    ac = cfg.agents[name]
    allowed = {"model", "scheduler_enabled", "skills", "provider_id", "permission_mode"}
    for k, v in data.items():
        if k in allowed:
            setattr(ac, k, v)
    if "disabled_tools" in data and isinstance(data["disabled_tools"], list):
        ac.disabled_tools = normalize_disabled_tools(data["disabled_tools"], ac.role, ac.skills)
    if "tools" in data and isinstance(data["tools"], list):
        ac.disabled_tools = disabled_tools_for_active_tools(data["tools"], ac.role)
    ac.disabled_tools = normalize_disabled_tools(ac.disabled_tools, ac.role, ac.skills)
    ac.tools = effective_tools_for_agent(ac.disabled_tools, ac.role, ac.skills)
    store.save(cfg)
    from marius.storage.task_store import seed_agent_system_tasks
    seed_agent_system_tasks(name, ac.tools or [])
    return True, "updated"


def _delete_agent(name: str) -> tuple[bool, str]:
    from marius.config.store import ConfigStore
    store = ConfigStore()
    cfg = store.load()
    if cfg is None:
        return False, "config unavailable"
    if name not in cfg.agents:
        return False, f"agent '{name}' not found"
    if name == cfg.main_agent:
        return False, "cannot delete the main agent"
    if cfg.agents[name].is_admin:
        return False, "cannot delete the admin agent"
    del cfg.agents[name]
    store.save(cfg)
    return True, "deleted"


def _api_routines() -> dict:
    from marius.storage.task_store import TaskStore
    from marius.config.store import ConfigStore
    cfg = ConfigStore().load()
    running_agents = {name for name in (cfg.agents if cfg else {}) if _is_running(name)}

    now = datetime.now(timezone.utc)
    routines = []
    for t in TaskStore().list_all(recurring_only=True, include_archived=False):
        next_run_human = "—"
        if t.next_run_at:
            try:
                dt   = datetime.fromisoformat(t.next_run_at)
                diff = int((dt - now).total_seconds())
                if diff <= 0:
                    next_run_human = "due"
                elif diff < 3600:
                    next_run_human = f"in {diff // 60}m"
                else:
                    next_run_human = f"in {diff // 3600}h {(diff % 3600) // 60}m"
            except (ValueError, TypeError):
                pass

        routines.append({
            "id":             t.id,
            "name":           t.title,
            "title":          t.title,
            "agent":          t.agent,
            "status":         t.status,
            "priority":       t.priority,
            "cadence":        t.cadence,
            "prompt":         t.prompt,
            "project_path":   t.project_path,
            "task_id":        t.id,
            "system":         t.system,
            "recurring":      True,
            "next_run_at":    t.next_run_at,
            "last_run":       t.last_run,
            "last_error":     t.last_error,
            "next_run_human": next_run_human,
            "last_run_human": _relative_time(t.last_run),
            "running_agent":  t.agent in running_agents,
        })
    return {"routines": routines}


def _patch_routine(routine_id: str, data: dict) -> tuple[bool, str]:
    from marius.storage.task_store import TaskStore
    ts = TaskStore()
    task = next((t for t in ts.load() if t.id == routine_id), None)
    if task is None:
        return False, f"routine '{routine_id}' not found"

    update: dict = {}
    new_status = data.get("status")
    if new_status in ("queued", "paused"):
        update["status"] = new_status
    new_prompt = data.get("prompt")
    if new_prompt is not None:
        update["prompt"] = new_prompt.strip()

    if not update:
        return False, "nothing to update"
    ts.update(routine_id, update)
    return True, "updated"


def _delete_routine(routine_id: str) -> tuple[bool, str]:
    from marius.storage.task_store import TaskStore
    ts = TaskStore()
    task = next((t for t in ts.load() if t.id == routine_id), None)
    if task is None:
        return False, f"routine '{routine_id}' not found"
    ts.update(routine_id, {"status": "archived"})
    return True, "deleted"


def _api_sessions(limit: int = 10) -> dict:
    from marius.config.store import ConfigStore
    cfg = ConfigStore().load()
    if cfg is None:
        return {"sessions": []}

    sessions = []
    for name in cfg.agents:
        sessions.extend(_sessions_for_agent(name, limit=5))
    sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    return {"sessions": sessions[:limit]}


def _api_session_get(agent_name: str, filename: str) -> dict | None:
    """Retourne le contenu brut d'un fichier de session."""
    if ".." in filename or "/" in filename or not filename.endswith(".md"):
        return None
    path = _WORKSPACE_ROOT / agent_name / "sessions" / filename
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        return {"agent": agent_name, "file": filename, "content": content}
    except OSError:
        return None


def _load_log_entries(n: int) -> list[dict]:
    log_path = _MARIUS_HOME / "logs" / "marius.jsonl"
    entries = []
    for raw in _tail_lines(log_path, n):
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return entries


def _duration_seconds(started: str | None, ended: str | None) -> int | None:
    if not started:
        return None
    try:
        s = datetime.fromisoformat(started.replace("Z", "+00:00"))
        e = datetime.fromisoformat(ended.replace("Z", "+00:00")) if ended \
            else datetime.now(timezone.utc)
        return max(0, int((e - s).total_seconds()))
    except (ValueError, TypeError):
        return None


def _enrich_token_series(sessions: list[dict], entries: list[dict]) -> None:
    """Attach token_series from log (does NOT overwrite first_user_preview)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    for s in sessions:
        if s.get("kind") != "session":
            continue
        opened = s.get("started_at", "")
        closed = s.get("ended_at") or now_iso
        agent  = s["agent"]
        series: list[int] = []
        for e in entries:
            ts = e.get("timestamp", "")
            if not ts or not (opened <= ts <= closed):
                continue
            data  = e.get("data", {})
            ev    = e.get("event", "")
            eagent = data.get("agent") or data.get("session_id", "")
            if eagent != agent:
                continue
            if ev == "turn_done":
                series.append(data.get("input_tokens", 0))
        if series:
            s["token_series"] = series
            s["total_tokens"] = sum(series)


def _build_live_session(agent_name: str, entries: list[dict], last_closed: str) -> dict | None:
    """Build a synthetic live-session entry from log events since last closed session."""
    # find the last gateway_start for this agent after last_closed
    gw_ts = ""
    gw_model = ""
    for e in entries:
        if e.get("event") != "gateway_start":
            continue
        data = e.get("data", {})
        if data.get("agent") != agent_name:
            continue
        ts = e.get("timestamp", "")
        if ts >= last_closed:
            gw_ts    = ts
            gw_model = data.get("model", "")

    if not gw_ts:
        # gateway is running but no gateway_start found in log window → use last known turn
        for e in reversed(entries):
            data = e.get("data", {})
            eagent = data.get("agent") or data.get("session_id", "")
            if eagent == agent_name and e.get("event") in ("turn_start", "turn_done", "gateway_start"):
                gw_ts = e.get("timestamp", "")
                break

    turns: list[dict] = []
    open_turn: dict | None = None
    current_tool = ""

    for e in entries:
        ts = e.get("timestamp", "")
        if gw_ts and ts < gw_ts:
            continue
        data   = e.get("data", {})
        event  = e.get("event", "")
        eagent = data.get("agent") or data.get("session_id", "")
        if eagent != agent_name:
            continue

        if event == "turn_start":
            open_turn    = {
                "at":               ts,
                "user_preview":     data.get("user_preview", ""),
                "tools":            [],
                "assistant_preview": "",
                "input_tokens":     0,
                "ok":               None,
            }
            current_tool = ""
        elif event == "tool_start" and open_turn is not None:
            open_turn["tools"].append({
                "name":    data.get("tool", ""),
                "target":  data.get("target", ""),
                "ok":      None,
                "summary": "",
            })
            current_tool = data.get("tool", "")
        elif event == "tool_result" and open_turn is not None:
            for t in reversed(open_turn["tools"]):
                if t["name"] == data.get("tool") and t["ok"] is None:
                    t["ok"]      = data.get("ok", True)
                    t["summary"] = data.get("summary_preview", "")
                    break
            current_tool = ""
        elif event in ("turn_done", "turn_unexpected_error", "turn_empty_response"):
            if open_turn is not None:
                open_turn["assistant_preview"] = data.get("assistant_preview", "")
                open_turn["input_tokens"]      = data.get("input_tokens", 0)
                open_turn["ok"]                = (event == "turn_done")
                turns.append(open_turn)
                open_turn = None
            current_tool = ""

    first_preview = ""
    if turns:
        first_preview = turns[0].get("user_preview", "")
    elif open_turn:
        first_preview = open_turn.get("user_preview", "")

    token_series = [t.get("input_tokens", 0) for t in turns]

    return {
        "agent":              agent_name,
        "file":               None,
        "started_at":         gw_ts or datetime.now(timezone.utc).isoformat(),
        "ended_at":           None,
        "turns":              len(turns) + (1 if open_turn else 0),
        "project":            "",
        "first_user_preview": first_preview,
        "is_running":         True,
        "is_live":            True,
        "kind":               "live",
        "model":              gw_model,
        "current_tool":       current_tool,
        "open_turn":          open_turn,
        "recent_turns":       turns[-8:],
        "token_series":       token_series,
        "total_tokens":       sum(token_series),
        "duration_seconds":   _duration_seconds(gw_ts or None, None),
    }


def _build_scheduled_rows(agent_names: list[str]) -> list[dict]:
    from marius.storage.task_store import TaskStore
    now   = datetime.now(timezone.utc)
    rows  = []
    agent_set = set(agent_names)
    for t in TaskStore().list_all(recurring_only=True, include_archived=False):
        if t.agent not in agent_set or not t.last_run:
            continue
        next_in = None
        if t.next_run_at:
            try:
                dt = datetime.fromisoformat(t.next_run_at)
                next_in = int((dt - now).total_seconds())
            except (ValueError, TypeError):
                pass
        rows.append({
            "agent":              t.agent,
            "file":               None,
            "kind":               "scheduled",
            "job_id":             t.id,
            "started_at":         t.next_run_at or "",
            "ended_at":           None,
            "last_run":           t.last_run,
            "last_run_human":     _relative_time(t.last_run),
            "last_error":         t.last_error,
            "is_running":         False,
            "is_live":            False,
            "turns":              None,
            "project":            "",
            "first_user_preview": t.title,
            "token_series":       [],
            "total_tokens":       0,
            "interval_seconds":   None,
            "status":             t.status,
            "next_in_seconds":    next_in,
            "duration_seconds":   None,
        })
    return rows


def _api_missions(limit: int = 60) -> dict:
    from marius.config.store import ConfigStore
    cfg = ConfigStore().load()
    if cfg is None:
        return {"rows": [], "stats": {}}

    entries = _load_log_entries(4000)

    # ── closed session files ───────────────────────────────────────────────
    closed_sessions: list[dict] = []
    last_closed_by: dict[str, str] = {}

    for name in cfg.agents:
        for s in _sessions_for_agent(name, limit=30):
            s["duration_seconds"] = _duration_seconds(s.get("started_at"), s.get("ended_at"))
            closed_sessions.append(s)
        ended = [s["ended_at"] for s in closed_sessions if s["agent"] == name and s.get("ended_at")]
        last_closed_by[name] = max(ended) if ended else ""

    _enrich_token_series(closed_sessions, entries)

    # ── live sessions (running gateways) ──────────────────────────────────
    live_sessions: list[dict] = []
    for name in cfg.agents:
        if _is_running(name):
            live = _build_live_session(name, entries, last_closed_by.get(name, ""))
            if live:
                live_sessions.append(live)

    # ── scheduled/cron rows ───────────────────────────────────────────────
    scheduled = _build_scheduled_rows(list(cfg.agents.keys()))

    # ── merge & sort ──────────────────────────────────────────────────────
    # live first, then closed sorted desc, scheduled sorted by run_at asc
    closed_sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    closed_sessions = closed_sessions[:limit]
    scheduled.sort(key=lambda s: s.get("started_at", ""))

    rows = live_sessions + closed_sessions[:limit]
    # stats
    total     = len(rows)
    running   = len(live_sessions)
    completed = sum(1 for s in closed_sessions if s.get("ended_at"))

    return {
        "rows":      rows,
        "scheduled": scheduled,
        "stats": {
            "total":     total,
            "running":   running,
            "completed": completed,
            "scheduled": len(scheduled),
        },
    }


def _create_agent(data: dict) -> tuple[bool, str]:
    from marius.config.store import ConfigStore
    from marius.config.contracts import AgentConfig, disabled_tools_for_active_tools, default_tools_for_role, normalize_disabled_tools
    import re as _re
    store = ConfigStore()
    cfg = store.load()
    if cfg is None:
        return False, "config unavailable"
    name = str(data.get("name", "")).strip()
    if not name or not _re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$", name):
        return False, "invalid agent name: use letters, digits, '-' or '_', and start with a letter"
    if name in cfg.agents:
        return False, f"agent '{name}' already exists"
    provider_id = str(data.get("provider_id", "")).strip()
    if not provider_id:
        return False, "provider_id is required"
    model = str(data.get("model", "")).strip()
    if not model:
        return False, "model is required"
    skills = list(data.get("skills") or [])
    if isinstance(data.get("disabled_tools"), list):
        disabled_tools = normalize_disabled_tools(data.get("disabled_tools"), "agent", skills)
    else:
        disabled_tools = disabled_tools_for_active_tools(
            data.get("tools") or default_tools_for_role("agent"),
            "agent",
        )
    agent = AgentConfig(
        name=name,
        provider_id=provider_id,
        model=model,
        role="agent",
        skills=skills,
        disabled_tools=disabled_tools,
        scheduler_enabled=bool(data.get("scheduler_enabled", True)),
    )
    cfg.agents[name] = agent
    store.save(cfg)
    from marius.storage.agent_docs import seed_agent_docs_from_global
    seed_agent_docs_from_global(name, marius_home=_MARIUS_HOME, workspace_root=_WORKSPACE_ROOT)
    from marius.storage.task_store import seed_agent_system_tasks
    seed_agent_system_tasks(name, agent.tools or [])
    return True, f"agent '{name}' created"


_CORE_TOOLS = {
    "read_file", "list_dir", "write_file", "make_dir", "move_path", "run_bash",
}

def _api_tools() -> dict:
    from marius.config.contracts import ALL_TOOLS, ADMIN_ONLY_TOOLS, default_tools_for_role, resolved_tool_groups
    return {
        "tools":      ALL_TOOLS,
        "admin_only": list(ADMIN_ONLY_TOOLS),
        "core":       list(_CORE_TOOLS),
        "groups":     resolved_tool_groups(ALL_TOOLS),
        "default_admin": default_tools_for_role("admin"),
        "default_agent": default_tools_for_role("agent"),
    }


def _api_telegram_get() -> dict:
    from marius.channels.telegram.config import load as tg_load
    cfg = tg_load()
    if cfg is None:
        return {"configured": False}
    return {
        "configured":    True,
        "agent_name":    cfg.agent_name,
        "enabled":       cfg.enabled,
        "allowed_users": cfg.allowed_users,
    }


def _api_telegram_patch(data: dict) -> tuple[bool, str]:
    from marius.channels.telegram.config import (
        load as tg_load, save as tg_save, TelegramChannelConfig,
    )
    cfg = tg_load()
    token = str(data.get("token") or "").strip()

    if cfg is None:
        if not token:
            return False, "token requis pour configurer Telegram"
        cfg = TelegramChannelConfig(
            token=token,
            agent_name=str(data.get("agent_name", "main")),
            enabled=bool(data.get("enabled", True)),
        )
    else:
        if "enabled"       in data: cfg.enabled       = bool(data["enabled"])
        if "agent_name"    in data: cfg.agent_name    = str(data["agent_name"])
        if "allowed_users" in data: cfg.allowed_users = [int(u) for u in data["allowed_users"] if str(u).lstrip("-").isdigit()]
        if token:                   cfg.token         = token

    tg_save(cfg)
    return True, "updated"


def _start_agent_web(agent_name: str) -> dict:
    import socket as _socket
    import subprocess
    import sys
    import time
    from urllib.error import URLError
    from urllib.request import urlopen

    def _http_up(port: int) -> bool:
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as r:
                return 200 <= r.status < 500
        except Exception:
            return False

    # already running → detect via HTTP (more reliable than PID files)
    info = _api_agent_web(agent_name)
    if info["running"] and _http_up(info["port"]):
        return {"ok": True, **info, "started": False}

    # ensure gateway is up
    from marius.gateway.launcher import is_running as gw_running, start as gw_start
    if not gw_running(agent_name):
        if not gw_start(agent_name):
            return {"ok": False, "error": f"Impossible de démarrer le gateway '{agent_name}'"}
        time.sleep(1.0)

    # find a free port (skip 8766 = dashboard)
    port = 8765
    for _ in range(20):
        if port == 8766:
            port += 1; continue
        with _socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                break
        port += 1

    # use the same launch pattern as marius_web tool
    subprocess.Popen(
        [sys.executable, "-c", "from marius.cli import main; main()",
         "web", "--agent", agent_name, "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # poll HTTP (same as _wait_for_web in marius_web)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if _http_up(port):
            url = f"http://localhost:{port}"
            return {"ok": True, "running": True, "url": url, "port": port, "started": True}
        time.sleep(0.2)

    return {"ok": False, "error": "Le canal web n'a pas démarré dans les délais"}


def _api_agent_web(agent_name: str) -> dict:
    import glob
    pattern = str(_RUN_DIR / f"web_{agent_name}_*.pid")
    for pid_file in sorted(glob.glob(pattern)):
        try:
            port = int(Path(pid_file).stem.rsplit("_", 1)[-1])
            pid  = int(Path(pid_file).read_text().strip())
            os.kill(pid, 0)
            return {"running": True, "url": f"http://localhost:{port}", "port": port}
        except (ValueError, OSError):
            continue
    return {"running": False, "url": None, "port": None}


def _api_config_get() -> dict:
    from marius.config.store import ConfigStore
    cfg = ConfigStore().load()
    if cfg is None:
        return {"permission_mode": "limited", "main_agent": "", "agent_count": 0}
    return {
        "permission_mode": cfg.permission_mode,
        "main_agent": cfg.main_agent,
        "agent_count": len(cfg.agents),
    }


def _api_config_patch(data: dict) -> tuple[bool, str]:
    from marius.config.store import ConfigStore
    store = ConfigStore()
    cfg = store.load()
    if cfg is None:
        return False, "config unavailable"
    allowed = {"safe", "limited", "power"}
    new_mode = data.get("permission_mode")
    if new_mode and new_mode in allowed:
        cfg.permission_mode = new_mode
        store.save(cfg)
        return True, f"permission_mode set to {new_mode}"
    return False, f"invalid permission_mode: {new_mode!r} (expected: safe|limited|power)"


def _create_provider(data: dict) -> tuple[bool, str]:
    from marius.provider_config.store import ProviderStore
    from marius.provider_config.contracts import ProviderEntry, AuthType
    from marius.provider_config.registry import PROVIDER_REGISTRY, normalize_base_url, requires_api_key_for_base_url

    kind = str(data.get("provider", "")).strip()
    if kind not in PROVIDER_REGISTRY:
        return False, f"kind '{kind}' inconnu (valeurs: {', '.join(PROVIDER_REGISTRY)})"
    defn = PROVIDER_REGISTRY[kind]
    base_url = normalize_base_url(kind, str(data.get("base_url", "") or defn.default_base_url))
    api_key  = str(data.get("api_key",  "") or "").strip()
    model    = str(data.get("model",    "") or "").strip()
    if requires_api_key_for_base_url(kind, base_url) and not api_key:
        return False, "clé API requise pour ce provider"
    if not model:
        return False, "modèle requis"
    store = ProviderStore()
    name = str(data.get("name", "") or "").strip() or f"{kind}-{len(store.load()) + 1}"
    entry = ProviderEntry(
        id=ProviderEntry.generate_id(), name=name, provider=kind,
        auth_type=AuthType.API, base_url=base_url, api_key=api_key, model=model,
    )
    store.add(entry)
    return True, entry.id


def _update_provider(provider_id: str, data: dict) -> tuple[bool, str]:
    from marius.provider_config.store import ProviderStore
    store   = ProviderStore()
    entries = store.load()
    entry   = next((e for e in entries if e.id == provider_id), None)
    if entry is None:
        return False, f"provider '{provider_id}' introuvable"
    if data.get("name"):     entry.name     = str(data["name"]).strip()
    if data.get("base_url"):
        from marius.provider_config.registry import normalize_base_url
        entry.base_url = normalize_base_url(entry.provider, str(data["base_url"]))
    if data.get("api_key"):  entry.api_key  = str(data["api_key"]).strip()
    if data.get("model"):    entry.model    = str(data["model"]).strip()
    store.update(entry)
    return True, "updated"


def _probe_provider_models(data: dict) -> dict:
    from marius.provider_config.contracts import ProviderEntry, AuthType
    from marius.provider_config.fetcher import fetch_models, ModelFetchError
    from marius.provider_config.registry import PROVIDER_REGISTRY, normalize_base_url
    kind = str(data.get("provider", "")).strip()
    if kind not in PROVIDER_REGISTRY:
        return {"models": [], "error": f"kind '{kind}' inconnu"}
    defn  = PROVIDER_REGISTRY[kind]
    entry = ProviderEntry(
        id="probe", name="probe", provider=kind, auth_type=AuthType.API,
        base_url=normalize_base_url(kind, str(data.get("base_url", "") or defn.default_base_url)),
        api_key=str(data.get("api_key",  "") or ""), model="",
    )
    try:
        return {"models": fetch_models(entry)}
    except ModelFetchError as e:
        return {"models": [], "error": str(e)}
    except Exception as e:
        return {"models": [], "error": f"Erreur : {e}"}


def _delete_provider(provider_id: str) -> tuple[bool, str]:
    from marius.provider_config.store import ProviderStore
    from marius.config.store import ConfigStore
    cfg = ConfigStore().load()
    if cfg:
        using = [n for n, a in cfg.agents.items() if a.provider_id == provider_id]
        if using:
            return False, f"provider used by agent(s): {', '.join(using)}"
    store = ProviderStore()
    ok = store.delete(provider_id)
    return (True, "deleted") if ok else (False, "provider not found")


def _api_providers() -> dict:
    from marius.provider_config.store import ProviderStore
    providers = ProviderStore().load()
    return {
        "providers": [
            {
                "id":        p.id,
                "name":      p.name,
                "provider":  str(p.provider),
                "auth_type": str(p.auth_type),
                "model":     p.model,
                "base_url":  p.base_url,
            }
            for p in providers
        ]
    }


def _api_provider_models(provider_id: str) -> dict:
    from marius.provider_config.store import ProviderStore
    from marius.provider_config.fetcher import fetch_models, ModelFetchError
    providers = ProviderStore().load()
    entry = next((p for p in providers if p.id == provider_id), None)
    if entry is None:
        return {"models": [], "error": "provider not found"}
    try:
        models = fetch_models(entry)
        return {"models": models, "error": None}
    except ModelFetchError as e:
        return {"models": [], "error": str(e)}
    except Exception as e:
        return {"models": [], "error": f"fetch error: {e}"}


def _api_projects() -> dict:
    """Retourne la liste des projets Marius connus + le projet actif."""
    projects_path = _MARIUS_HOME / "projects.json"
    active_path   = _MARIUS_HOME / "active_project.json"

    projects: list[dict] = []
    try:
        raw = json.loads(projects_path.read_text(encoding="utf-8"))
        for p in (raw if isinstance(raw, list) else []):
            projects.append({
                "path":         p.get("path", ""),
                "name":         p.get("name", "") or Path(p.get("path", "")).name,
                "last_opened":  p.get("last_opened", ""),
                "session_count": p.get("session_count", 0),
            })
    except (OSError, json.JSONDecodeError):
        pass

    active_path_str = ""
    active_name = ""
    active_set_at = ""
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
        active_path_str = active.get("path", "")
        active_name = active.get("name", "")
        active_set_at = active.get("set_at", "")
    except (OSError, json.JSONDecodeError):
        pass

    if active_path_str and not any(p["path"] == active_path_str for p in projects):
        projects.append({
            "path": active_path_str,
            "name": active_name or Path(active_path_str).name,
            "last_opened": active_set_at,
            "session_count": 0,
        })

    for p in projects:
        p["active"] = (p["path"] == active_path_str)

    # Sort: active first, then by last_opened desc
    projects.sort(key=lambda p: p.get("last_opened", ""), reverse=True)
    projects.sort(key=lambda p: not p["active"])

    return {"projects": projects, "active_path": active_path_str}


def _api_projects_add(data: dict) -> tuple[bool, str]:
    path_str = str(data.get("path", "")).strip()
    if not path_str:
        return False, "path requis"
    if not Path(path_str).exists():
        return False, f"chemin introuvable : {path_str}"
    projects_file = _MARIUS_HOME / "projects.json"
    try:
        raw = json.loads(projects_file.read_text(encoding="utf-8"))
        projects = raw if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError):
        projects = []
    if any(p.get("path") == path_str for p in projects):
        return False, "projet déjà dans la liste"
    name = str(data.get("name", "") or Path(path_str).name).strip()
    projects.append({
        "path": path_str, "name": name,
        "last_opened": datetime.now(timezone.utc).isoformat(),
        "session_count": 0,
    })
    projects_file.write_text(json.dumps(projects, indent=2, ensure_ascii=False), encoding="utf-8")
    return True, "added"


def _api_projects_remove(data: dict) -> tuple[bool, str]:
    path_str = str(data.get("path", "")).strip()
    projects_file = _MARIUS_HOME / "projects.json"
    try:
        raw = json.loads(projects_file.read_text(encoding="utf-8"))
        projects = raw if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError):
        return False, "projects.json introuvable"
    filtered = [p for p in projects if p.get("path") != path_str]
    if len(filtered) == len(projects):
        return False, "projet non trouvé"
    projects_file.write_text(json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8")
    return True, "removed"


def _api_projects_patch(data: dict) -> tuple[bool, str]:
    path_str = str(data.get("path", "")).strip()
    projects_file = _MARIUS_HOME / "projects.json"
    active_file   = _MARIUS_HOME / "active_project.json"
    try:
        raw = json.loads(projects_file.read_text(encoding="utf-8"))
        projects = raw if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError):
        projects = []
    project = next((p for p in projects if p.get("path") == path_str), None)
    if project is None:
        if data.get("set_active") and path_str and Path(path_str).expanduser().is_dir():
            resolved = str(Path(path_str).expanduser().resolve())
            project = {
                "path": resolved,
                "name": Path(resolved).name,
                "last_opened": datetime.now(timezone.utc).isoformat(),
                "session_count": 0,
            }
            projects.append(project)
            path_str = resolved
        else:
            return False, "projet non trouvé"
    if "name" in data:
        project["name"] = str(data["name"]).strip() or Path(path_str).name
    if data.get("set_active"):
        project["last_opened"] = datetime.now(timezone.utc).isoformat()
    projects_file.write_text(json.dumps(projects, indent=2, ensure_ascii=False), encoding="utf-8")
    if data.get("set_active"):
        active_file.write_text(json.dumps({
            "path": path_str, "name": project["name"],
            "set_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return True, "updated"


def _send_to_agent(agent_name: str, message: str) -> dict:
    """Envoie un message au gateway d'un agent (fire-and-forget via socket Unix)."""
    import socket as _socket
    from urllib.request import Request, urlopen
    from marius.gateway.workspace import socket_path
    from marius.gateway.protocol import InputEvent, encode

    web = _api_agent_web(agent_name)
    if not web.get("running"):
        started = _start_agent_web(agent_name)
        if started.get("ok"):
            web = started
    if web.get("running") and web.get("port"):
        try:
            payload = json.dumps({
                "message": message,
                "session_id": "dashboard-task",
            }).encode("utf-8")
            req = Request(
                f"http://127.0.0.1:{web['port']}/api/message",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8") or "{}")
            if data.get("ok"):
                return {"ok": True}
            return {"ok": False, "error": data.get("error") or "web send failed"}
        except Exception:
            pass

    sock_path = socket_path(agent_name)
    if not sock_path.exists():
        return {"ok": False, "error": f"Gateway '{agent_name}' non actif."}

    try:
        conn = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        conn.settimeout(5.0)
        conn.connect(str(sock_path))
        # Lire le WelcomeEvent
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        # Envoyer le message
        conn.sendall(encode(InputEvent(text=message)))
        conn.close()
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def _send_routine_to_agent(agent_name: str, prompt: str) -> dict:
    """Envoie une routine au gateway et garde la connexion ouverte jusqu'à la fin du tour."""
    import socket as _socket
    from marius.gateway.workspace import socket_path
    from marius.gateway.protocol import InputEvent, PermissionResponseEvent, decode, encode

    web = _api_agent_web(agent_name)
    if not web.get("running"):
        started = _start_agent_web(agent_name)
        if started.get("ok"):
            web = started

    sock_path = socket_path(agent_name)
    if not sock_path.exists():
        return {"ok": False, "error": f"Gateway '{agent_name}' non actif."}

    conn = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    try:
        conn.settimeout(900.0)
        conn.connect(str(sock_path))
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk

        conn.sendall(encode(InputEvent(text=prompt, channel="routine")))
        while True:
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return {"ok": False, "error": "gateway closed before routine completion"}
                buf += chunk
            raw, buf = buf.split(b"\n", 1)
            event = decode(raw.decode(errors="replace"))
            etype = event.get("type")
            if etype == "permission_request":
                conn.sendall(encode(PermissionResponseEvent(
                    request_id=str(event.get("request_id") or ""),
                    approved=False,
                )))
            elif etype == "error":
                return {"ok": False, "error": str(event.get("message") or "routine failed")}
            elif etype in {"done", "status"}:
                return {"ok": True}
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _launch_routine_task(task_store: Any, task: Any) -> tuple[int, dict]:
    prompt = str(getattr(task, "prompt", "") or "").strip() or str(getattr(task, "title", "") or "")
    if not prompt:
        return 400, {"ok": False, "error": "prompt required"}

    previous_status = str(getattr(task, "status", "") or "queued")
    now = datetime.now(timezone.utc)
    task = task_store.update(task.id, {
        "locked_at": now.isoformat(),
        "locked_by": "dashboard-routine",
        "last_error": "",
    }) or task

    def _worker() -> None:
        from marius.storage.task_store import TaskStore

        ts = TaskStore()
        result = _send_routine_to_agent(task.agent, prompt)
        restore_status = "paused" if previous_status == "paused" else "queued"
        if result.get("ok"):
            ts.update(task.id, {
                "status": restore_status,
                "locked_at": "",
                "locked_by": "",
                "last_error": "",
                "attempts": 0,
            })
            ts.add_event(task.id, {
                "kind": "launched",
                "agent": task.agent,
                "cmd": prompt[:200],
                "channel": "routine",
                "manual": True,
            })
        else:
            error = str(result.get("error") or "send_failed")[:300]
            ts.update(task.id, {
                "status": restore_status,
                "locked_at": "",
                "locked_by": "",
                "last_error": error,
            })
            ts.add_event(task.id, {
                "kind": "launch_failed",
                "runner": "dashboard-routine",
                "error": error,
                "channel": "routine",
                "manual": True,
            })

    threading.Thread(target=_worker, daemon=True, name=f"routine-test-{task.id}").start()
    return 202, {"ok": True, "routine": True, "task": asdict(task)}


def _launch_task(task_store: Any, task_id: str) -> tuple[int, dict]:
    task = next((t for t in task_store.load() if t.id == task_id), None)
    if task is None:
        return 404, {"ok": False, "error": "not_found"}
    if not task.agent:
        return 400, {"ok": False, "error": "agent required"}
    if task.recurring and not task.system:
        if task.status not in {"queued", "paused", "failed"}:
            return 400, {"ok": False, "error": f"routine status is {task.status}"}
        return _launch_routine_task(task_store, task)
    if task.status not in {"backlog", "queued", "failed"}:
        return 400, {"ok": False, "error": f"task status is {task.status}"}

    now = datetime.now(timezone.utc)
    scheduled = _parse_task_datetime(task.scheduled_for)
    if task.scheduled_for and scheduled is None:
        return 400, {"ok": False, "error": "invalid scheduled_for"}

    prepared, error = _prepare_new_project_task(task_store, task)
    if error:
        return 400, {"ok": False, "error": error}
    task = prepared

    if scheduled and scheduled > now:
        task = task_store.update(task.id, {
            "status": "queued",
            "last_error": "",
            "next_attempt_at": "",
            "locked_at": "",
            "locked_by": "",
            "attempts": 0,
        }) or task
        task_store.add_event(task.id, {
            "kind": "scheduled",
            "agent": task.agent,
            "for": task.scheduled_for,
        })
        return 200, {"ok": True, "scheduled": True, "task": asdict(task)}

    if _task_queue_locked(task, now):
        return 202, {"ok": True, "queued": True, "locked": True, "task": asdict(task)}
    if task.status in {"backlog", "failed"}:
        task = task_store.update(task.id, {
            "status": "queued",
            "last_error": "",
            "next_attempt_at": "",
            "locked_at": "",
            "locked_by": "",
            "attempts": 0,
        }) or task
    task = task_store.update(task.id, {
        "locked_at": now.isoformat(),
        "locked_by": "dashboard",
    }) or task

    msg = _task_execution_message(task)
    result = _send_to_agent(task.agent, msg)
    if not result.get("ok"):
        task, payload = _mark_task_launch_failed(
            task_store,
            task,
            str(result.get("error") or "send_failed"),
            now=datetime.now(timezone.utc),
            runner="dashboard",
        )
        return 200, {**payload, "task": asdict(task)}

    task = task_store.update(task.id, {
        "status": "running",
        "scheduled_for": "",
        "next_attempt_at": "",
        "locked_at": "",
        "locked_by": "",
        "attempts": 0,
        "last_error": "",
    }) or task
    task_store.add_event(task.id, {
        "kind": "launched",
        "agent": task.agent,
        "cmd": msg[:200],
    })
    return 200, {"ok": True, "scheduled": False, "task": asdict(task)}


def _prepare_new_project_task(task_store: Any, task: Any) -> tuple[Any, str | None]:
    if not _is_new_project_marker(getattr(task, "project_path", "")):
        return task, None

    project_path, error = _resolve_new_project_path(task)
    if error:
        return task, error

    try:
        project_path.mkdir(parents=True, exist_ok=True)
        from marius.storage.project_store import ProjectStore
        from marius.storage.allow_root_store import AllowRootStore

        ProjectStore().record_open(project_path)
        AllowRootStore().add(project_path, reason="dashboard_new_project_task")
    except OSError as exc:
        return task, str(exc)

    updated = task_store.update(task.id, {
        "project_path": str(project_path),
        "last_error": "",
    }) or task
    task_store.add_event(updated.id, {
        "kind": "new_project_prepared",
        "path": str(project_path),
    })
    return updated, None


def _is_new_project_marker(value: str) -> bool:
    return str(value or "").strip().lower() in {"nouveau", "new", "__new__", "__new_project__"}


def _resolve_new_project_path(task: Any) -> tuple[Path | None, str | None]:
    text = f"{getattr(task, 'title', '')}\n{getattr(task, 'prompt', '')}"
    root = _DEFAULT_PROJECTS_ROOT.expanduser().resolve(strict=False)

    absolute = _extract_absolute_project_path(text)
    if absolute is not None:
        path = absolute.expanduser().resolve(strict=False)
    else:
        name = _extract_new_project_name(text)
        if not name:
            return None, "new project selected but no project name found"
        path = (root / name).resolve(strict=False)

    if not _is_path_under(path, root):
        return None, f"new project path must be under {root}"
    if path == root:
        return None, "new project path cannot be the projects root itself"
    return path, None


def _extract_absolute_project_path(text: str) -> Path | None:
    pattern = rf"{re.escape(str(_DEFAULT_PROJECTS_ROOT))}/[^\s\"'`<>]+"
    match = re.search(pattern, text)
    if not match:
        return None
    raw = match.group(0).rstrip(".,;:)]}")
    return Path(raw)


def _extract_new_project_name(text: str) -> str:
    patterns = [
        r"(?:projet|dossier)\s+(?:nomm[ée]|appel[ée])\s+[\"“”']([^\"“”']+)[\"“”']",
        r"[\"“”']([A-Za-z0-9][A-Za-z0-9_.-]{0,80})[\"“”']",
        r"(?:projet|dossier)\s+(?:nomm[ée]|appel[ée])\s+([A-Za-z0-9][A-Za-z0-9_.-]{0,80})\b",
        r"(?:nouveau\s+)?(?:projet|dossier)\s+([A-Za-z0-9][A-Za-z0-9_.-]{0,80})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        name = match.group(1).strip().strip(".,;:)]}")
        if _is_safe_project_name(name):
            return name
    return ""


def _is_safe_project_name(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}", name))


def _is_path_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _task_execution_message(task: Any) -> str:
    from marius.storage.task_execution import task_execution_message
    return task_execution_message(task)


def _parse_task_datetime(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def _task_queue_locked(task: Any, now: datetime) -> bool:
    locked_at = _parse_task_datetime(getattr(task, "locked_at", ""))
    return bool(locked_at and now - locked_at < timedelta(minutes=5))


def _queue_retry_delay_seconds(attempts: int) -> int:
    return min(300, 10 * (2 ** max(0, attempts - 1)))


def _mark_task_launch_failed(
    task_store: Any,
    task: Any,
    error: str,
    *,
    now: datetime,
    runner: str,
) -> tuple[Any, dict]:
    attempts = int(getattr(task, "attempts", 0) or 0) + 1
    max_attempts = max(1, int(getattr(task, "max_attempts", 5) or 5))
    short_error = str(error or "send_failed")[:300]
    if attempts >= max_attempts:
        task = task_store.update(task.id, {
            "status": "failed",
            "attempts": attempts,
            "last_error": short_error,
            "scheduled_for": "",
            "next_attempt_at": "",
            "locked_at": "",
            "locked_by": "",
        }) or task
        task_store.add_event(task.id, {
            "kind": "launch_failed",
            "runner": runner,
            "attempts": attempts,
            "error": short_error,
        })
        return task, {"ok": False, "failed": True, "error": short_error}

    retry_at = now + timedelta(seconds=_queue_retry_delay_seconds(attempts))
    task = task_store.update(task.id, {
        "status": "queued",
        "attempts": attempts,
        "last_error": short_error,
        "scheduled_for": "",
        "next_attempt_at": retry_at.isoformat(),
        "locked_at": "",
        "locked_by": "",
    }) or task
    task_store.add_event(task.id, {
        "kind": "retry_scheduled",
        "runner": runner,
        "attempts": attempts,
        "next_attempt_at": retry_at.isoformat(),
        "error": short_error,
    })
    return task, {
        "ok": True,
        "retry_scheduled": True,
        "next_attempt_at": retry_at.isoformat(),
        "error": short_error,
    }


def _api_doc_get(name: str) -> dict | None:
    """Lit SOUL.md ou IDENTITY.md depuis ~/.marius/."""
    allowed = {"soul": "SOUL.md", "identity": "IDENTITY.md"}
    filename = allowed.get(name)
    if not filename:
        return None
    path = _MARIUS_HOME / filename
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"name": name, "content": content}


def _api_doc_put(name: str, data: dict) -> tuple[bool, str]:
    allowed = {"soul": "SOUL.md", "identity": "IDENTITY.md"}
    filename = allowed.get(name)
    if not filename:
        return False, f"document '{name}' inconnu"
    content = str(data.get("content", ""))
    (_MARIUS_HOME / filename).write_text(content, encoding="utf-8")
    return True, "updated"


def _api_agent_doc_get(agent_name: str, name: str) -> dict | None:
    path = _agent_doc_path(agent_name, name)
    if path is None:
        return None
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "name": name,
        "agent": agent_name,
        "scope": "agent",
        "exists": path.exists(),
        "path": str(path),
        "content": content,
    }


def _api_agent_doc_put(agent_name: str, name: str, data: dict) -> tuple[bool, str]:
    path = _agent_doc_path(agent_name, name)
    if path is None:
        return False, "invalid agent document"
    content = str(data.get("content", ""))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, "updated"


def _agent_doc_path(agent_name: str, name: str) -> Path | None:
    from marius.storage.agent_docs import agent_doc_path
    return agent_doc_path(agent_name, name, marius_home=_MARIUS_HOME, workspace_root=_WORKSPACE_ROOT)


def _api_skills() -> dict:
    from marius.kernel.skills import SkillReader
    from marius.config.store import ConfigStore
    try:
        metas = SkillReader().list()
        cfg = ConfigStore().load()
        agent_skills: dict[str, list[str]] = {}
        if cfg:
            for aname, ac in cfg.agents.items():
                for sk in (ac.skills or []):
                    agent_skills.setdefault(sk, []).append(aname)
        return {
            "skills": [
                {
                    "name": m.name,
                    "description": m.description,
                    "agents": agent_skills.get(m.name, []),
                }
                for m in metas
            ]
        }
    except Exception:
        return {"skills": []}


def _api_skill_get(name: str) -> dict | None:
    skill_file = Path.home() / ".marius" / "skills" / name / "SKILL.md"
    if not skill_file.exists():
        return None
    content = skill_file.read_text(encoding="utf-8")
    description = ""
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.lower().startswith("description:"):
                description = line.split(":", 1)[1].strip()
    return {"name": name, "description": description, "content": content}


def _create_skill(data: dict) -> tuple[bool, str]:
    import re as _re
    name = str(data.get("name", "")).strip().lower()
    if not name or not _re.match(r"^[a-z][a-z0-9_-]{0,63}$", name):
        return False, "nom invalide (minuscules, commence par une lettre)"
    skill_dir = Path.home() / ".marius" / "skills" / name
    if skill_dir.exists():
        return False, f"skill '{name}' existe déjà"
    description = str(data.get("description", name)).strip()
    content = str(data.get("content", "")).strip()
    if not content:
        content = f"---\nname: {name}\ndescription: {description}\n---\n\n# Skill : {name}\n\n{description}\n"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return True, f"skill '{name}' créé"


def _update_skill(name: str, data: dict) -> tuple[bool, str]:
    skill_file = Path.home() / ".marius" / "skills" / name / "SKILL.md"
    if not skill_file.exists():
        return False, f"skill '{name}' introuvable"
    content = str(data.get("content", ""))
    if not content.strip():
        return False, "contenu requis"
    skill_file.write_text(content, encoding="utf-8")
    return True, "updated"


def _delete_skill(name: str) -> tuple[bool, str]:
    import shutil
    if name == "assistant":
        return False, "impossible de supprimer le skill système 'assistant'"
    skill_dir = Path.home() / ".marius" / "skills" / name
    if not skill_dir.exists():
        return False, f"skill '{name}' introuvable"
    from marius.config.store import ConfigStore
    store = ConfigStore()
    cfg = store.load()
    if cfg:
        changed = False
        for ac in cfg.agents.values():
            if name in (ac.skills or []):
                ac.skills = [s for s in ac.skills if s != name]
                changed = True
        if changed:
            store.save(cfg)
    shutil.rmtree(skill_dir)
    return True, "deleted"
