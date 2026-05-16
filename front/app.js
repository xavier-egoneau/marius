/* Marius Dashboard — vanilla JS, no build step */
"use strict";

const API_BASE = "";   // same origin

// ── API ───────────────────────────────────────────────────────────────────────

async function apiJson(response) {
  let data = null;
  try {
    data = await response.json();
  } catch (_) {
    data = null;
  }
  if (!response.ok) {
    const message = data?.message || data?.error || `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return data;
}

const api = {
  async get(path) {
    const r = await fetch(API_BASE + path);
    return apiJson(r);
  },
  async post(path, body) {
    const r = await fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return apiJson(r);
  },
  async put(path, body) {
    const r = await fetch(API_BASE + path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return apiJson(r);
  },
  async patch(path, body) {
    const r = await fetch(API_BASE + path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return apiJson(r);
  },
  async del(path, body) {
    const opts = { method: "DELETE" };
    if (body) { opts.headers = { "Content-Type": "application/json" }; opts.body = JSON.stringify(body); }
    const r = await fetch(API_BASE + path, opts);
    return apiJson(r);
  },
};

// ── toast ─────────────────────────────────────────────────────────────────────

function toast(msg, kind = "ok") {
  const el = document.createElement("div");
  el.className = `toast-item ${kind}`;
  el.textContent = msg;
  document.getElementById("toast").appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ── modal ─────────────────────────────────────────────────────────────────────

const Modal = (() => {
  const overlay = document.getElementById("modal-overlay");
  const title   = document.getElementById("modal-title");
  const body    = document.getElementById("modal-body");
  const footer  = document.getElementById("modal-footer");

  document.getElementById("modal-close").onclick = close;
  let _mdOnOverlay = false;
  overlay.addEventListener("mousedown", e => { _mdOnOverlay = e.target === overlay; });
  overlay.addEventListener("mouseup",   e => { if (_mdOnOverlay && e.target === overlay) close(); });

  function open(opts) {
    title.textContent  = opts.title || "";
    body.innerHTML     = opts.body  || "";
    footer.innerHTML   = opts.footer || "";
    overlay.classList.remove("hidden");
    if (opts.onOpen) opts.onOpen();
  }
  function close() {
    overlay.classList.add("hidden");
    body.innerHTML   = "";
    footer.innerHTML = "";
  }
  return { open, close };
})();

// ── ForceGraph ────────────────────────────────────────────────────────────────

class ForceGraph {
  constructor(svgEl) {
    this.svg   = svgEl;
    this.nodes = [];
    this.links = [];
    this._raf  = null;
    this._drag = null;
    this._w    = 0;
    this._h    = 0;
  }

  resize() {
    const r = this.svg.getBoundingClientRect();
    this._w = r.width || 800;
    this._h = r.height || 600;
  }

  setData(nodes, links) {
    this.nodes = nodes;
    this.links = links;
  }

  initPositions() {
    this.resize();
    const cx = this._w * 0.36, cy = this._h * 0.5;
    const admin  = this.nodes.find(n => n.is_admin);
    const others = this.nodes.filter(n => !n.is_admin);
    if (admin) { admin.x = cx; admin.y = cy; admin.vx = 0; admin.vy = 0; }
    const r = Math.min(this._w, this._h) * 0.27;
    others.forEach((n, i) => {
      const a = -Math.PI / 2 + (i / Math.max(others.length, 1)) * 2 * Math.PI;
      n.x  = cx + r * Math.cos(a) + (Math.random() - .5) * 20;
      n.y  = cy + r * Math.sin(a) + (Math.random() - .5) * 20;
      n.vx = 0; n.vy = 0;
    });
  }

  _tick() {
    const { nodes, links, _w: W, _h: H } = this;
    const cx = W * 0.36, cy = H * 0.5;

    for (const n of nodes) {
      const pull = n.is_admin ? 0.018 : 0.0005;
      n.vx += (cx - n.x) * pull;
      n.vy += (cy - n.y) * pull;
    }

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d2 = dx * dx + dy * dy || 1;
        const d  = Math.sqrt(d2);
        const f  = 14000 / d2;
        a.vx -= f * dx / d; a.vy -= f * dy / d;
        b.vx += f * dx / d; b.vy += f * dy / d;
      }
    }

    for (const lk of links) {
      const a = nodes.find(n => n.id === lk.source);
      const b = nodes.find(n => n.id === lk.target);
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      const d  = Math.sqrt(dx * dx + dy * dy) || 1;
      const f  = (d - 230) * 0.038;
      a.vx += f * dx / d; a.vy += f * dy / d;
      b.vx -= f * dx / d; b.vy -= f * dy / d;
    }

    const pad = 64;
    for (const n of nodes) {
      if (n === this._drag) continue;
      n.vx *= 0.62; n.vy *= 0.62;
      n.x = Math.max(pad, Math.min(W - pad, n.x + n.vx));
      n.y = Math.max(pad, Math.min(H - pad, n.y + n.vy));
    }
  }

  _render() {
    for (const n of this.nodes) {
      const g = this.svg.querySelector(`[data-node="${n.id}"]`);
      if (g) g.setAttribute("transform", `translate(${n.x},${n.y})`);
    }
    for (const lk of this.links) {
      const ln = this.svg.querySelector(`[data-link="${lk.source}|${lk.target}"]`);
      if (!ln) continue;
      const a = this.nodes.find(n => n.id === lk.source);
      const b = this.nodes.find(n => n.id === lk.target);
      if (a && b) {
        ln.setAttribute("x1", a.x); ln.setAttribute("y1", a.y);
        ln.setAttribute("x2", b.x); ln.setAttribute("y2", b.y);
      }
    }
  }

  _loop() {
    this._tick();
    this._render();
    this._raf = requestAnimationFrame(() => this._loop());
  }

  start() { if (!this._raf) this._loop(); }

  stop() {
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
  }

  bindDrag(gEl, nodeData) {
    const self = this;
    function move(e) {
      if (self._drag !== nodeData) return;
      const rect = self.svg.getBoundingClientRect();
      nodeData.x  = (e.clientX - rect.left);
      nodeData.y  = (e.clientY - rect.top);
      nodeData.vx = 0; nodeData.vy = 0;
    }
    function up() {
      self._drag = null;
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup",   up);
    }
    gEl.addEventListener("mousedown", e => {
      e.preventDefault();
      self._drag = nodeData;
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup",   up);
    });
  }
}

// ── AgentPanel ────────────────────────────────────────────────────────────────

const AgentPanel = (() => {
  let _agent = null;

  function open(agent) {
    _agent = agent;
    const panel = document.getElementById("agent-panel");
    if (!panel) return;

    document.getElementById("panel-name").textContent = agent.name.toUpperCase();

    const roleLabel = agent.is_admin ? "ORCHESTRATOR" : _agentRoleLabel(agent);
    const skillsHtml = (agent.skills || []).length
      ? (agent.skills || []).map(s => `<span class="tag">${esc(s)}</span>`).join(" ")
      : `<span style="color:var(--dim)">—</span>`;

    document.getElementById("panel-body").innerHTML = `
      <div class="panel-section">
        <div class="panel-label">STATUS</div>
        <div class="panel-value" style="display:flex;align-items:center;gap:8px">
          <span class="dot ${agent.running ? "on pulse" : ""}"></span>
          <span style="color:${agent.running ? "var(--accent)" : "var(--dim)"}">${agent.running ? "Running" : "Idle"}</span>
        </div>
      </div>
      <div class="panel-section">
        <div class="panel-label">RÔLE</div>
        <div class="panel-value">${esc(roleLabel)}</div>
      </div>
      <div class="panel-section">
        <div class="panel-label">MODÈLE</div>
        <div class="panel-value">${esc(agent.model)}</div>
      </div>
      <div class="panel-section">
        <div class="panel-label">PROVIDER</div>
        <div class="panel-value">${esc(agent.provider_name)}</div>
      </div>
      <div class="panel-section">
        <div class="panel-label">SKILLS</div>
        <div class="panel-value" style="display:flex;flex-wrap:wrap;gap:5px;margin-top:4px">${skillsHtml}</div>
      </div>
      <div class="panel-section">
        <div class="panel-label">TOOLS</div>
        <div class="panel-value">${agent.tools_count} actifs</div>
      </div>
      <div class="panel-section">
        <div class="panel-label">PERMISSIONS</div>
        <div class="panel-value">${esc(agent.permission_mode || "limited")}</div>
      </div>
      ${agent.last_session ? `
        <div class="panel-section">
          <div class="panel-label">DERNIÈRE SESSION</div>
          <div class="panel-value">${esc(agent.last_session)}</div>
        </div>` : ""}
    `;

    document.getElementById("panel-footer").innerHTML = `
      <button class="btn primary" id="btn-panel-chat" style="width:100%">Ouvrir le chat</button>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button class="btn" id="btn-panel-edit" style="flex:1">Éditer agent</button>
        ${!agent.is_admin ? `<button class="btn danger" id="btn-panel-del">Del</button>` : ""}
      </div>
      <button class="btn" id="btn-panel-soul" style="width:100%;margin-top:6px">SOUL.MD</button>
      <button class="btn" id="btn-panel-identity" style="width:100%;margin-top:6px">IDENTITY.MD</button>
    `;

    panel.classList.add("open");

    document.getElementById("btn-panel-edit").onclick = async () => {
      close();
      await openEditAgentModal(agent);
    };
    const delBtn = document.getElementById("btn-panel-del");
    if (delBtn) delBtn.onclick = () => { close(); confirmDeleteAgent(agent.name); };

    document.getElementById("btn-panel-chat").onclick = () => {
      ChatPanel.open(agent);
    };

    document.getElementById("btn-panel-soul").onclick     = () => _openDocEditor("soul", agent.name);
    document.getElementById("btn-panel-identity").onclick = () => _openDocEditor("identity", agent.name);
  }

  function close() {
    _agent = null;
    document.getElementById("agent-panel")?.classList.remove("open");
  }

  function _agentRoleLabel(a) {
    const skills = a.skills || [];
    if (skills.includes("dev"))             return "BUILDER";
    if (skills.includes("rag"))             return "RESEARCHER";
    if (skills.includes("sentinelle"))      return "ANALYST";
    if (skills.includes("caldav_calendar")) return "ASSISTANT";
    if (skills.includes("watch"))           return "MONITOR";
    return "AGENT";
  }

  return { open, close, currentName: () => _agent?.name ?? null };
})();

// ── Doc editor (SOUL / IDENTITY) ──────────────────────────────────────────────

async function _openDocEditor(name, agentName = null) {
  const labels = { soul: "SOUL.MD", identity: "IDENTITY.MD" };
  const hints  = {
    soul:     agentName ? `Override agent ${agentName}` : "Document global",
    identity: agentName ? `Override agent ${agentName}` : "Document global",
  };
  const label = labels[name] || name.toUpperCase();
  const basePath = agentName
    ? `/api/agents/${encodeURIComponent(agentName)}/docs/${encodeURIComponent(name)}`
    : `/api/docs/${encodeURIComponent(name)}`;

  let content = "";
  try {
    const d = await api.get(basePath);
    content = d.content || "";
  } catch (e) { toast("Erreur chargement : " + e.message, "err"); return; }

  Modal.open({
    title: agentName ? `${agentName.toUpperCase()} · ${label}` : label,
    body: `
      <div style="font-size:11px;color:var(--dim);margin-bottom:12px">${esc(hints[name] || "")}</div>
      <textarea id="doc-editor-ta" class="form-textarea"
        style="min-height:420px;font-family:monospace;font-size:12px;line-height:1.6"
      >${esc(content)}</textarea>`,
    footer: `
      <span style="flex:1"></span>
      <button class="btn" onclick="Modal.close()">Annuler</button>
      <button class="btn primary" id="btn-doc-save">Sauvegarder</button>`,
    onOpen() {
      document.getElementById("btn-doc-save").onclick = async () => {
        const newContent = document.getElementById("doc-editor-ta").value;
        try {
          const res = await api.put(basePath, { content: newContent });
          if (res.ok) { toast(`${label} sauvegardé`, "ok"); Modal.close(); }
          else toast(res.message || "Erreur", "err");
        } catch (e) { toast("Erreur : " + e.message, "err"); }
      };
    },
  });
}

// ── ChatPanel ────────────────────────────────────────────────────────────────

const ChatPanel = (() => {
  const overlay   = document.getElementById("chat-overlay");
  const frame     = document.getElementById("chat-frame");
  const loading   = document.getElementById("chat-loading");
  const loadingMsg = document.getElementById("chat-loading-msg");
  const statusDot = document.getElementById("chat-status-dot");
  const statusMsg = document.getElementById("chat-status-msg");

  document.getElementById("chat-close").onclick = close;
  let _draft = "";
  let _autoSend = "";
  let _syncTimer = null;
  // Chat panel closes only via ✕ button — not on outside click

  async function open(agent, opts = {}) {
    _draft = opts.draft || "";
    _autoSend = opts.autoSend || "";

    frame.style.display = "none";
    frame.src = "";
    loading.classList.remove("hidden");
    loadingMsg.textContent = "Démarrage du canal web…";
    statusDot.className = "dot pulse";
    statusMsg.textContent = "";
    overlay.classList.remove("hidden");
    startSync();

    try {
      const res = await api.post(`/api/agents/${encodeURIComponent(agent.name)}/web`, {});
      if (!res.ok) {
        loadingMsg.textContent = res.error || "Erreur au démarrage";
        statusDot.className = "dot err";
        return;
      }
      statusDot.className = "dot on";
      statusMsg.textContent = res.url;
      frame.onload = () => {
        loading.classList.add("hidden");
        frame.style.display = "block";
        if (_draft) {
          injectDraft();
          setTimeout(injectDraft, 300);
          setTimeout(injectDraft, 1000);
        }
      };
      frame.src = _draft ? `${res.url}#draft=${encodeURIComponent(_draft)}` : res.url;
    } catch (e) {
      loadingMsg.textContent = "Erreur : " + e.message;
      statusDot.className = "dot err";
    }
  }

  function close() {
    overlay.classList.add("hidden");
    frame.src = "";
    frame.style.display = "none";
    loading.classList.remove("hidden");
    _draft = "";
    _autoSend = "";
    stopSync();
    if (currentView === "tasks") {
      Views.tasks.reload().catch(() => {});
    } else if (currentView === "routines") {
      Views.routines.reload().catch(() => {});
    }
  }

  function injectDraft() {
    if (!_draft) return;
    frame.contentWindow?.postMessage({ type: "marius:setDraft", text: _draft }, "*");
  }

  function sendAuto() {
    if (!_autoSend) return;
    const text = _autoSend;
    _autoSend = "";
    frame.contentWindow?.postMessage({ type: "marius:sendMessage", text }, "*");
  }

  function startSync() {
    stopSync();
    _syncTimer = setInterval(() => {
      if (currentView === "tasks") {
        Views.tasks.reload().catch(() => {});
      } else if (currentView === "routines") {
        Views.routines.reload().catch(() => {});
      }
    }, 2500);
  }

  function stopSync() {
    if (_syncTimer) {
      clearInterval(_syncTimer);
      _syncTimer = null;
    }
  }

  return { open, close, sendAuto };
})();

// ── router ────────────────────────────────────────────────────────────────────

const VIEWS = ["agents", "control", "tasks", "routines", "skills"];
let currentView = null;
let pollTimer   = null;

window.addEventListener("message", event => {
  if (event.source === document.getElementById("chat-frame")?.contentWindow && event.data?.type === "marius:ready") {
    ChatPanel.sendAuto();
    return;
  }
  if (!["marius:turnDone", "marius:tasksChanged"].includes(event.data?.type)) return;
  if (currentView === "tasks") {
    Views.tasks.reload().catch(() => {});
  } else if (currentView === "routines") {
    Views.routines.reload().catch(() => {});
  }
});

function navigate(view) {
  if (!VIEWS.includes(view)) view = "agents";
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }

  // unmount current view
  if (currentView && Views[currentView]?.unmount) Views[currentView].unmount();

  VIEWS.forEach(v => {
    document.getElementById(`view-${v}`).classList.toggle("active", v === view);
    document.querySelector(`.tab[data-view="${v}"]`).classList.toggle("active", v === view);
  });

  currentView = view;
  location.hash = view;

  const breadcrumbs = {
    agents:   "MARIUS · <b>AGENTS</b>",
    control:  "MARIUS · <b>SESSIONS</b>",
    tasks:    "MARIUS · <b>TASK.BOARD</b>",
    routines: "MARIUS · <b>ROUTINES.CRON</b>",
    skills:   "MARIUS · <b>SKILLS</b>",
  };
  document.getElementById("nav-breadcrumb").innerHTML = breadcrumbs[view];

  Views[view].mount();
}

// ── agents view ───────────────────────────────────────────────────────────────

const Views = {
  agents: {
    data:  null,
    graph: null,

    async mount() {
      const el = document.getElementById("view-agents");
      el.style.overflow = "hidden";
      el.style.padding  = "0";
      setActions([{ label: "+ NEW AGENT", cls: "primary", cb: openNewAgentModal }]);
      await this.reload();
      pollTimer = setInterval(() => this.reload(), 8000);
    },

    unmount() {
      if (this.graph) { this.graph.stop(); }
      AgentPanel.close();
      const el = document.getElementById("view-agents");
      el.style.overflow = "";
      el.style.padding  = "";
    },

    async reload() {
      try {
        const d = await api.get("/api/agents");
        this.data = d;
        renderAgentGraph(d.agents || []);
      } catch (e) {
        document.getElementById("view-agents").innerHTML =
          `<div class="empty">Cannot reach API · ${e.message}</div>`;
      }
    },
  },

  control: {
    async mount() {
      setActions([]);
      await this.reload();
      pollTimer = setInterval(() => this.reload(), 4000);
    },
    async reload() {
      try {
        const d = await api.get("/api/missions");
        renderMissions(d.rows || [], d.scheduled || [], d.stats || {});
      } catch (e) {
        document.getElementById("view-control").innerHTML =
          `<div class="empty">Cannot reach API · ${e.message}</div>`;
      }
    },
  },

  tasks: {
    data:            [],
    filter:          "all",
    projects:        [],
    selectedProject: "all",   // "all" | project path string
    activeProject:   "",
    _projectReady:   false,   // true after first auto-select — user choice is preserved after that

    async mount() {
      this._projectReady = false;
      setActions([
        { label: "ALL",  cls: "filter-btn active", id: "f-all",  cb: () => this.setFilter("all") },
        { label: "HIGH", cls: "filter-btn",        id: "f-high", cb: () => this.setFilter("high") },
        { label: "MED",  cls: "filter-btn",        id: "f-med",  cb: () => this.setFilter("med") },
        { label: "LOW",  cls: "filter-btn",        id: "f-low",  cb: () => this.setFilter("low") },
        { label: "+ NEW TASK", cls: "primary", cb: () => openTaskModal(null, this) },
      ]);
      await this.reload();
      pollTimer = setInterval(() => this.reload(), 3000);
    },

    setFilter(f) {
      this.filter = f;
      ["all","high","med","low"].forEach(k => {
        const el = document.getElementById(`f-${k}`);
        if (el) el.classList.toggle("active", k === f);
      });
      renderKanban(this.data, this.filter, this.selectedProject, this.projects);
    },

    setProject(path) {
      this.selectedProject = path;
      document.querySelectorAll(".project-chip").forEach(c =>
        c.classList.toggle("active", c.dataset.path === path)
      );
      renderKanban(this.data, this.filter, this.selectedProject, this.projects);
    },

    async reload() {
      try {
        const [td, pd] = await Promise.all([
          api.get("/api/tasks?non_recurring=1"),
          api.get("/api/projects").catch(() => ({ projects: [], active_path: "" })),
        ]);
        this.data          = td.tasks    || [];
        this.projects      = pd.projects || [];
        this.activeProject = pd.active_path || "";
        const projectPaths = new Set(this.projects.map(p => p.path));

        if (!this._projectReady) {
          // First load only: auto-select the active project if known
          this._projectReady = true;
          const activeKnown = this.activeProject && projectPaths.has(this.activeProject);
          if (activeKnown) this.selectedProject = this.activeProject;
        } else if (this.selectedProject !== "all" && !projectPaths.has(this.selectedProject)) {
          // Project was deleted or renamed — fall back gracefully
          this.selectedProject = "all";
        }

        renderKanban(this.data, this.filter, this.selectedProject, this.projects);
      } catch (e) {
        document.getElementById("view-tasks").innerHTML =
          `<div class="empty">Cannot reach API · ${e.message}</div>`;
      }
    },
  },

  routines: {
    async mount() {
      setActions([{ label: "+ ROUTINE", cls: "primary", cb: () => openTaskModal(null, Views.tasks, true) }]);
      await this.reload();
      pollTimer = setInterval(() => this.reload(), 15000);
    },
    async reload() {
      try {
        const rd = await api.get("/api/routines");
        renderRoutines(rd.routines || []);
      } catch (e) {
        document.getElementById("view-routines").innerHTML =
          `<div class="empty">Cannot reach API · ${e.message}</div>`;
      }
    },
  },

  skills: {
    _skills:  [],
    _agents:  [],
    _selected: null,

    async mount() {
      setActions([{ label: "+ SKILL", cls: "primary", cb: () => _skillsOpenNew() }]);
      await this._load();
    },

    unmount() { this._selected = null; },

    async _load() {
      const el = document.getElementById("view-skills");
      try {
        const [sd, ad] = await Promise.all([api.get("/api/skills"), api.get("/api/agents")]);
        this._skills = sd.skills || [];
        this._agents = ad.agents || [];
        _skillsRenderList(this);
        const toOpen = this._selected || this._skills[0]?.name || null;
        if (toOpen) await _skillsOpenSkill(this, toOpen);
        else _skillsRenderEmpty();
      } catch (e) {
        el.innerHTML = `<div class="empty">Cannot reach API · ${e.message}</div>`;
      }
    },
  },
};

// ── nav actions helper ────────────────────────────────────────────────────────

function setActions(items) {
  const el = document.getElementById("nav-actions");
  el.innerHTML = "";
  items.forEach(item => {
    const btn = document.createElement("button");
    btn.className = `nav-btn ${item.cls || ""}`;
    btn.textContent = item.label;
    if (item.id) btn.id = item.id;
    btn.onclick = item.cb;
    el.appendChild(btn);
  });
}

// ── skills helpers ────────────────────────────────────────────────────────────

function _skillsRenderList(sv) {
  const el = document.getElementById("view-skills");
  if (!document.getElementById("skills-list")) {
    el.innerHTML = `
      <div id="skills-list">
        <div id="skills-list-header">
          <h3>SKILLS</h3>
          <span class="badge" id="skills-count">0</span>
        </div>
        <div id="skills-list-body"></div>
      </div>
      <div id="skills-editor">
        <div id="skills-editor-scroll"></div>
      </div>`;
  }
  document.getElementById("skills-count").textContent = sv._skills.length;
  const body = document.getElementById("skills-list-body");
  body.innerHTML = "";
  for (const sk of sv._skills) {
    const item = document.createElement("div");
    item.className = `skill-item${sk.name === sv._selected ? " active" : ""}`;
    item.dataset.name = sk.name;
    const tags = (sk.agents || []).map(a => `<span class="skill-tag">${esc(a)}</span>`).join("");
    item.innerHTML = `
      <div class="skill-item-name">${esc(sk.name)}</div>
      <div class="skill-item-desc">${esc(sk.description || "")}</div>
      ${tags ? `<div class="skill-item-agents">${tags}</div>` : ""}`;
    item.onclick = () => _skillsOpenSkill(sv, sk.name);
    body.appendChild(item);
  }
}

function _skillsRenderEmpty() {
  const ed = document.getElementById("skills-editor-scroll");
  if (ed) ed.innerHTML = `<div style="color:var(--dim);font-size:13px;text-align:center;margin-top:60px">Sélectionner un skill pour l'éditer</div>`;
}

async function _skillsOpenSkill(sv, name) {
  sv._selected = name;
  document.querySelectorAll(".skill-item").forEach(el =>
    el.classList.toggle("active", el.dataset.name === name));
  const ed = document.getElementById("skills-editor-scroll");
  if (!ed) return;
  ed.innerHTML = `<div style="color:var(--dim);font-size:12px">Chargement…</div>`;
  try {
    const d = await api.get(`/api/skills/${encodeURIComponent(name)}`);
    _skillsRenderEditor(sv, d);
  } catch (e) {
    ed.innerHTML = `<div class="empty">Erreur : ${esc(e.message)}</div>`;
  }
}

function _skillsRenderEditor(sv, skill) {
  const ed = document.getElementById("skills-editor-scroll");
  if (!ed) return;
  const name = skill.name;
  const isSystem = name === "assistant";

  const agentRows = sv._agents.map(a => {
    const on = (a.skills || []).includes(name);
    return `
      <div class="skill-agent-row">
        <div>
          <div class="skill-agent-row-name">${esc(a.name)}</div>
          <div class="skill-agent-row-role">${esc(a.role || "agent")}</div>
        </div>
        <label class="toggle-wrap" title="${on ? "Désactiver" : "Activer"} pour ${esc(a.name)}">
          <input type="checkbox" class="toggle-input" data-agent="${esc(a.name)}" ${on ? "checked" : ""}>
          <span class="toggle-slider"></span>
        </label>
      </div>`;
  }).join("") || `<div style="color:var(--dim);font-size:12px">Aucun agent configuré</div>`;

  ed.innerHTML = `
    <h2 class="skills-editor-name">${esc(name)}</h2>
    <div class="skills-section-label no-border">SKILL.MD</div>
    <textarea id="skill-content-ta" class="form-textarea" style="min-height:300px;font-family:monospace;font-size:12px;line-height:1.5">${esc(skill.content || "")}</textarea>
    <div style="margin-top:10px;display:flex;gap:8px">
      <button class="nav-btn primary" id="skill-save-btn">SAVE</button>
    </div>
    <div class="skills-section-label">AGENTS</div>
    ${agentRows}
    ${!isSystem ? `
      <div class="skills-section-label">DANGER</div>
      <button class="nav-btn skill-danger-btn" id="skill-delete-btn">SUPPRIMER CE SKILL</button>
    ` : ""}`;

  document.getElementById("skill-save-btn").onclick = () => _skillsSave(sv, name);
  if (!isSystem) document.getElementById("skill-delete-btn").onclick = () => _skillsDelete(sv, name);
  ed.querySelectorAll("input[data-agent]").forEach(cb => {
    cb.onchange = () => _skillsToggleAgent(sv, cb.dataset.agent, name, cb.checked);
  });
}

function _skillsOpenNew() {
  const sv = Views.skills;
  sv._selected = null;
  document.querySelectorAll(".skill-item").forEach(el => el.classList.remove("active"));
  const ed = document.getElementById("skills-editor-scroll");
  if (!ed) return;

  ed.innerHTML = `
    <h2 class="skills-editor-name">NOUVEAU SKILL</h2>
    <div class="form-row">
      <label class="form-label">NOM <span style="color:var(--dim);font-size:10px">(minuscules, tirets OK)</span></label>
      <input type="text" class="form-input" id="new-skill-name" placeholder="mon-skill">
    </div>
    <div class="form-row">
      <label class="form-label">DESCRIPTION</label>
      <input type="text" class="form-input" id="new-skill-desc" placeholder="Ce que fait ce skill">
    </div>
    <div class="form-row">
      <label class="form-label">SKILL.MD</label>
      <textarea class="form-textarea" id="new-skill-content" style="min-height:220px;font-family:monospace;font-size:12px;line-height:1.5"></textarea>
    </div>
    <button class="nav-btn primary" id="new-skill-create-btn">CRÉER</button>`;

  const nameEl    = document.getElementById("new-skill-name");
  const descEl    = document.getElementById("new-skill-desc");
  const contentEl = document.getElementById("new-skill-content");

  const fillTemplate = () => {
    if (contentEl.value.trim()) return;
    const n = nameEl.value.trim() || "mon-skill";
    const d = descEl.value.trim() || n;
    contentEl.value = `---\nname: ${n}\ndescription: ${d}\n---\n\n# Skill : ${n}\n\n${d}\n`;
  };
  nameEl.oninput = fillTemplate;
  descEl.oninput = fillTemplate;

  document.getElementById("new-skill-create-btn").onclick = () => _skillsCreate(sv);
}

async function _skillsCreate(sv) {
  const name    = (document.getElementById("new-skill-name")?.value    || "").trim();
  const desc    = (document.getElementById("new-skill-desc")?.value    || "").trim();
  const content = (document.getElementById("new-skill-content")?.value || "").trim();
  if (!name) { toast("Nom requis", "err"); return; }
  try {
    await api.post("/api/skills", { name, description: desc, content });
    toast(`Skill '${name}' créé`, "ok");
    sv._selected = name;
    await sv._load();
  } catch (e) { toast(e.message || "Erreur", "err"); }
}

async function _skillsSave(sv, name) {
  const content = document.getElementById("skill-content-ta")?.value || "";
  if (!content.trim()) { toast("Contenu requis", "err"); return; }
  try {
    await api.put(`/api/skills/${encodeURIComponent(name)}`, { content });
    toast("Sauvegardé", "ok");
  } catch (e) { toast(e.message || "Erreur", "err"); }
}

async function _skillsDelete(sv, name) {
  if (!confirm(`Supprimer le skill "${name}" ?\nIl sera retiré de tous les agents.`)) return;
  try {
    await api.del(`/api/skills/${encodeURIComponent(name)}`);
    toast(`Skill '${name}' supprimé`, "ok");
    sv._selected = null;
    await sv._load();
  } catch (e) { toast(e.message || "Erreur", "err"); }
}

async function _skillsToggleAgent(sv, agentName, skillName, enable) {
  const agent = sv._agents.find(a => a.name === agentName);
  if (!agent) return;
  const skills = [...(agent.skills || [])];
  if (enable  && !skills.includes(skillName)) skills.push(skillName);
  if (!enable) { const i = skills.indexOf(skillName); if (i !== -1) skills.splice(i, 1); }
  try {
    await api.put(`/api/agents/${encodeURIComponent(agentName)}`, { skills });
    agent.skills = skills;
    const sk = sv._skills.find(s => s.name === skillName);
    if (sk) {
      sk.agents = sv._agents.filter(a => (a.skills || []).includes(skillName)).map(a => a.name);
      _skillsRenderList(sv);
    }
    toast(`${enable ? "Activé" : "Désactivé"} pour ${agentName}`, "ok");
  } catch (e) {
    toast(e.message || "Erreur", "err");
  }
}

// ── render: agent graph ───────────────────────────────────────────────────────

const _NS = "http://www.w3.org/2000/svg";

function _svgEl(tag, attrs = {}) {
  const el = document.createElementNS(_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

// Space Invader pixel art — admin gets the iconic 11×8 crab, others get the 8×8 squid
const _INVADER_PIXELS = {
  admin: [
    [0,1,0,0,0,0,0,0,0,1,0],
    [0,0,1,0,0,0,0,0,1,0,0],
    [0,1,1,1,1,1,1,1,1,1,0],
    [1,1,0,1,1,1,1,1,0,1,1],
    [1,1,1,1,1,1,1,1,1,1,1],
    [1,0,1,1,1,1,1,1,1,0,1],
    [1,0,1,0,0,0,0,0,1,0,1],
    [0,0,0,1,1,0,1,1,0,0,0],
  ],
  default: [
    [0,0,0,1,1,0,0,0],
    [0,0,1,1,1,1,0,0],
    [0,1,1,1,1,1,1,0],
    [1,1,0,1,1,0,1,1],
    [1,1,1,1,1,1,1,1],
    [0,1,0,1,1,0,1,0],
    [1,0,0,0,0,0,0,1],
    [0,1,0,0,0,0,1,0],
  ],
};

function _nodeInvaderSVG(isAdmin) {
  const pixels = isAdmin ? _INVADER_PIXELS.admin : _INVADER_PIXELS.default;
  const rows = pixels.length, cols = pixels[0].length;
  const px = 2.8, gap = 0.2;
  const ox = -(cols * px) / 2, oy = -(rows * px) / 2;
  let out = '';
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (!pixels[r][c]) continue;
      out += `<rect x="${(ox + c * px).toFixed(2)}" y="${(oy + r * px).toFixed(2)}" width="${px - gap}" height="${px - gap}" class="node-icon"/>`;
    }
  }
  return out;
}

async function _refreshSystemHud(agents) {
  const hud = document.getElementById("system-hud");
  if (!hud) return;

  const [taskData, routineData] = await Promise.all([
    api.get("/api/tasks?non_recurring=1").catch(() => ({ tasks: [] })),
    api.get("/api/routines").catch(() => ({ routines: [] })),
  ]);
  const tasks    = taskData.tasks    || [];
  const routines = routineData.routines || [];

  const runningAgents   = agents.filter(a => a.running).length;
  const totalAgents     = agents.length;
  const healthOk        = runningAgents > 0;

  const reviewTasks     = tasks.filter(t => t.status === "review");
  const failedTasks     = tasks.filter(t => t.status === "failed");
  const erroredRoutines = routines.filter(r => r.last_error);
  const blockedCount    = failedTasks.length + erroredRoutines.length;
  const runningTasks    = tasks.filter(t => t.status === "running");
  const activeRoutines  = routines.filter(r => r.status !== "paused");

  const pill = (count, singular, plural, color, onclick) => {
    const label = `${count} ${count === 1 ? singular : plural}`;
    return `<div class="hud-pill hud-clickable" onclick="${onclick}" style="color:${color}">${esc(label)}</div>`;
  };

  const agentLabel = `${runningAgents} ${runningAgents === 1 ? "agent actif" : "agents actifs"} / ${totalAgents}`;

  hud.innerHTML = `
    <span class="dot ${healthOk ? "ok" : "err"}" style="width:8px;height:8px;flex-shrink:0"></span>
    <div class="hud-pill hud-clickable" onclick="navigate('agents')" style="color:${healthOk ? "var(--green)" : "var(--red)"}">${esc(agentLabel)}</div>
    <div class="hud-sep"></div>
    ${pill(reviewTasks.length, "task en review", "tasks en review",
        reviewTasks.length ? "var(--accent)" : "var(--dim)", "navigate('tasks')")}
    <div class="hud-sep"></div>
    ${pill(blockedCount, "task bloquée", "tasks bloquées",
        blockedCount ? "var(--red)" : "var(--dim)", "navigate('tasks')")}
    <div class="hud-sep"></div>
    ${pill(activeRoutines.length, "routine active", "routines actives",
        activeRoutines.length ? "var(--text)" : "var(--dim)", "navigate('routines')")}
  `;
}

function _buildGraphDOM(el) {
  el.innerHTML = `
    <div id="agent-graph-wrap">
      <div id="agent-graph-toolbar">
        <span id="graph-label" style="color:var(--muted);font-size:12px;letter-spacing:.09em">AGENTS</span>
        <span class="badge" id="graph-count">0</span>
      </div>
      <div id="system-hud"></div>
      <svg id="agent-graph" xmlns="${_NS}">
        <defs>
          <pattern id="graph-grid" width="52" height="52" patternUnits="userSpaceOnUse">
            <path d="M52 0 L0 0 0 52" fill="none" stroke="#131313" stroke-width="1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="#0a0a0a"/>
        <rect width="100%" height="100%" fill="url(#graph-grid)"/>
        <g id="links-layer"></g>
        <g id="nodes-layer"></g>
      </svg>
      <div id="agent-panel">
        <div id="panel-head">
          <span id="panel-name"></span>
          <button id="panel-close">✕</button>
        </div>
        <div id="panel-body"></div>
        <div id="panel-footer"></div>
      </div>
    </div>
  `;
  document.getElementById("panel-close").onclick = () => AgentPanel.close();
  // Panel closes only via ✕ button — not on outside click
}

function _buildNodeEl(nodeData) {
  const g = _svgEl("g", {
    class: `agent-node${nodeData.running ? " running" : ""}`,
    "data-node": nodeData.id,
    transform: `translate(${nodeData.x},${nodeData.y})`,
  });

  const roleLabel = nodeData.is_admin ? "ORCHESTRATOR" : (() => {
    const s = nodeData.skills || [];
    if (s.includes("dev"))             return "BUILDER";
    if (s.includes("rag"))             return "RESEARCHER";
    if (s.includes("sentinelle"))      return "ANALYST";
    if (s.includes("caldav_calendar")) return "ASSISTANT";
    if (s.includes("watch"))           return "MONITOR";
    return "AGENT";
  })();

  g.innerHTML = `
    <circle r="42" class="node-pulse"/>
    <circle r="32" class="node-ring"/>
    <circle r="29" class="node-bg"/>
    ${_nodeInvaderSVG(nodeData.is_admin)}
    <text y="50" class="node-name">${esc(nodeData.id.toUpperCase())}</text>
    <text y="64" class="node-role">${esc(roleLabel)}</text>
  `;

  g.addEventListener("click", e => { e.stopPropagation(); AgentPanel.open(nodeData); });
  return g;
}

function renderAgentGraph(agents) {
  const el = document.getElementById("view-agents");
  if (!agents.length) {
    el.innerHTML = `<div class="empty" style="padding-top:80px">No agents configured.</div>`;
    return;
  }

  const isNew = !document.getElementById("agent-graph-wrap");
  if (isNew) _buildGraphDOM(el);

  document.getElementById("graph-count").textContent = agents.length;

  const svg         = document.getElementById("agent-graph");
  const linksLayer  = document.getElementById("links-layer");
  const nodesLayer  = document.getElementById("nodes-layer");
  const admin       = agents.find(a => a.is_admin);

  // save positions from previous graph tick
  const prevPos = {};
  if (Views.agents.graph) {
    for (const n of Views.agents.graph.nodes) prevPos[n.id] = { x: n.x, y: n.y };
  }

  const nodeData = agents.map(a => ({
    id: a.name, ...a,
    x: prevPos[a.name]?.x ?? 0,
    y: prevPos[a.name]?.y ?? 0,
    vx: 0, vy: 0,
  }));
  const linkData = agents
    .filter(a => !a.is_admin && admin)
    .map(a => ({ source: admin.name, target: a.name }));

  // rebuild SVG elements
  linksLayer.innerHTML = "";
  linkData.forEach(lk => {
    const ln = _svgEl("line", {
      class: "agent-link",
      "data-link": `${lk.source}|${lk.target}`,
      x1: 0, y1: 0, x2: 0, y2: 0,
    });
    linksLayer.appendChild(ln);
  });

  nodesLayer.innerHTML = "";
  nodeData.forEach(n => {
    const g = _buildNodeEl(n);
    nodesLayer.appendChild(g);
  });

  // init or reset force graph
  if (!Views.agents.graph) {
    Views.agents.graph = new ForceGraph(svg);
  } else {
    Views.agents.graph.stop();
  }
  Views.agents.graph.setData(nodeData, linkData);

  if (isNew || Object.keys(prevPos).length === 0) {
    Views.agents.graph.initPositions();
  }

  nodeData.forEach(n => {
    const g = nodesLayer.querySelector(`[data-node="${n.id}"]`);
    if (g) Views.agents.graph.bindDrag(g, n);
  });

  Views.agents.graph.start();

  // Keep panel open: refresh current agent or auto-open admin on first render
  const currentName = AgentPanel.currentName();
  const target = currentName
    ? nodeData.find(n => n.id === currentName)
    : (nodeData.find(n => n.is_admin) || nodeData[0]);
  if (target) AgentPanel.open(target);

  // Refresh system HUD (fire-and-forget)
  _refreshSystemHud(agents);
}

// ── render: missions table ────────────────────────────────────────────────────

const _expandedMissions = new Set();

async function _openSessionTranscript(s) {
  if (!s.file) { toast("Transcript non disponible", "err"); return; }
  let content = "";
  try {
    const d = await api.get(`/api/sessions/${encodeURIComponent(s.agent)}/${encodeURIComponent(s.file)}`);
    if (!d || typeof d !== "object") { toast("Réponse invalide", "err"); return; }
    if (d.error) { toast(d.error, "err"); return; }
    content = d.content || "";
  } catch (e) { toast("Erreur chargement : " + e.message, "err"); return; }

  // Parse markdown : strip frontmatter, split turns
  const body = content.replace(/^---[\s\S]*?---\s*\n/, "");
  const turns = [];
  let current = null;
  for (const line of body.split("\n")) {
    const userMatch = line.match(/^\*\*(User|Utilisateur)\*\*\s*:?\s*(.*)/);
    const asstMatch = line.match(/^\*\*(Assistant|Marius)\*\*\s*:?\s*(.*)/);
    if (userMatch) {
      if (current) turns.push(current);
      current = { role: "user", lines: [userMatch[2]] };
    } else if (asstMatch) {
      if (current) turns.push(current);
      current = { role: "asst", lines: [asstMatch[2]] };
    } else if (current) {
      current.lines.push(line);
    }
  }
  if (current) turns.push(current);

  const turnsHtml = turns.map(t => {
    const isUser = t.role === "user";
    const text = t.lines.join("\n").trim();
    return `<div class="transcript-turn ${isUser ? "transcript-user" : "transcript-asst"}">
      <div class="transcript-role">${isUser ? "VOUS" : esc(s.agent.toUpperCase())}</div>
      <div class="transcript-text">${esc(text)}</div>
    </div>`;
  }).join("");

  const date = s.started_at ? new Date(s.started_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" }) : "";

  Modal.open({
    title: `${esc(s.agent.toUpperCase())} · ${date}`,
    body: turnsHtml || `<div style="color:var(--dim)">Transcript vide</div>`,
    footer: `<span style="flex:1"></span><button class="btn" onclick="Modal.close()">Fermer</button>`,
    onOpen() {},
  });
}

const _AGENT_COLORS = ["#e07020","#60a5fa","#22c55e","#f59e0b","#a78bfa","#f472b6","#34d399","#fb923c"];
function _agentColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return _AGENT_COLORS[h % _AGENT_COLORS.length];
}

function _fmtDuration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60)    return `${seconds}s`;
  if (seconds < 3600)  return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}j ${Math.floor((seconds % 86400) / 3600)}h`;
}

function _fmtTok(n) {
  if (!n) return "—";
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;
}

function _miniSpark(series, turns) {
  // prefer token series, fall back to equal-height bars for turns count
  const bars = series && series.length ? series.slice(-16)
    : turns ? Array(Math.min(turns, 16)).fill(1) : null;
  if (!bars) return `<span class="m-tok">—</span>`;
  const max  = Math.max(...bars, 1);
  const total = series ? series.reduce((a,b)=>a+b,0) : 0;
  const tip   = series?.length ? `${series.length} turns · ${_fmtTok(total)} tok` : `${turns} turns`;
  const html  = bars.map(v => {
    const h = Math.max(2, Math.round((v / max) * 18));
    return `<span class="${v === max ? "hi" : ""}" style="height:${h}px"></span>`;
  }).join("");
  return `<span class="m-spark" title="${tip}">${html}</span>`;
}

function _sparkStat(values) {
  if (!values || !values.length) return "";
  const max = Math.max(...values, 1);
  return values.map(v => {
    const h = Math.max(2, Math.round((v / max) * 24));
    return `<span style="height:${h}px"></span>`;
  }).join("");
}

function _missionAge(iso) {
  if (!iso) return "—";
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 0)                return `in ${_fmtDuration(Math.abs(diff))}`;
    if (diff < 60)               return `${Math.round(diff)}s`;
    if (diff < 3600)             return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400)            return `${Math.round(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}j ago`;
  } catch { return "—"; }
}

function _toolsHtml(tools) {
  if (!tools || !tools.length) return "";
  return tools.map(t => {
    const ok  = t.ok === null ? "pending" : t.ok ? "ok" : "err";
    const sym = t.ok === null ? "…" : t.ok ? "✓" : "✗";
    return `<span class="m-tool ${ok}" title="${esc(t.summary||t.target||"")}">${sym} ${esc(t.name)}</span>`;
  }).join(" ");
}

function renderMissions(rows, scheduled, stats) {
  const el = document.getElementById("view-control");
  const savedScroll = document.getElementById("missions-wrap")?.scrollTop ?? 0;

  // Token histogram for sparkline in stats
  const tokByDay = {};
  rows.forEach(s => {
    const day = (s.started_at || "").slice(0, 10);
    if (day) tokByDay[day] = (tokByDay[day] || 0) + (s.total_tokens || 0);
  });
  const sparkVals = Object.values(tokByDay).slice(-12);

  el.innerHTML = `
    <div id="missions-stats">
      <div class="mstat">
        <div class="mstat-label">SESSIONS</div>
        <div class="mstat-value">${stats.total ?? rows.length}</div>
        <div class="mstat-spark">${_sparkStat(sparkVals)}</div>
      </div>
      <div class="mstat">
        <div class="mstat-label">ACTIVE</div>
        <div class="mstat-value running">${stats.running ?? 0}</div>
      </div>
      <div class="mstat">
        <div class="mstat-label">COMPLETED</div>
        <div class="mstat-value green">${stats.completed ?? 0}</div>
      </div>
      <div class="mstat">
        <div class="mstat-label">SCHEDULED</div>
        <div class="mstat-value" style="color:var(--blue)">${stats.scheduled ?? scheduled.length}</div>
      </div>
    </div>
    <div id="missions-wrap">
      <table id="missions-table">
        <thead>
          <tr>
            <th>STATUS</th>
            <th>AGENT</th>
            <th>PROMPT / JOB</th>
            <th class="r">DURÉE</th>
            <th class="r">TURNS</th>
            <th>OUTILS · ACTIVITÉ</th>
            <th class="r">QUAND</th>
          </tr>
        </thead>
        <tbody id="missions-tbody"></tbody>
      </table>
    </div>
  `;

  const tbody = document.getElementById("missions-tbody");
  const color = name => _agentColor(name);

  // ── SCHEDULED future jobs first ──────────────────────────────────────────
  if (scheduled.length) {
    const hdr = document.createElement("tr");
    hdr.innerHTML = `<td colspan="7" class="m-section-hdr">SCHEDULED · ${scheduled.length} jobs</td>`;
    tbody.appendChild(hdr);

    scheduled.forEach(j => {
      const tr = document.createElement("tr");
      const overdue = j.next_in_seconds != null && j.next_in_seconds < 0;
      const statusHtml = overdue
        ? `<span class="m-status overdue">OVERDUE</span>`
        : `<span class="m-status scheduled">SCHED</span>`;
      const nextHtml = j.next_in_seconds != null
        ? (overdue ? `overdue ${_fmtDuration(Math.abs(j.next_in_seconds))}` : `in ${_fmtDuration(j.next_in_seconds)}`)
        : _missionAge(j.started_at);
      const intervalHtml = j.interval_seconds
        ? `<span class="m-interval">${_fmtDuration(j.interval_seconds)}</span>` : "";
      const lastRunHtml  = j.last_run_human ? `<span class="m-tok">last ${esc(j.last_run_human)}</span>` : "";
      const errorHtml    = j.last_error ? `<span class="m-tool err" title="${esc(j.last_error)}">✗ error</span>` : "";

      tr.innerHTML = `
        <td>${statusHtml}</td>
        <td><span class="m-agent"><span class="m-agent-dot" style="background:${color(j.agent)}"></span>${esc(j.agent)}</span></td>
        <td class="m-prompt">${esc(j.first_user_preview || j.job_id)} ${intervalHtml}</td>
        <td class="r m-dur">—</td>
        <td class="r m-tok">—</td>
        <td>${errorHtml} ${lastRunHtml}</td>
        <td class="r m-time">${nextHtml}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // ── LIVE + HISTORY rows ───────────────────────────────────────────────────
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="7" style="color:var(--dim);padding:24px 14px;text-align:center">No sessions yet</td>`;
    tbody.appendChild(tr);
    return;
  }

  // section header if we also have scheduled
  if (scheduled.length) {
    const hdr = document.createElement("tr");
    hdr.innerHTML = `<td colspan="7" class="m-section-hdr">HISTORY · ${rows.length} sessions</td>`;
    tbody.appendChild(hdr);
  }

  rows.forEach(s => {
    const tr = document.createElement("tr");
    const isLive = s.is_live || s.is_running;

    if (isLive) tr.className = "m-running";

    // status badge
    let statusHtml;
    if (isLive) {
      const tool = s.current_tool ? ` <span style="font-size:10px;opacity:.7">${esc(s.current_tool)}</span>` : "";
      statusHtml = `<span class="m-status running"><span class="dot on pulse" style="width:6px;height:6px;flex-shrink:0"></span>LIVE${tool}</span>`;
    } else {
      statusHtml = `<span class="m-status done">COMPLETED</span>`;
    }

    // prompt
    const prompt = (s.first_user_preview || "").trim() || (s.project && s.project !== s.agent ? s.project : "") || "—";

    // tools column: for live show open turn tools; for closed show token sparkline
    let toolsCol;
    if (isLive) {
      const openTools = (s.open_turn?.tools || []);
      const recentDone = (s.recent_turns || []).slice(-3).flatMap(t => t.tools || []);
      const allTools   = [...recentDone, ...openTools];
      toolsCol = allTools.length ? _toolsHtml(allTools) : `<span class="m-tok">—</span>`;
    } else {
      // for completed: show most-used tools + sparkline
      const allTools = (s.recent_turns || []).flatMap(t => t.tools || []);
      const toolNames = [...new Set(allTools.map(t => t.name))].slice(0, 4);
      const toolPills = toolNames.map(n => `<span class="m-tool ok" style="opacity:.5">✓ ${esc(n)}</span>`).join(" ");
      toolsCol = (toolPills || "") + (s.token_series?.length ? " " + _miniSpark(s.token_series, s.turns) : _miniSpark(null, s.turns));
    }

    tr.innerHTML = `
      <td>${statusHtml}</td>
      <td><span class="m-agent"><span class="m-agent-dot" style="background:${color(s.agent)}"></span>${esc(s.agent)}</span></td>
      <td class="m-prompt">${esc(prompt.slice(0, 80))}</td>
      <td class="r m-dur">${_fmtDuration(s.duration_seconds)}</td>
      <td class="r m-tok">${s.turns ?? "—"}</td>
      <td class="m-tools-cell">${toolsCol}</td>
      <td class="r m-time">${_missionAge(s.started_at)}</td>
    `;

    // clic : live → ouvrir le chat · passé → ouvrir le transcript
    tr.style.cursor = "pointer";
    tr.title = isLive ? "Ouvrir le chat" : "Lire le transcript";
    tr.addEventListener("click", () => {
      if (isLive) {
        ChatPanel.open({ name: s.agent });
      } else if (s.file) {
        _openSessionTranscript(s);
      }
    });
    tbody.appendChild(tr);
  });

  if (savedScroll) document.getElementById("missions-wrap").scrollTop = savedScroll;
}

function _expandMissionRow(tr, s, forceOpen = false) {
  // toggle detail row
  const existing = tr.nextElementSibling;
  if (existing && existing.classList.contains("m-detail-row")) {
    if (forceOpen) return; // already open, keep it
    existing.remove(); return;
  }
  const det = document.createElement("tr");
  det.className = "m-detail-row";
  const turns = [...(s.recent_turns || [])];
  if (s.open_turn) turns.push({ ...s.open_turn, _open: true });
  if (!turns.length) return;

  const rows = turns.slice(-8).reverse().map(t => `
    <div class="m-detail-turn">
      <div class="m-detail-head">
        <span class="m-time">${_missionAge(t.at)}</span>
        ${t.input_tokens ? `<span class="m-tok">${_fmtTok(t.input_tokens)} tok</span>` : ""}
        ${t._open ? `<span class="m-status running" style="padding:1px 5px;font-size:10px">IN PROGRESS</span>` : ""}
      </div>
      ${t.user_preview ? `<div class="m-detail-user">▸ ${esc(t.user_preview)}</div>` : ""}
      ${(t.tools||[]).length ? `<div class="m-detail-tools">${_toolsHtml(t.tools)}</div>` : ""}
      ${t.assistant_preview ? `<div class="m-detail-assistant">${esc(t.assistant_preview.slice(0,200))}</div>` : ""}
    </div>`).join("");

  det.innerHTML = `<td colspan="7"><div class="m-detail">${rows}</div></td>`;
  tr.after(det);
}

// ── projects modal ────────────────────────────────────────────────────────────

async function openProjectsModal(tv) {
  const reload = async () => {
    const d = await api.get("/api/projects").catch(() => ({ projects: [], active_path: "" }));
    return { projects: d.projects || [], active: d.active_path || "" };
  };

  const renderRows = (projects, active) => projects.map(p => `
    <div class="proj-row" data-path="${esc(p.path)}">
      <div class="proj-row-info">
        <div style="display:flex;align-items:center;gap:8px">
          <input class="form-input proj-name-input" value="${esc(p.name)}" data-path="${esc(p.path)}"
            style="font-size:13px;padding:4px 8px;flex:0 0 160px" title="Modifier le nom — valide en quittant le champ">
          ${p.active ? `<span class="tag orange">actif</span>` : `<button class="nav-btn proj-set-active" data-path="${esc(p.path)}" style="font-size:10px;padding:2px 8px">Activer</button>`}
        </div>
        <div class="proj-row-path" title="${esc(p.path)}">${esc(p.path)}</div>
      </div>
      <button class="icon-btn danger proj-remove" data-path="${esc(p.path)}">✕</button>
    </div>`).join("") ||
    `<div style="color:var(--dim);font-size:12px;padding:8px 0">Aucun projet enregistré</div>`;

  let { projects, active } = await reload();

  Modal.open({
    title: "PROJETS",
    body: `
      <div id="proj-list">${renderRows(projects, active)}</div>
      <div style="margin-top:20px;border-top:1px solid var(--border);padding-top:16px">
        <div class="form-label" style="margin-bottom:8px">AJOUTER UN PROJET</div>
        <div style="display:flex;gap:8px;align-items:flex-end">
          <div style="flex:1">
            <div style="font-size:11px;color:var(--dim);margin-bottom:4px">CHEMIN ABSOLU</div>
            <input class="form-input" id="proj-add-path" placeholder="/home/user/Documents/projets/monapp">
          </div>
          <div style="flex:0 0 140px">
            <div style="font-size:11px;color:var(--dim);margin-bottom:4px">NOM (optionnel)</div>
            <input class="form-input" id="proj-add-name" placeholder="auto">
          </div>
          <button class="nav-btn primary" id="proj-add-btn">Ajouter</button>
        </div>
      </div>`,
    footer: `<span style="flex:1"></span><button class="btn" onclick="Modal.close()">Fermer</button>`,
    onOpen() {
      const refresh = async () => {
        const r = await reload();
        projects = r.projects; active = r.active;
        document.getElementById("proj-list").innerHTML = renderRows(projects, active);
        wireRows();
        if (tv) await tv.reload();
      };

      const wireRows = () => {
        document.querySelectorAll(".proj-remove").forEach(btn => {
          btn.onclick = async () => {
            if (!confirm(`Retirer "${btn.dataset.path}" de la liste ?`)) return;
            const res = await api.del("/api/projects", { path: btn.dataset.path }).catch(e => ({ ok: false, message: e.message }));
            if (res.ok) { toast("Projet retiré", "ok"); await refresh(); }
            else toast(res.message || "Erreur", "err");
          };
        });
        document.querySelectorAll(".proj-set-active").forEach(btn => {
          btn.onclick = async () => {
            const res = await api.patch("/api/projects", { path: btn.dataset.path, set_active: true }).catch(e => ({ ok: false, message: e.message }));
            if (res.ok) { toast("Projet activé", "ok"); await refresh(); }
            else toast(res.message || "Erreur", "err");
          };
        });
        document.querySelectorAll(".proj-name-input").forEach(input => {
          const saveName = async () => {
            const name = input.value.trim();
            const path = input.dataset.path;
            const original = projects.find(p => p.path === path)?.name || "";
            if (!name || name === original) return;
            const res = await api.patch("/api/projects", { path, name }).catch(e => ({ ok: false, message: e.message }));
            if (res.ok) { toast("Renommé", "ok"); await refresh(); }
            else toast(res.message || "Erreur", "err");
          };
          input.addEventListener("blur", saveName);
          input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); input.blur(); } });
        });
      };
      wireRows();

      document.getElementById("proj-add-btn").onclick = async () => {
        const path = document.getElementById("proj-add-path").value.trim();
        const name = document.getElementById("proj-add-name").value.trim();
        if (!path) { toast("Chemin requis", "err"); return; }
        const res = await api.post("/api/projects", { path, name }).catch(e => ({ ok: false, message: e.message }));
        if (res.ok) {
          toast("Projet ajouté", "ok");
          document.getElementById("proj-add-path").value = "";
          document.getElementById("proj-add-name").value = "";
          await refresh();
        } else toast(res.message || "Erreur", "err");
      };
    },
  });
}

// ── render: kanban ────────────────────────────────────────────────────────────

const COLS = [
  { id: "backlog",  label: "BACKLOG" },
  { id: "queued",   label: "QUEUED" },
  { id: "running",  label: "RUNNING" },
  { id: "failed",   label: "FAILED" },
  { id: "done",     label: "DONE" },
];

function renderKanban(tasks, filter, selectedProject, projects) {
  const el = document.getElementById("view-tasks");

  // Preserve horizontal scroll position across re-renders
  const savedScrollLeft = document.getElementById("kanban")?.scrollLeft ?? 0;

  // filter by project first
  const byProject = selectedProject === "all"
    ? tasks
    : tasks.filter(t => t.project_path === selectedProject);

  const filtered  = filter === "all" ? byProject : byProject.filter(t => t.priority === filter);
  const total     = filtered.length;
  const inflight  = filtered.filter(t => t.status === "running").length;
  const done      = filtered.filter(t => t.status === "done").length;
  const pct       = total ? Math.round(done / total * 100) : 0;

  document.getElementById("nav-breadcrumb").innerHTML =
    `MARIUS · <b>TASK.BOARD</b> <span style="color:var(--dim);font-size:10px;margin-left:8px">${total} tasks · ${inflight} inflight · ${pct}% done</span>`;

  // project bar
  const projBar = _buildProjectBar(projects, selectedProject);

  el.innerHTML = `${projBar}<div id="kanban"></div>`;

  const board = document.getElementById("kanban");

  // wire project chips
  document.querySelectorAll(".project-chip").forEach(chip => {
    chip.addEventListener("click", () => Views.tasks.setProject(chip.dataset.path));
  });
  document.getElementById("btn-edit-projects")?.addEventListener("click", () => openProjectsModal(Views.tasks));

  COLS.forEach(col => {
    const colTasks = filtered.filter(t => t.status === col.id);
    const colEl = document.createElement("div");
    colEl.className = "kanban-col";
    colEl.dataset.status = col.id;
    colEl.innerHTML = `
      <div class="col-head">
        <span class="dot ${col.id === "running" ? "on pulse" : col.id === "done" ? "ok" : col.id === "failed" ? "err" : ""}"></span>
        <span class="col-title">${col.label}</span>
        <span class="col-count">${colTasks.length}</span>
      </div>
      <div class="col-body" data-col="${col.id}"></div>
    `;
    const body = colEl.querySelector(".col-body");
    body.addEventListener("dragover",  e => { e.preventDefault(); body.classList.add("drag-over"); });
    body.addEventListener("dragleave", ()  => body.classList.remove("drag-over"));
    body.addEventListener("drop", async e => {
      e.preventDefault();
      body.classList.remove("drag-over");
      const id = e.dataTransfer.getData("text/plain");
      if (!id) return;
      try {
        await api.patch(`/api/tasks/${id}`, { status: col.id });
        await Views.tasks.reload();
      } catch (err) { toast("Move failed: " + err.message, "err"); }
    });
    colTasks.forEach(t => body.appendChild(buildTaskCard(t)));
    board.appendChild(colEl);
  });

  // Restore horizontal scroll after columns are in the DOM
  board.scrollLeft = savedScrollLeft;
}

function _buildProjectBar(projects, selected) {
  const editBtn = `<button class="project-bar-edit" id="btn-edit-projects" title="Gérer les projets">···</button>`;
  if (!projects || !projects.length) {
    return `<div id="project-bar"><span id="project-bar-label">PROJET</span><button class="project-chip${selected === "all" ? " active" : ""}" data-path="all">Tous</button>${editBtn}</div>`;
  }
  const chips = [
    `<button class="project-chip${selected === "all" ? " active" : ""}" data-path="all">Tous</button>`,
    ...projects.map(p => {
      const isActive = p.active ? " active-project" : "";
      const isSel    = selected === p.path ? " active" : "";
      return `<button class="project-chip${isActive}${isSel}" data-path="${esc(p.path)}" title="${esc(p.path)}">${esc(p.name)}</button>`;
    }),
  ].join("");
  return `<div id="project-bar"><span id="project-bar-label">PROJET</span>${chips}${editBtn}</div>`;
}

function buildTaskCard(t) {
  const card = document.createElement("div");
  card.className = "task-card";
  if (t.permission_pending) card.classList.add("needs-permission");
  if (t.status === "running") card.classList.add("is-running");
  card.dataset.priority = t.priority;
  card.draggable = true;

  const elapsed = t.time_spent_minutes
    ? t.time_spent_minutes >= 60 ? `${Math.floor(t.time_spent_minutes/60)}h` : `${t.time_spent_minutes}m`
    : "";
  const tags = (t.tags || []).map(tg => `<span class="tag">${esc(tg)}</span>`).join(" ");

  // action buttons: backlog is cadrage/queue; queued is already owned by the scheduler.
  const canPlan = t.agent && ["backlog","failed"].includes(t.status);
  const canQueue = t.agent && t.status === "backlog";
  const canRetry = t.agent && t.status === "failed";
  const retryHtml = t.next_attempt_at
    ? `<div class="task-desc">Retry ${esc(_missionAge(t.next_attempt_at))}</div>`
    : "";
  const errorHtml = t.last_error
    ? `<div class="task-desc" style="color:var(--red)">${esc(t.last_error)}</div>`
    : "";
  const permissionHtml = t.permission_pending
    ? `<span class="task-alert" title="${esc(t.permission_reason || "Autorisation requise")}">ASK</span>`
    : "";
  const agentTitle = t.running_agent
    ? `${t.agent} actif`
    : `${t.agent} inactif`;
  const agentHtml = t.agent
    ? `<span class="task-agent ${t.running_agent ? "is-running" : "is-idle"}" title="${esc(agentTitle)}"><span class="task-agent-dot"></span>${esc(t.agent)}</span>`
    : "";
  const actHtml = canPlan ? `
    <div class="task-actions" onclick="event.stopPropagation()">
      <button class="task-btn task-btn-plan">Plan</button>
      ${canQueue ? `<button class="task-btn primary task-btn-queue">Queue →</button>` : ""}
      ${canRetry ? `<button class="task-btn primary task-btn-retry">Retry →</button>` : ""}
    </div>` : t.status === "running" && t.agent ? `
    <div class="task-actions" onclick="event.stopPropagation()">
      <button class="task-btn primary task-btn-view">${t.permission_pending ? "Ask" : "Voir"} →</button>
    </div>` : "";

  card.innerHTML = `
    <div class="task-top">
      <span class="task-id">${esc(t.id.toUpperCase())}</span>
      ${permissionHtml}
      ${t.status === "running" ? `<span class="task-gear">⚙</span>` : elapsed ? `<span class="task-time">${elapsed}</span>` : ""}
    </div>
    <div class="task-title">${esc(t.title)}</div>
    ${t.prompt ? `<div class="task-desc">${esc(t.prompt.slice(0,100))}</div>` : ""}
    ${retryHtml}
    ${errorHtml}
    ${t.status === "running" && t.progress > 0 ? `
      <div class="task-progress">
        <div class="task-progress-fill" style="width:${t.progress}%"></div>
      </div>` : ""}
    <div class="task-footer">
      ${t.project_path || t.project ? `<span class="task-project">${esc((t.project_path||t.project).split("/").pop())}</span>` : ""}
      ${agentHtml}
    </div>
    ${actHtml}
  `;

  card.addEventListener("dragstart", e => e.dataTransfer.setData("text/plain", t.id));
  card.onclick = () => {
    if (t.permission_pending && t.agent) viewTask(t);
    else openTaskModal(t, Views.tasks);
  };

  card.querySelector(".task-btn-plan")?.addEventListener("click", e => { e.stopPropagation(); planTask(t); });
  card.querySelector(".task-btn-queue")?.addEventListener("click", e => { e.stopPropagation(); queueTask(t); });
  card.querySelector(".task-btn-retry")?.addEventListener("click", e => { e.stopPropagation(); queueTask(t); });
  card.querySelector(".task-btn-view")?.addEventListener("click", e => { e.stopPropagation(); viewTask(t); });

  return card;
}

// ── task actions ──────────────────────────────────────────────────────────────

function _taskPlanningMessage(t, projectPath = "") {
  const effectiveProject = t.project_path || t.project || projectPath || "";
  const parts = [
    `Voici le plan actuel de cette task. Aide-moi à mieux le cadrer avant exécution.`,
    `Critique la task : ce qui est flou, trop large, manquant, risqué ou mal formulé.`,
    `Demande-moi les infos supplémentaires nécessaires si tu en as besoin, puis aide-moi à la réécrire proprement.`,
    `Quand le cadrage est clair, propose une version structurée puis utilise explicitement l'outil task_update avec l'id ci-dessous et le champ prompt. N'utilise jamais de champ description. Ne crée pas de nouvelle task.`,
    `Ne change pas status, priority, agent ni project_path sauf si je te le demande explicitement.`,
    `Task id: ${t.id}`,
    `Titre actuel: ${t.title}`,
    `Status actuel: ${t.status || "backlog"}`,
    `Priorité actuelle: ${t.priority || "med"}`,
    `Agent actuel: ${t.agent || "(aucun)"}`,
    `Project path actuel: ${effectiveProject || "(aucun)"}`,
  ];
  parts.push(`Prompt actuel:\n${t.prompt || "(vide)"}`);
  return parts.join("\n\n");
}

async function planTask(t) {
  let projectPath = t.project_path || t.project || "";
  if (!t.project_path && !t.project && Views.tasks?.selectedProject && Views.tasks.selectedProject !== "all") {
    projectPath = Views.tasks.selectedProject;
    t = { ...t, project_path: projectPath };
    api.patch(`/api/tasks/${t.id}`, { project_path: projectPath }).catch(() => {});
  }
  if (projectPath) {
    await api.patch("/api/projects", { path: projectPath, set_active: true })
      .then(() => {
        if (Views.tasks) Views.tasks.activeProject = projectPath;
      })
      .catch(() => toast(`Projet actif non modifié`, "err"));
  }
  ChatPanel.open({ name: t.agent }, { draft: _taskPlanningMessage(t, projectPath) });
  toast(`Message de cadrage prêt dans le chat → ${t.agent}`, "ok");
  if (projectPath) Views.tasks.reload().catch(() => {});
}

async function queueTask(t) {
  try {
    const res = await api.patch(`/api/tasks/${t.id}`, {
      status: "queued",
      last_error: "",
      next_attempt_at: "",
      locked_at: "",
      locked_by: "",
      attempts: 0,
    });
    if (!res.task) {
      toast(`Mise en queue échouée`, "err");
    } else if (res.task.scheduled_for) {
      toast(`Tâche programmée → ${t.agent}`, "ok");
    } else {
      toast(`Tâche en queue → ${t.agent}`, "ok");
    }
    await Views.tasks.reload();
  } catch (e) { toast("Erreur : " + e.message, "err"); }
}

function viewTask(t) {
  ChatPanel.open({ name: t.agent });
}

// ── render: routines ──────────────────────────────────────────────────────────

function renderRoutines(routines) {
  const el = document.getElementById("view-routines");

  const active  = routines.filter(r => r.status !== "paused").length;
  const nextJob = routines
    .filter(r => r.next_run_human && r.next_run_human !== "—" && r.next_run_human !== "due")
    .sort((a, b) => (a.next_run_at || "").localeCompare(b.next_run_at || ""))[0];

  el.innerHTML = `
    <div class="section-head">
      <h2>ROUTINES.CRON</h2>
      <span id="routines-meta" class="badge">
        ${active} actives${nextJob ? ` · next ${esc(nextJob.next_run_human)}` : ""}
      </span>
    </div>
    <div id="routines-grid"></div>
  `;

  const grid = document.getElementById("routines-grid");

  if (!routines.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Aucune routine configurée.";
    grid.appendChild(empty);
    return;
  }

  routines.forEach(r => {
    const isPaused  = r.status === "paused";
    const isRunning = r.status === "running";
    const hasError  = !!r.last_error;
    const dotClass  = isRunning ? "on pulse" : hasError ? "err" : isPaused ? "" : "ok";

    const card = document.createElement("div");
    card.className = `routine-card${isPaused ? " paused" : hasError ? " last-failed" : ""}`;
    card.style.cursor = "pointer";
    card.innerHTML = `
      <div class="routine-head">
        <span class="dot ${dotClass}"></span>
        <span class="routine-name">${esc(r.name)}</span>
        ${r.system ? `<span style="font-size:10px;color:var(--dim);padding:1px 5px;border:1px solid var(--border);border-radius:3px;margin-left:2px">sys</span>` : ""}
        ${isPaused ? `<span style="font-size:10px;color:var(--dim);margin-left:4px">paused</span>` : ""}
      </div>
      <div class="routine-meta" style="margin-top:4px">
        <span class="routine-cron">${esc(r.cadence || "—")}</span>
        ${r.agent ? `<span class="routine-agent">● ${esc(r.agent)}</span>` : ""}
        ${r.next_run_human && r.next_run_human !== "—" ? `<span style="color:var(--dim);font-size:11px;margin-left:6px">next ${esc(r.next_run_human)}</span>` : ""}
        ${r.last_run_human && r.last_run_human !== "—" ? `<span style="color:var(--dim);font-size:11px;margin-left:4px">· last ${esc(r.last_run_human)}</span>` : ""}
      </div>
      ${r.last_error ? `<div class="routine-desc" style="color:var(--red);font-size:11px">${esc(r.last_error)}</div>` : ""}
      ${r.prompt ? `<div class="routine-desc" style="font-size:11px;color:var(--dim)">${esc(r.prompt)}</div>` : ""}
      <div class="routine-footer">
        <button class="routine-footer-btn btn-toggle-routine">${isPaused ? "▶ Activer" : "⏸ Pause"}</button>
        ${r.agent && r.prompt ? `<button class="routine-footer-btn accent btn-test-routine">▶ Tester</button>` : ""}
      </div>
    `;

    card.onclick = () => openTaskModal(r, Views.routines);

    card.querySelector(".btn-toggle-routine").onclick = async e => {
      e.stopPropagation();
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        const newStatus = isPaused ? "queued" : "paused";
        await api.patch(`/api/routines/${encodeURIComponent(r.id)}`, { status: newStatus });
        await Views.routines.reload();
      } catch (err) {
        toast("Erreur : " + err.message, "err");
        btn.disabled = false;
      }
    };

    if (r.agent && r.prompt) {
      card.querySelector(".btn-test-routine").onclick = async e => {
        e.stopPropagation();
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = "Envoi…";
        try {
          const res = await api.post(`/api/tasks/${encodeURIComponent(r.id)}/launch`, {});
          if (!res.ok) throw new Error(res.error || "test failed");
          toast(`Test lancé → ${r.agent}`, "ok");
          ChatPanel.open({ name: r.agent });
          await Views.routines.reload();
        } catch(err) {
          toast("Erreur : " + err.message, "err");
        } finally {
          btn.disabled = false;
          btn.textContent = "▶ Tester";
        }
      };
    }


    grid.appendChild(card);
  });
}

// ── modals: agent ─────────────────────────────────────────────────────────────

async function openNewAgentModal() {
  const [provData, skillData, toolData] = await Promise.all([
    api.get("/api/providers").catch(() => ({ providers: [] })),
    api.get("/api/skills").catch(() => ({ skills: [] })),
    api.get("/api/tools").catch(() => ({ tools: [], admin_only: [] })),
  ]);
  const providers = provData.providers || [];
  const allSkills = skillData.skills   || [];
  const allTools  = toolData.tools     || [];
  const adminOnly = new Set(toolData.admin_only || []);

  // blank agent shell for the form
  const blank = {
    name: "", provider_id: providers[0]?.id || "", model: providers[0]?.model || "",
    is_admin: false, role: "agent", skills: [], tools: toolData.default_agent || [], disabled_tools: [], permission_mode: "limited",
  };

  Modal.open({
    title: "NEW AGENT",
    body: `
      <div class="form-row">
        <label class="form-label">NAME</label>
        <input class="form-input" id="f-name" placeholder="ex: researcher" autocomplete="off">
        <div style="font-size:11px;color:var(--dim);margin-top:6px">Identifiant : lettres, chiffres, tiret ou underscore. Les espaces seront remplacés par des tirets.</div>
      </div>
      ${_agentFormHtml(blank, providers, allSkills, new Set(), providers[0] || null, allTools, adminOnly, toolData, { configured: false }, true)}
    `,
    footer: `
      <span style="flex:1"></span>
      <button class="btn" onclick="Modal.close()">Annuler</button>
      <button class="btn primary" id="btn-create-agent">Créer</button>
    `,
    onOpen() {
      // provider → model cascade (same as edit)
      const provSel  = document.getElementById("f-provider");
      const modelSel = document.getElementById("f-model");
      if (provSel && modelSel) {
        provSel.addEventListener("change", async () => {
          modelSel.disabled = true;
          modelSel.innerHTML = "<option>Loading…</option>";
          const d = await api.get(`/api/providers/${encodeURIComponent(provSel.value)}/models`).catch(() => ({ models: [] }));
          if (d.models?.length) {
            modelSel.innerHTML = d.models.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
          } else {
            modelSel.outerHTML = `<input class="form-input" id="f-model" value="">`;
          }
          modelSel.disabled = false;
        });
        // trigger once for initial provider
        if (providers.length) provSel.dispatchEvent(new Event("change"));
      }

      document.getElementById("btn-create-agent").onclick = async () => {
        const rawName = val("f-name");
        const name = normalizeAgentName(rawName);
        const nameEl = document.getElementById("f-name");
        if (nameEl && rawName !== name) nameEl.value = name;
        if (!name) { toast("Le nom est requis", "err"); return; }
        if (!isValidAgentName(name)) {
          toast("Nom invalide : commence par une lettre, puis lettres/chiffres/tiret/underscore.", "err");
          return;
        }
        const d = _readAgentForm();
        if (!d.provider_id) { toast("Sélectionne un provider", "err"); return; }
        if (!d.model)        { toast("Renseigne un modèle", "err"); return; }
        try {
          const res = await api.post("/api/agents", { name, ...d });
          if (res.ok) {
            toast(`Agent "${name}" créé`, "ok");
            Modal.close();
            await Views.agents.reload();
          } else {
            toast(res.message || "Erreur", "err");
          }
        } catch (e) { toast("Erreur : " + e.message, "err"); }
      };
    },
  });
}

async function openEditAgentModal(agent) {
  const [provData, skillData, toolData, tgData] = await Promise.all([
    api.get("/api/providers").catch(() => ({ providers: [] })),
    api.get("/api/skills").catch(() => ({ skills: [] })),
    api.get("/api/tools").catch(() => ({ tools: [], admin_only: [] })),
    api.get("/api/telegram").catch(() => ({ configured: false })),
  ]);
  const providers    = provData.providers || [];
  const allSkills    = skillData.skills   || [];
  const allTools     = toolData.tools     || [];
  const adminOnly    = new Set(toolData.admin_only || []);
  const activeSkills = new Set(agent.skills || []);

  // telegram ownership — calculé ici pour être accessible dans le closure onOpen
  const tgOwner  = tgData.configured && tgData.agent_name === agent.name;
  const tgActive = tgOwner && tgData.enabled;

  // find the current provider entry so we can pre-load its models
  const currentProv = providers.find(p => p.id === agent.provider_id) || null;

  Modal.open({
    title: `EDIT AGENT · ${agent.name.toUpperCase()}`,
    body: _agentFormHtml(agent, providers, allSkills, activeSkills, currentProv, allTools, adminOnly, toolData, tgData),
    footer: `
      ${!agent.is_admin ? `<button class="btn danger" id="btn-del-agent">Delete</button>` : ""}
      <span style="flex:1"></span>
      <button class="btn" onclick="Modal.close()">Cancel</button>
      <button class="btn primary" id="btn-save-agent">Save</button>
    `,
    onOpen() {
      // wire provider → model cascade
      const provSelect  = document.getElementById("f-provider");
      const modelSelect = document.getElementById("f-model");

      async function loadModels(providerId, currentModel) {
        modelSelect.disabled = true;
        modelSelect.innerHTML = `<option>Loading…</option>`;
        try {
          const d = await api.get(`/api/providers/${encodeURIComponent(providerId)}/models`);
          const models = d.models || [];
          if (models.length) {
            modelSelect.innerHTML = models.map(m =>
              `<option value="${esc(m)}" ${m === currentModel ? "selected" : ""}>${esc(m)}</option>`
            ).join("");
          } else {
            // fallback: free-text
            modelSelect.outerHTML = `<input class="form-input" id="f-model" value="${esc(currentModel)}">`;
          }
        } catch {
          modelSelect.outerHTML = `<input class="form-input" id="f-model" value="${esc(currentModel)}">`;
        }
        modelSelect.disabled = false;
      }

      // load models for the current provider on open
      if (currentProv) {
        loadModels(currentProv.id, agent.model);
      }

      provSelect.addEventListener("change", () => {
        const selectedId = provSelect.value;
        const curModel = document.getElementById("f-model")?.value || "";
        loadModels(selectedId, curModel);
      });

      // permission mode toggle
      document.querySelectorAll('.perm-option input[name="f-perm"]').forEach(input => {
        input.addEventListener("change", () => {
          document.querySelectorAll('.perm-option input[name="f-perm"]').forEach(el =>
            el.closest(".perm-option").classList.remove("active")
          );
          input.closest(".perm-option").classList.add("active");
        });
      });

      // telegram toggle → show/hide fields
      const tgToggle = document.getElementById("f-tg-enabled");
      const tgFields = document.getElementById("tg-fields");
      if (tgToggle && tgFields) {
        tgToggle.addEventListener("change", () => {
          tgFields.style.display = tgToggle.checked ? "" : "none";
        });
      }

      document.getElementById("btn-save-agent").onclick = async () => {
        const data = _readAgentForm();
        try {
          // save agent config
          const res = await api.put(`/api/agents/${agent.name}`, data);
          if (!res.ok) { toast(res.message || "Erreur", "err"); return; }

          // save telegram uniquement si interaction explicite
          const tgToggle = document.getElementById("f-tg-enabled");
          if (tgToggle) {
            const token        = val("f-tg-token").trim();
            const usersRaw     = val("f-tg-users").trim();
            const toggledOn    = tgToggle.checked;
            const ownsChannel  = tgOwner;   // cet agent était déjà propriétaire
            const tokenEntered = !!token;

            // cas 1 : nouveau token entré → configurer / transférer ce canal ici
            // cas 2 : propriétaire existant + état toggle changé → enable/disable
            // cas 3 : propriétaire + users modifiés
            const usersChanged = ownsChannel && usersRaw !== (tgData.allowed_users || []).join(", ");
            const stateChanged = ownsChannel && toggledOn !== tgActive;

            if (tokenEntered || stateChanged || usersChanged) {
              const patch = { enabled: toggledOn, agent_name: agent.name };
              if (token) patch.token = token;
              if (usersRaw !== undefined) {
                patch.allowed_users = usersRaw
                  ? usersRaw.split(",").map(s => parseInt(s.trim())).filter(n => !isNaN(n))
                  : [];
              }
              await api.patch("/api/telegram", patch).catch(e => toast("Telegram : " + e.message, "err"));
            }
          }

          toast("Agent sauvegardé", "ok");
          Modal.close();
          await Views.agents.reload();
        } catch (e) { toast("Erreur : " + e.message, "err"); }
      };

      const delBtn = document.getElementById("btn-del-agent");
      if (delBtn) delBtn.onclick = () => {
        Modal.close();
        confirmDeleteAgent(agent.name);
      };
    },
  });
}

function _agentFormHtml(agent, providers, allSkills, activeSkills, currentProv, allTools, adminOnly, toolData, tgData, hideNameRow = false) {
  // provider select
  const provOptions = providers.map(p =>
    `<option value="${esc(p.id)}" ${p.id === agent.provider_id ? "selected" : ""}>${esc(p.name)} · ${esc(p.provider)}</option>`
  ).join("");

  const modelHtml = `<option value="${esc(agent.model)}" selected>${esc(agent.model || "—")}</option>`;

  // skills as toggles
  const skillsList = allSkills.length
    ? allSkills
    : (agent.skills || []).map(s => ({ name: s, description: "" }));

  const skillsHtml = skillsList.length
    ? skillsList.map(s => `
        <label class="toggle-row skill-toggle-row">
          <span class="toggle-label-block">
            <span class="toggle-label">${esc(s.name)}</span>
            ${s.description ? `<span class="toggle-desc">${esc(s.description)}</span>` : ""}
          </span>
          <span class="toggle-wrap">
            <input type="checkbox" class="toggle-input" name="skill" value="${esc(s.name)}"
              ${activeSkills.has(s.name) ? "checked" : ""}>
            <span class="toggle-slider"></span>
          </span>
        </label>`).join("")
    : `<span style="color:var(--dim);font-size:12px">Aucun skill disponible</span>`;

  // tools as group toggles
  const activeTools = new Set(agent.tools || []);
  const disabledTools = new Set(agent.disabled_tools || []);
  const isAdmin     = agent.is_admin;
  const coreTools   = new Set(toolData?.core || []);
  const toolGroups  = (toolData?.groups || []).length
    ? toolData.groups
    : [{ id: "all", label: "Tools", description: "Outils disponibles", tools: allTools }];

  const editableTools = [];

  const toolsHtml = `
    <input type="hidden" id="f-disabled-tools" value="${esc([...disabledTools].join(","))}">
    <div class="tool-toggles">
      ${toolGroups.map(group => {
        const label = group.label || group.id || "Tools";
        const desc = group.description || "";
        const items = Array.isArray(group.tools) ? group.tools.filter(t => allTools.includes(t)) : [];
        // filter: remove core, remove admin-only if not admin
        const available = items.filter(t =>
          !coreTools.has(t) && (isAdmin || !adminOnly.has(t))
        );
        if (!available.length) return "";
        editableTools.push(...available);
        const isOn = available.some(t => activeTools.has(t));
        const activeCount = available.filter(t => activeTools.has(t)).length;
        const partial = activeCount > 0 && activeCount < available.length;
        return `
          <label class="toggle-row tool-toggle-row">
            <span class="toggle-label-block">
              <span class="toggle-label">${esc(label)}</span>
              ${desc ? `<span class="toggle-desc">${esc(desc)}</span>` : ""}
              ${partial ? `<span class="toggle-desc tool-partial">Partiel : ${activeCount}/${available.length} outils actifs.</span>` : ""}
            </span>
            <span class="toggle-wrap">
              <input type="checkbox" class="toggle-input tool-group-toggle"
                data-tools="${esc(available.join(","))}"
                data-initial-disabled="${esc(available.filter(t => disabledTools.has(t)).join(","))}"
                onchange="this.dataset.dirty='1'"
                ${isOn ? "checked" : ""}>
              <span class="toggle-slider"></span>
            </span>
          </label>`;
      }).filter(Boolean).join("")}
    </div>
    <input type="hidden" id="f-editable-tools" value="${esc([...new Set(editableTools)].join(","))}">`;

  // telegram — recalculé ici pour le rendu (tgOwner/tgActive existent aussi dans openEditAgentModal pour le save handler)
  const tgOwner  = tgData.configured && tgData.agent_name === agent.name;
  const tgActive = tgOwner && tgData.enabled;
  const tgUsers  = (tgData.allowed_users || []).join(", ");
  const tgHtml = `
    <label class="toggle-row" style="margin-bottom:6px">
      <span class="toggle-label">Canal Telegram</span>
      <span class="toggle-wrap">
        <input type="checkbox" id="f-tg-enabled" class="toggle-input" ${tgActive ? "checked" : ""}>
        <span class="toggle-slider"></span>
      </span>
    </label>
    <div id="tg-fields" style="${tgActive ? "" : "display:none"}">
      <div class="form-row" style="margin-top:8px;margin-bottom:0">
        <label class="form-label">BOT TOKEN</label>
        <input class="form-input" id="f-tg-token" type="password"
          placeholder="${tgOwner ? "Laisser vide pour conserver le token existant" : "123456789:ABCdef…"}">
      </div>
      <div class="form-row" style="margin-top:8px;margin-bottom:0">
        <label class="form-label">ALLOWED USER IDS <span style="color:var(--dim);font-weight:normal">(séparés par virgule — vide = tous)</span></label>
        <input class="form-input" id="f-tg-users" value="${esc(tgUsers)}"
          placeholder="ex : 123456789, 987654321">
      </div>
    </div>`;

  const permOpts = ["safe", "limited", "power"];
  const curPerm  = agent.permission_mode || "limited";
  const permHtml = `
    <div style="display:flex;gap:8px">
      ${permOpts.map(p => `
        <label class="perm-option ${p === curPerm ? "active" : ""}">
          <input type="radio" name="f-perm" value="${p}" ${p === curPerm ? "checked" : ""} style="display:none">
          <span>${p.toUpperCase()}</span>
        </label>`).join("")}
    </div>
    <div style="margin-top:6px;font-size:11px;color:var(--dim)">
      safe — lecture seule &nbsp;·&nbsp; limited — écriture locale (recommandé) &nbsp;·&nbsp; power — sans restriction
    </div>`;

  return `
    ${hideNameRow ? "" : `
    <div class="form-row">
      <label class="form-label">NAME</label>
      <div class="form-input" style="opacity:.45;cursor:default">${esc(agent.name)}</div>
    </div>`}
    <div class="form-row">
      <label class="form-label">PERMISSION MODE</label>
      ${permHtml}
    </div>
    <div class="form-row">
      <label class="form-label">PROVIDER</label>
      ${providers.length
        ? `<select class="form-select" id="f-provider">${provOptions}</select>`
        : `<div class="form-input" style="opacity:.45">${esc(agent.provider_id)}</div><input type="hidden" id="f-provider" value="${esc(agent.provider_id)}">`}
    </div>
    <div class="form-row">
      <label class="form-label">MODEL</label>
      <select class="form-select" id="f-model">${modelHtml}</select>
    </div>
    <div class="form-row">
      <label class="form-label">TELEGRAM</label>
      <div>${tgHtml}</div>
    </div>
    <div class="form-row">
      <label class="form-label">SKILLS <span style="color:var(--dim);font-weight:normal;letter-spacing:0">— packs de capacités injectés dans le prompt</span></label>
      <div class="tool-toggles">${skillsHtml}</div>
    </div>
    <div class="form-row">
      <label class="form-label">TOOLS</label>
      <div class="tools-container">${toolsHtml}</div>
    </div>
  `;
}

function _readAgentForm() {
  const provEl  = document.getElementById("f-provider");
  const modelEl = document.getElementById("f-model");
  const skills  = [...document.querySelectorAll('input[name="skill"]:checked')].map(el => el.value);

  const existingDisabledEl = document.getElementById("f-disabled-tools");
  const disabled = new Set(existingDisabledEl ? existingDisabledEl.value.split(",").filter(Boolean) : []);
  document.querySelectorAll(".tool-group-toggle").forEach(t => {
    const tools = t.dataset.tools.split(",").filter(Boolean);
    if (t.dataset.dirty === "1") {
      tools.forEach(tool => {
        if (t.checked) disabled.delete(tool);
        else disabled.add(tool);
      });
    }
  });

  const permEl = document.querySelector('input[name="f-perm"]:checked');

  return {
    provider_id:     provEl  ? provEl.value  : "",
    model:           modelEl ? modelEl.value : "",
    permission_mode: permEl  ? permEl.value  : "limited",
    skills,
    disabled_tools:  [...disabled],
  };
}

function confirmDeleteAgent(name) {
  Modal.open({
    title: "DELETE AGENT",
    body: `<div style="padding:8px 0;color:var(--muted)">Delete agent <b style="color:var(--text)">${esc(name)}</b>? This cannot be undone.</div>`,
    footer: `
      <button class="btn" onclick="Modal.close()">Cancel</button>
      <button class="btn danger" id="btn-confirm-del">Delete</button>
    `,
    onOpen() {
      document.getElementById("btn-confirm-del").onclick = async () => {
        try {
          const res = await api.del(`/api/agents/${name}`);
          if (res.ok) {
            toast(`Agent ${name} deleted`, "ok");
            Modal.close();
            await Views.agents.reload();
          } else {
            toast(res.message || "Error", "err");
          }
        } catch (e) { toast("Error: " + e.message, "err"); }
      };
    },
  });
}

// ── modals: task ──────────────────────────────────────────────────────────────

async function openTaskModal(task, tasksView, isRoutine = false) {
  const isNew = !task;
  const tv = tasksView || Views.tasks;
  // if opening from routines, pre-set recurring=true on new task
  if (isNew && isRoutine) task = { recurring: true, cadence: "1d" };

  // fetch agents + projects for selects
  const [agData, prData] = await Promise.all([
    api.get("/api/agents").catch(() => ({ agents: [] })),
    api.get("/api/projects").catch(() => ({ projects: [], active_path: "" })),
  ]);
  const agents   = (agData.agents || []).map(a => a.name);
  const projects = prData.projects || [];
  const defaultProject = tv.selectedProject !== "all" ? tv.selectedProject
    : (prData.active_path || "");

  const isRoutineEdit = !isNew && task.recurring;
  const canTest       = isRoutineEdit && task.agent && task.prompt;
  const isPausedModal = task?.status === "paused";

  Modal.open({
    title: isNew ? "NEW TASK" : `EDIT · ${(task.title||task.name||task.id||"").toUpperCase()}`,
    body: taskFormHtml(task || {}, agents, projects, defaultProject),
    footer: `
      ${!isNew ? `<button class="btn danger" id="btn-del-task">Delete</button>` : ""}
      ${isRoutineEdit ? `<button class="btn" id="btn-modal-toggle-routine">${isPausedModal ? "▶ Activer" : "⏸ Pause"}</button>` : ""}
      <span style="flex:1"></span>
      ${canTest ? `<button class="btn" id="btn-modal-test-routine">▶ Tester</button>` : ""}
      <button class="btn" onclick="Modal.close()">Cancel</button>
      <button class="btn primary" id="btn-save-task">${isNew ? "Create" : "Save"}</button>
    `,
    onOpen() {
      // wire recurring toggle
      const recurringEl = document.getElementById("tf-recurring");
      const cadenceWrap = document.getElementById("tf-cadence-wrap");
      const schedForWrap = document.getElementById("tf-schedfor-wrap");
      if (recurringEl && cadenceWrap) {
        recurringEl.addEventListener("change", () => {
          cadenceWrap.style.display = recurringEl.checked ? "flex" : "none";
          if (schedForWrap) schedForWrap.style.display = recurringEl.checked ? "none" : "block";
        });
      }

      // wire cadence preset → show/hide time picker and custom input
      const cadencePreset = document.getElementById("tf-cadence-preset");
      const cadenceTime   = document.getElementById("tf-cadence-time");
      const cadenceCustom = document.getElementById("tf-cadence-custom");
      if (cadencePreset) {
        cadencePreset.addEventListener("change", () => {
          const v = cadencePreset.value;
          if (cadenceTime)   cadenceTime.style.display   = v === "at_time" ? "block" : "none";
          if (cadenceCustom) cadenceCustom.style.display = v === "custom"  ? "block" : "none";
        });
      }

      document.getElementById("btn-save-task").onclick = async () => {
        const data = readTaskForm();
        if (!data.title) { toast("Title is required", "err"); return; }
        try {
          if (isNew) {
            await api.post("/api/tasks", data);
            toast("Task créée", "ok");
            // aligner le filtre projet sur la tâche créée pour qu'elle soit visible
            if (tv.selectedProject !== undefined) {
              tv.selectedProject = data.project_path === "nouveau" ? "all" : (data.project_path || "all");
            }
          } else {
            await api.patch(`/api/tasks/${task.id}`, data);
            toast("Task sauvegardée", "ok");
          }
          Modal.close();
          await tv.reload();
          if (Views.routines) await Views.routines.reload();
        } catch (e) { toast("Error: " + e.message, "err"); }
      };
      if (!isNew) {
        document.getElementById("btn-del-task").onclick = async () => {
          try {
            await api.del(`/api/tasks/${task.id}`);
            toast("Task supprimée", "ok");
            Modal.close();
            await tv.reload();
          } catch (e) { toast("Error: " + e.message, "err"); }
        };
      }

      if (isRoutineEdit) {
        document.getElementById("btn-modal-toggle-routine").onclick = async e => {
          const btn = e.currentTarget;
          btn.disabled = true;
          try {
            const newStatus = isPausedModal ? "queued" : "paused";
            await api.patch(`/api/routines/${encodeURIComponent(task.id)}`, { status: newStatus });
            toast(newStatus === "paused" ? "Routine mise en pause" : "Routine activée", "ok");
            Modal.close();
            await Views.routines.reload();
          } catch (err) {
            toast("Erreur : " + err.message, "err");
            btn.disabled = false;
          }
        };
      }

      if (canTest) {
        document.getElementById("btn-modal-test-routine").onclick = async e => {
          const btn = e.currentTarget;
          btn.disabled = true;
          btn.textContent = "Envoi…";
          try {
            const res = await api.post(`/api/tasks/${encodeURIComponent(task.id)}/launch`, {});
            if (!res.ok) throw new Error(res.error || "test failed");
            toast(`Test lancé → ${task.agent}`, "ok");
            Modal.close();
            ChatPanel.open({ name: task.agent });
            await Views.routines.reload();
          } catch (err) {
            toast("Erreur : " + err.message, "err");
          } finally {
            btn.disabled = false;
            btn.textContent = "▶ Tester";
          }
        };
      }
    },
  });
}

function taskFormHtml(t, agents, projects, defaultProject) {
  const statuses   = ["backlog","queued","running","failed","done"];
  const priorities = ["high","med","low"];
  const curProject = t.project_path || t.project || defaultProject || "";
  const curAgent   = t.agent || "";

  const agentOptions = agents.length
    ? `<option value="">— aucun —</option>` + agents.map(a =>
        `<option value="${esc(a)}" ${a===curAgent?"selected":""}>${esc(a)}</option>`).join("")
    : `<option value="${esc(curAgent)}">${esc(curAgent||"—")}</option>`;

  const newProjectOption = `<option value="nouveau" ${curProject==="nouveau"?"selected":""}>Nouveau projet</option>`;
  const projectOptions = projects.length
    ? `<option value="">— aucun —</option>${newProjectOption}` + projects.map(p =>
        `<option value="${esc(p.path)}" ${p.path===curProject?"selected":""}>${esc(p.name)}</option>`).join("")
    : `<option value="">— aucun —</option>${newProjectOption}`;

  // events timeline
  const eventsHtml = (t.events || []).length ? `
    <div class="form-row">
      <label class="form-label">HISTORIQUE</label>
      <div class="task-events">${_renderEvents(t.events)}</div>
    </div>` : "";

  const isRecurring = t.recurring || false;

  return `
    <div class="form-row">
      <label class="form-label">TITRE</label>
      <input class="form-input" id="tf-title" value="${esc(t.title||"")}" placeholder="Que faut-il faire ?">
    </div>
    <div class="form-row-2">
      <div class="form-row">
        <label class="form-label">STATUT</label>
        <select class="form-select" id="tf-status">
          ${statuses.map(s => `<option value="${s}" ${(t.status||"backlog")===s?"selected":""}>${s.toUpperCase()}</option>`).join("")}
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">PRIORITÉ</label>
        <select class="form-select" id="tf-priority">
          ${priorities.map(p => `<option value="${p}" ${(t.priority||"med")===p?"selected":""}>${p.toUpperCase()}</option>`).join("")}
        </select>
      </div>
    </div>
    <div class="form-row-2">
      <div class="form-row">
        <label class="form-label">AGENT</label>
        <select class="form-select" id="tf-agent">${agentOptions}</select>
      </div>
      <div class="form-row">
        <label class="form-label">PROJET</label>
        <select class="form-select" id="tf-project">${projectOptions}</select>
      </div>
    </div>

    <div class="form-row">
      <label class="form-label">RÉCURRENCE</label>
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <label class="toggle-wrap" style="margin:0">
          <input type="checkbox" id="tf-recurring" class="toggle-input" ${isRecurring?"checked":""}>
          <span class="toggle-slider"></span>
        </label>
        <div id="tf-cadence-wrap" style="display:${isRecurring?"flex":"none"};gap:8px;align-items:center;flex:1;flex-wrap:wrap">
          ${_cadenceSelectHtml(t.cadence||"")}
        </div>
      </div>
    </div>

    <div class="form-row" id="tf-schedfor-wrap" style="${isRecurring ? "display:none" : "display:block"}">
      <label class="form-label">DATE/HEURE DE LANCEMENT <span style="color:var(--dim);font-weight:normal">— optionnel</span></label>
      <input type="datetime-local" class="form-input" id="tf-scheduled-for" value="${esc(_toDatetimeLocal(t.scheduled_for||""))}">
    </div>

    <div class="form-row">
      <label class="form-label">PROMPT / PLAN <span style="color:var(--dim);font-weight:normal">— source unique envoyée au gateway</span></label>
      <textarea class="form-textarea" id="tf-prompt" style="min-height:180px" placeholder="Instruction exécutable, contexte, critères d'acceptation, hors scope…">${esc(t.prompt||"")}</textarea>
    </div>
    ${eventsHtml}
  `;
}

function _renderEvents(events) {
  const icons = {
    created:        "✦",
    status_changed: "→",
    planning_requested: "◇",
    launched:       "▶",
    retry_scheduled:"↻",
    launch_failed:  "!",
    comment:        "◆",
  };
  return [...events].reverse().map(e => {
    const icon = icons[e.kind] || "·";
    let label = "";
    if (e.kind === "created")        label = `Créée`;
    if (e.kind === "status_changed") label = `${esc(e.from)} → <b>${esc(e.to)}</b>`;
    if (e.kind === "planning_requested") label = `Cadrage demandé via <b>${esc(e.agent)}</b>`;
    if (e.kind === "launched")       label = `Lancée via <b>${esc(e.agent)}</b>`;
    if (e.kind === "retry_scheduled") label = `Retry ${esc(e.attempts || "")}${e.next_attempt_at ? ` · ${esc(_missionAge(e.next_attempt_at))}` : ""}`;
    if (e.kind === "launch_failed")  label = `Échec lancement${e.error ? ` · ${esc(e.error)}` : ""}`;
    if (e.kind === "comment")        label = esc(e.text);
    const ago = _missionAge(e.at);
    return `<div class="task-event"><span class="task-event-icon">${icon}</span><span class="task-event-label">${label}</span><span class="task-event-time">${ago}</span></div>`;
  }).join("");
}

const _CADENCE_PRESETS = [
  { value: "at_time", label: "Chaque jour à…" },
  { value: "1d",      label: "Chaque jour" },
  { value: "hourly",  label: "Toutes les heures" },
  { value: "4h",      label: "Toutes les 4h" },
  { value: "6h",      label: "Toutes les 6h" },
  { value: "12h",     label: "Toutes les 12h" },
  { value: "weekly",  label: "Chaque semaine" },
  { value: "custom",  label: "Personnalisé…" },
];

function _parseCadencePreset(cadence) {
  if (!cadence) return { preset: "1d", time: "08:00", custom: "" };
  if (/^\d{2}:\d{2}$/.test(cadence)) return { preset: "at_time", time: cadence, custom: "" };
  const known = _CADENCE_PRESETS.map(p => p.value).filter(v => v !== "at_time" && v !== "custom");
  if (known.includes(cadence)) return { preset: cadence, time: "08:00", custom: "" };
  return { preset: "custom", time: "08:00", custom: cadence };
}

function _cadenceSelectHtml(cadence) {
  const { preset, time, custom } = _parseCadencePreset(cadence);
  const opts = _CADENCE_PRESETS.map(p =>
    `<option value="${p.value}"${preset === p.value ? " selected" : ""}>${p.label}</option>`
  ).join("");
  return `
    <select class="form-select" id="tf-cadence-preset" style="flex:1;min-width:160px">${opts}</select>
    <input type="time" id="tf-cadence-time" class="form-input"
      value="${esc(time)}"
      style="width:110px;display:${preset==="at_time"?"block":"none"}">
    <input class="form-input" id="tf-cadence-custom"
      value="${esc(custom)}"
      placeholder="ex : 30m · 2h · 3d"
      style="flex:1;display:${preset==="custom"?"block":"none"}">
  `;
}

function _readCadence() {
  const preset = document.getElementById("tf-cadence-preset")?.value || "1d";
  if (preset === "at_time") return document.getElementById("tf-cadence-time")?.value || "08:00";
  if (preset === "custom")  return document.getElementById("tf-cadence-custom")?.value.trim() || "";
  return preset;
}

function readTaskForm() {
  const recurring = document.getElementById("tf-recurring")?.checked || false;
  return {
    title:         val("tf-title"),
    prompt:        val("tf-prompt"),
    status:        val("tf-status")   || "backlog",
    priority:      val("tf-priority") || "med",
    agent:         val("tf-agent"),
    project_path:  val("tf-project"),
    recurring,
    cadence:       recurring ? _readCadence() : "",
    scheduled_for: recurring ? "" : _fromDatetimeLocal(val("tf-scheduled-for")),
  };
}

function _toDatetimeLocal(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function _fromDatetimeLocal(value) {
  if (!value) return "";
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    return new Date(value).toISOString();
  }
  return value;
}

// ── routine context menu ──────────────────────────────────────────────────────

function openRoutineMenu(r) {
  const isPaused = r.status === "paused";
  Modal.open({
    title: `ROUTINE · ${(r.name||"").toUpperCase()}`,
    body: `
      <div style="color:var(--muted);font-size:11px;margin-bottom:12px">
        ${r.last_error ? `<div style="color:var(--red);margin-bottom:8px">Error: ${esc(r.last_error)}</div>` : ""}
        Status: <b style="color:var(--text)">${esc(r.status)}</b> &nbsp;·&nbsp;
        Agent: <b style="color:var(--text)">${esc(r.agent||"—")}</b> &nbsp;·&nbsp;
        Last: ${esc(r.last_run_human)} &nbsp;·&nbsp; Next: ${esc(r.next_run_human)}
      </div>
      <div class="form-row" style="margin-bottom:0">
        <label class="form-label">PROMPT</label>
        <input class="form-input" id="f-routine-prompt" value="${esc(r.prompt||"")}" placeholder="ex : /dream">
      </div>
    `,
    footer: `
      <button class="btn" id="btn-toggle-routine">${isPaused ? "Resume" : "Pause"}</button>
      <span style="flex:1"></span>
      <button class="btn primary" id="btn-save-routine">Save</button>
      <button class="btn danger" id="btn-delete-routine">Delete</button>
      <button class="btn" onclick="Modal.close()">Close</button>
    `,
    onOpen() {
      document.getElementById("btn-toggle-routine").onclick = async () => {
        const newStatus = isPaused ? "queued" : "paused";
        try {
          const res = await api.patch(`/api/routines/${r.id}`, { status: newStatus });
          if (res.ok) {
            toast(`Routine ${newStatus}`, "ok");
            Modal.close();
            await Views.routines.reload();
          } else {
            toast(res.message || "Error", "err");
          }
        } catch (e) { toast("Error: " + e.message, "err"); }
      };

      document.getElementById("btn-save-routine").onclick = async () => {
        const prompt = document.getElementById("f-routine-prompt").value.trim();
        try {
          const res = await api.patch(`/api/routines/${r.id}`, { prompt });
          if (res.ok) {
            toast("Prompt sauvegardé", "ok");
            Modal.close();
            await Views.routines.reload();
          } else {
            toast(res.message || "Error", "err");
          }
        } catch (e) { toast("Error: " + e.message, "err"); }
      };

      const btnDel = document.getElementById("btn-delete-routine");
      btnDel.onclick = () => {
        if (btnDel.dataset.confirm) {
          api.del(`/api/routines/${r.id}`).then(res => {
            if (res.ok) {
              toast("Routine supprimée", "ok");
              Modal.close();
              Views.routines.reload();
            } else {
              toast(res.message || "Error", "err");
            }
          }).catch(e => toast("Error: " + e.message, "err"));
        } else {
          btnDel.textContent = "Confirm?";
          btnDel.dataset.confirm = "1";
          setTimeout(() => { btnDel.textContent = "Delete"; delete btnDel.dataset.confirm; }, 3000);
        }
      };
    },
  });
}

// ── utils ─────────────────────────────────────────────────────────────────────

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function val(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : "";
}

function normalizeAgentName(name) {
  return String(name ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 64);
}

function isValidAgentName(name) {
  return /^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(String(name ?? ""));
}

// ── boot ──────────────────────────────────────────────────────────────────────

document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => navigate(btn.dataset.view);
});

// ── provider defaults (registry mirrors) ─────────────────────────────────────
// 3 connection types → maps to (provider kind, auth_type, fields shown)
const _CONN_TYPES = {
  api:          { label: "OpenAI API",     hint: "OpenAI-compatible avec /v1",                 kind: "openai", needsKey: true  },
  ollama_cloud: { label: "Ollama Cloud",   hint: "API distante Ollama avec clé",                kind: "ollama", needsKey: true  },
  local:        { label: "Ollama local",   hint: "Modèle local, pas de clé",                    kind: "ollama", needsKey: false },
  oauth:        { label: "OAuth",          hint: "ChatGPT via abonnement",                      kind: "openai", needsKey: false },
};

function _provConnType(p) {
  if (p.auth_type === "auth") return "oauth";
  const kind = String(p.provider).toLowerCase();
  const baseUrl = String(p.base_url || "").toLowerCase();
  if (kind.includes("ollama")) {
    if (p.has_api_key || baseUrl.includes("ollama.com")) return "ollama_cloud";
    return "local";
  }
  return "api";
}

function _providersListHtml(providers) {
  if (!providers.length) {
    return `<div style="color:var(--dim);font-size:12px;padding:6px 0">Aucun provider configuré.</div>`;
  }
  return providers.map(p => {
    const ct = _provConnType(p);
    const ctLabel = _CONN_TYPES[ct]?.label || ct;
    return `
    <div class="provider-row" data-id="${esc(p.id)}">
      <span class="provider-dot"></span>
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:13px;color:var(--text)">${esc(p.name)}</span>
          <span style="font-size:10px;padding:1px 6px;border:1px solid var(--border-hi);border-radius:2px;color:var(--dim)">${esc(ctLabel)}</span>
        </div>
        <div style="font-size:11px;color:var(--dim);margin-top:2px">${esc(p.model || "—")}</div>
      </div>
      <button class="icon-btn provider-edit"
        data-id="${esc(p.id)}" data-name="${esc(p.name)}" data-ct="${ct}"
        data-url="${esc(p.base_url || "")}" data-model="${esc(p.model || "")}">edit</button>
      <button class="icon-btn danger provider-del"
        data-id="${esc(p.id)}" data-name="${esc(p.name)}">del</button>
    </div>`;
  }).join("");
}

const FolderPicker = (() => {
  const overlay  = document.getElementById("fp-overlay");
  const content  = document.getElementById("fp-content");
  let _selected  = "";
  let _onSelect  = null;

  document.getElementById("fp-close").onclick  = close;
  document.getElementById("fp-cancel").onclick = close;
  document.getElementById("fp-confirm").onclick = () => {
    close();
    if (_onSelect) _onSelect(_selected);
  };

  function close() { overlay.classList.add("hidden"); }

  async function render(path) {
    let d;
    try { d = await api.get(`/api/browse?path=${encodeURIComponent(path)}`); } catch {}
    if (!d || typeof d !== "object") d = { ok: false, error: "Réponse invalide" };

    _selected = d.path || path;

    const parts = (d.path || "").split("/").filter(Boolean);
    const crumbs = [{ label: "/", path: "/" }].concat(
      parts.map((p, i) => ({ label: p, path: "/" + parts.slice(0, i + 1).join("/") }))
    );

    content.innerHTML = `
      <div class="fp-crumbs">
        ${crumbs.map((b, i) => `
          <button class="nav-btn fp-crumb" data-path="${esc(b.path)}" style="font-size:11px;padding:2px 7px">${esc(b.label)}</button>
          ${i < crumbs.length - 1 ? '<span style="color:var(--dim)">/</span>' : ""}
        `).join("")}
      </div>
      ${d.ok === false ? `<div style="color:var(--err);font-size:12px;margin-bottom:8px">${esc(d.error || "Erreur")}</div>` : ""}
      <div id="fp-list">
        ${d.parent != null ? `<button class="fp-dir-btn" data-path="${esc(d.parent)}" data-enter="1" style="color:var(--dim)">↑ dossier parent</button>` : ""}
        ${(d.dirs || []).map(name => {
          const full = (d.path || "").replace(/\/$/, "") + "/" + name;
          return `<button class="fp-dir-btn" data-path="${esc(full)}">📁 ${esc(name)}</button>`;
        }).join("")}
        ${!(d.dirs || []).length && d.ok !== false ? `<div style="padding:12px 14px;color:var(--dim);font-size:12px">Dossier vide</div>` : ""}
      </div>
      <div style="margin-top:12px;font-size:11px;color:var(--dim)">Sélectionné :</div>
      <div id="fp-selected" style="font-size:12px;color:var(--accent);margin-top:4px;word-break:break-all">${esc(_selected)}</div>
    `;

    content.querySelectorAll(".fp-crumb").forEach(btn => {
      btn.onclick = () => render(btn.dataset.path);
    });
    content.querySelectorAll(".fp-dir-btn").forEach(btn => {
      if (btn.dataset.enter) { btn.onclick = () => render(btn.dataset.path); return; }
      btn.onclick = () => {
        _selected = btn.dataset.path;
        document.getElementById("fp-selected").textContent = _selected;
        content.querySelectorAll(".fp-dir-btn").forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
      };
      btn.ondblclick = () => render(btn.dataset.path);
    });
  }

  async function open(onSelect) {
    _onSelect = onSelect;
    _selected = "";
    overlay.classList.remove("hidden");
    let startPath = "";
    try { const h = await api.get("/api/browse?path=~"); startPath = h?.path || ""; } catch {}
    render(startPath);
  }

  return { open };
})();

function openFolderPicker(onSelect) { FolderPicker.open(onSelect); }

document.getElementById("btn-settings").onclick = async () => {
  const [cfgData, provData, rootsData] = await Promise.all([
    api.get("/api/config").catch(() => ({})),
    api.get("/api/providers").catch(() => ({ providers: [] })),
    api.get("/api/allow-roots").catch(() => ({ roots: [] })),
  ]);
  const cfg       = cfgData;
  const providers = provData.providers || [];
  let   roots     = rootsData.roots || [];

  Modal.open({
    title: "SETTINGS",
    body: `
      <div class="form-row" style="margin-top:4px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
          <label class="form-label" style="margin:0">PROVIDERS</label>
          <button class="nav-btn" id="pf-add-btn" style="font-size:11px;padding:3px 10px">+ Ajouter</button>
        </div>
        <div id="providers-list">${_providersListHtml(providers)}</div>

        <div id="pf-wrap" style="display:none;margin-top:12px;border:1px solid var(--border);border-radius:4px;padding:16px">
          <div style="display:flex;align-items:center;margin-bottom:16px">
            <span style="font-size:11px;letter-spacing:.1em;color:var(--muted)" id="pf-title">NOUVEAU PROVIDER</span>
            <span style="flex:1"></span>
            <button class="icon-btn" id="pf-cancel">✕</button>
          </div>

          <!-- 1. Type de connexion -->
          <div class="form-row" id="pf-type-row" style="margin-bottom:14px">
            <label class="form-label">TYPE DE CONNEXION</label>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              ${Object.entries(_CONN_TYPES).map(([k, t]) => `
                <label class="perm-option pf-conn-option${k==="api"?" active":""}" id="pf-ct-${k}" data-ct="${k}" role="radio" aria-checked="${k==="api"?"true":"false"}" tabindex="0" title="${t.hint}">
                  <input type="radio" name="pf-ct" value="${k}" ${k==="api"?"checked":""} style="display:none">
                  <span>${t.label}</span>
                </label>`).join("")}
            </div>
          </div>

          <!-- 2. OAuth notice (read-only when creating, model-only when editing) -->
          <div id="pf-oauth-notice" style="display:none;margin-bottom:12px;padding:10px 12px;background:var(--card);border-radius:4px;font-size:12px;color:var(--muted);line-height:1.7">
            La connexion OAuth (ChatGPT via abonnement) nécessite un flow navigateur.<br>
            Créez ce provider depuis le terminal : <code style="color:var(--accent)">marius add provider</code><br>
            <span id="pf-oauth-edit-hint" style="display:none">En mode édition, vous pouvez modifier le nom et changer de modèle.</span>
          </div>

          <!-- 3. Champs communs (nom + url) -->
          <div id="pf-fields-common" style="margin-bottom:12px">
            <div class="form-row-2">
              <div>
                <label class="form-label">NOM</label>
                <input class="form-input" id="pf-name" placeholder="ex: anthropic-api">
              </div>
              <div id="pf-url-col">
                <label class="form-label">BASE URL</label>
                <input class="form-input" id="pf-url" value="https://api.openai.com/v1">
              </div>
            </div>
          </div>

          <!-- 4. Clé API (API seulement) -->
          <div id="pf-key-row" class="form-row" style="margin-bottom:12px">
            <label class="form-label">CLEF API</label>
            <input class="form-input" id="pf-key" type="password" placeholder="sk-… / ollama_…" autocomplete="new-password">
            <div style="margin-top:4px;font-size:11px;color:var(--dim)" id="pf-key-hint">OpenAI-compatible avec clef API.</div>
          </div>

          <!-- 5. Modèle -->
          <div id="pf-model-row" class="form-row" style="margin-bottom:14px">
            <label class="form-label">MODÈLE</label>
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
              <select class="form-select" id="pf-model-sel" style="flex:1">
                <option value="">— cliquez Charger pour voir les modèles disponibles —</option>
              </select>
              <button class="nav-btn" id="pf-fetch" style="white-space:nowrap;flex-shrink:0">⟳ Charger</button>
            </div>
            <input class="form-input" id="pf-model-manual" placeholder="Ou saisir le nom du modèle manuellement" style="display:none">
            <button style="background:none;border:none;color:var(--dim);font-size:11px;cursor:pointer;padding:0;font-family:var(--font)" id="pf-manual-toggle">Saisir manuellement</button>
          </div>

          <button class="nav-btn primary" id="pf-submit">CRÉER</button>
        </div>
      </div>

      <div class="form-row" style="margin-top:4px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
          <label class="form-label" style="margin:0">DOSSIERS AUTORISÉS</label>
        </div>
        <div id="roots-list"></div>
        <div style="display:flex;gap:8px;margin-top:10px">
          <input class="form-input" id="roots-input" placeholder="/home/user/projets" style="flex:1">
          <button class="nav-btn" id="roots-browse-btn" title="Parcourir" style="font-size:14px;padding:3px 9px;flex-shrink:0">📁</button>
          <button class="nav-btn" id="roots-add-btn" style="font-size:11px;padding:3px 10px;flex-shrink:0">+ Ajouter</button>
        </div>
        <div style="margin-top:5px;font-size:11px;color:var(--dim)">
          Racines de confiance — un dossier parent couvre tous ses sous-projets
        </div>
      </div>

      <div class="form-row" style="margin-top:4px">
        <label class="form-label">AGENT ADMIN</label>
        <div style="font-size:13px;color:var(--muted)">${esc(cfg.main_agent || "—")}
          <span style="color:var(--dim);margin-left:8px">${cfg.agent_count} agent(s) configuré(s)</span>
        </div>
      </div>
    `,
    footer: `
      <span style="flex:1"></span>
      <button class="btn primary" id="btn-save-settings" onclick="Modal.close()">Fermer</button>
    `,
    onOpen() {
      let _pfEditId = null;

      // ── connection type switching ──────────────────────────────────────
      const DEFAULT_URLS = {
        api:          "https://api.openai.com/v1",
        ollama_cloud: "https://ollama.com",
        local:        "http://localhost:11434",
      };

      const pfSelectedCt = () => {
        const active = document.querySelector(".pf-conn-option.active input[name='pf-ct']");
        if (active?.value) return active.value;
        return document.querySelector("input[name='pf-ct']:checked")?.value || "api";
      };

      const pfApplyCt = (ct, isEdit = false) => {
        Object.keys(_CONN_TYPES).forEach(k => {
          const el = document.getElementById(`pf-ct-${k}`);
          if (!el) return;
          el.classList.toggle("active", k === ct);
          el.setAttribute("aria-checked", k === ct ? "true" : "false");
        });
        const checked = document.querySelector(`input[name="pf-ct"][value="${ct}"]`);
        if (checked) checked.checked = true;

        const isOauth = ct === "oauth";
        const isLocal = ct === "local";
        const needsKey = !!_CONN_TYPES[ct]?.needsKey;

        // OAuth: in edit mode show only a small badge, no CLI message
        document.getElementById("pf-oauth-notice").style.display   = isOauth && !isEdit ? "" : "none";
        document.getElementById("pf-oauth-edit-hint").style.display = "none";
        document.getElementById("pf-fields-common").style.display  = (!isOauth || isEdit) ? "" : "none";
        document.getElementById("pf-url-col").style.display        = isOauth ? "none" : "";
        document.getElementById("pf-key-row").style.display        = (!isOauth && needsKey) ? "" : "none";
        document.getElementById("pf-model-row").style.display      = (!isOauth || isEdit) ? "" : "none";
        document.getElementById("pf-submit").style.display         = isOauth && !isEdit ? "none" : "";
        document.getElementById("pf-key-hint").textContent = ct === "ollama_cloud"
          ? "Clef API Ollama Cloud. Base URL attendue : https://ollama.com"
          : "OpenAI-compatible avec clef API.";

        const urlEl = document.getElementById("pf-url");
        if (!urlEl.dataset.userEdited && !isEdit) {
          urlEl.value = DEFAULT_URLS[ct] || DEFAULT_URLS.api;
        }
      };

      document.querySelectorAll(".pf-conn-option").forEach(label => {
        const input = label.querySelector("input[name='pf-ct']");
        const apply = event => {
          event?.preventDefault();
          if (!input) return;
          const next = label.dataset.ct || input.value;
          const current = pfSelectedCt();
          const urlEl = document.getElementById("pf-url");
          if (urlEl && urlEl.value.trim() === (DEFAULT_URLS[current] || "")) {
            delete urlEl.dataset.userEdited;
          }
          pfApplyCt(next, !!_pfEditId);
        };
        label.addEventListener("click", apply);
        label.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") apply(event);
        });
        input?.addEventListener("change", () => pfApplyCt(input.value, !!_pfEditId));
      });
      document.getElementById("pf-url")?.addEventListener("input", e =>
        { e.target.dataset.userEdited = "1"; });

      // ── show / hide form ───────────────────────────────────────────────
      const showForm = (prefill = null) => {
        _pfEditId = prefill?.id || null;
        const ct  = prefill?.ct || "api";
        const isEdit = !!_pfEditId;

        document.getElementById("pf-title").textContent    = isEdit ? "MODIFIER PROVIDER" : "NOUVEAU PROVIDER";
        document.getElementById("pf-submit").textContent   = isEdit ? "METTRE À JOUR" : "CRÉER";
        document.getElementById("pf-type-row").style.display = isEdit ? "none" : "";

        document.getElementById("pf-name").value = prefill?.name || "";
        const urlEl = document.getElementById("pf-url");
        delete urlEl.dataset.userEdited;
        if (isEdit) {
          urlEl.value = prefill?.url || "";
          urlEl.dataset.userEdited = "1";
        } else {
          urlEl.value = "";
        }
        pfApplyCt(ct, isEdit);
        document.getElementById("pf-key").value = "";

        // Reset model select
        const sel = document.getElementById("pf-model-sel");
        sel.innerHTML = `<option value="">Chargement…</option>`;
        document.getElementById("pf-model-manual").style.display = "none";
        document.getElementById("pf-model-manual").value = prefill?.model || "";
        document.getElementById("pf-wrap").style.display = "";
        document.getElementById("pf-wrap").scrollIntoView({ behavior: "smooth", block: "nearest" });

        // Auto-fetch models for existing providers
        if (isEdit && prefill?.id) {
          api.get(`/api/providers/${encodeURIComponent(prefill.id)}/models`)
            .then(res => {
              const models = res?.models || [];
              const cur    = prefill?.model || "";
              if (models.length) {
                sel.innerHTML = models.map(m =>
                  `<option value="${esc(m)}" ${m === cur ? "selected" : ""}>${esc(m)}</option>`
                ).join("");
              } else {
                sel.innerHTML = `<option value="${esc(cur)}" selected>${esc(cur || "—")}</option>`;
                if (res?.error) toast(res.error, "err");
              }
            })
            .catch(() => {
              const cur = prefill?.model || "";
              sel.innerHTML = `<option value="${esc(cur)}" selected>${esc(cur || "—")}</option>`;
            });
        } else {
          sel.innerHTML = `<option value="">— cliquez Charger pour voir les modèles disponibles —</option>`;
        }
      };

      const hideForm = () => { _pfEditId = null; document.getElementById("pf-wrap").style.display = "none"; };

      document.getElementById("pf-add-btn").onclick = () => showForm(null);
      document.getElementById("pf-cancel").onclick  = hideForm;

      // ── manual model toggle ────────────────────────────────────────────
      document.getElementById("pf-manual-toggle").onclick = () => {
        const manEl = document.getElementById("pf-model-manual");
        const shown = manEl.style.display !== "none";
        manEl.style.display = shown ? "none" : "";
        document.getElementById("pf-manual-toggle").textContent = shown ? "Saisir manuellement" : "Utiliser la liste";
      };

      // ── fetch models ───────────────────────────────────────────────────
      const pfGetModel = () => {
        const manual = document.getElementById("pf-model-manual").value.trim();
        if (manual) return manual;
        const sel = document.getElementById("pf-model-sel");
        return sel.value || "";
      };

      document.getElementById("pf-fetch").onclick = async () => {
        const ct = pfSelectedCt();
        const btn = document.getElementById("pf-fetch");
        btn.disabled = true; btn.textContent = "…";
        try {
          let models = [];
          if (_pfEditId) {
            // Edit: use stored credentials via provider models endpoint
            const res = await api.get(`/api/providers/${encodeURIComponent(_pfEditId)}/models`);
            models = res.models || [];
            if (res.error) toast(res.error, "err");
          } else {
            // Create: use probe
            const kind    = _CONN_TYPES[ct]?.kind || "openai";
            const base_url = document.getElementById("pf-url").value.trim();
            const api_key  = document.getElementById("pf-key").value.trim();
            const res = await api.post("/api/providers/probe", { provider: kind, base_url, api_key });
            models = res.models || [];
            if (!models.length) toast(res.error || "Aucun modèle trouvé", "err");
          }
          if (models.length) {
            const sel = document.getElementById("pf-model-sel");
            const cur = pfGetModel();
            sel.innerHTML = models.map(m =>
              `<option value="${esc(m)}" ${m===cur?"selected":""}>${esc(m)}</option>`).join("");
            if (!cur && models[0]) {/* first is auto-selected by browser */}
            toast(`${models.length} modèle(s) disponibles`, "ok");
          }
        } catch (e) { toast("Fetch failed: " + e.message, "err"); }
        finally { btn.disabled = false; btn.textContent = "⟳ Charger"; }
      };

      // ── create / update ────────────────────────────────────────────────
      document.getElementById("pf-submit").onclick = async () => {
        const ct      = pfSelectedCt();
        const name    = document.getElementById("pf-name").value.trim();
        const base_url = document.getElementById("pf-url").value.trim();
        const api_key  = document.getElementById("pf-key").value.trim();
        const model   = pfGetModel();
        if (!model) { toast("Modèle requis — chargez la liste ou saisissez manuellement", "err"); return; }
        try {
          let res;
          if (_pfEditId) {
            res = await api.put(`/api/providers/${encodeURIComponent(_pfEditId)}`,
              { name, base_url: base_url || undefined, api_key: api_key || undefined, model });
          } else {
            const kind = _CONN_TYPES[ct]?.kind || "openai";
            res = await api.post("/api/providers", { provider: kind, name, base_url, api_key, model });
          }
          if (!res.ok) { toast(res.message || "Erreur", "err"); return; }
          toast(_pfEditId ? "Provider mis à jour" : "Provider ajouté", "ok");
          hideForm();
          const fresh = await api.get("/api/providers").catch(() => ({ providers: [] }));
          document.getElementById("providers-list").innerHTML = _providersListHtml(fresh.providers || []);
          _wireProviderBtns();
        } catch (e) { toast("Erreur: " + e.message, "err"); }
      };

      // ── delete + edit buttons ─────────────────────────────────────────
      const _wireProviderBtns = () => {
        document.querySelectorAll(".provider-del").forEach(btn => {
          btn.onclick = async () => {
            const id = btn.dataset.id, name = btn.dataset.name;
            if (!confirm(`Supprimer le provider "${name}" ?`)) return;
            try {
              const res = await api.del(`/api/providers/${encodeURIComponent(id)}`);
              if (res.ok) { btn.closest(".provider-row").remove(); toast(`Provider ${name} supprimé`, "ok"); }
              else toast(res.message || "Erreur", "err");
            } catch (e) { toast("Erreur: " + e.message, "err"); }
          };
        });
        document.querySelectorAll(".provider-edit").forEach(btn => {
          btn.onclick = () => showForm({
            id: btn.dataset.id, name: btn.dataset.name,
            ct: btn.dataset.ct, url: btn.dataset.url, model: btn.dataset.model,
          });
        });
      };
      _wireProviderBtns();

      // ── allowed roots ──────────────────────────────────────────────────
      const _renderRoots = () => {
        const el = document.getElementById("roots-list");
        if (!el) return;
        if (!roots.length) {
          el.innerHTML = `<div style="font-size:12px;color:var(--dim);padding:4px 0">Aucune racine configurée.</div>`;
          return;
        }
        el.innerHTML = roots.map(r => `
          <div class="proj-row" data-path="${esc(r.path)}" style="align-items:flex-start">
            <div style="flex:1;min-width:0">
              <div class="proj-row-path">${esc(r.path)}</div>
              ${r.reason && r.reason !== "dashboard" ? `<div style="font-size:11px;color:var(--dim);margin-top:2px">${esc(r.reason)}</div>` : ""}
            </div>
            <button class="icon-btn roots-del-btn" data-path="${esc(r.path)}" title="Retirer" style="flex-shrink:0;margin-left:8px">✕</button>
          </div>`).join("");
        el.querySelectorAll(".roots-del-btn").forEach(btn => {
          btn.onclick = async () => {
            const path = btn.dataset.path;
            try {
              const res = await api.del("/api/allow-roots", { path });
              if (res.ok) {
                roots = roots.filter(r => r.path !== path);
                _renderRoots();
                toast("Racine retirée", "ok");
              } else toast(res.message || "Erreur", "err");
            } catch (e) { toast("Erreur : " + e.message, "err"); }
          };
        });
      };
      _renderRoots();

      document.getElementById("roots-add-btn").onclick = async () => {
        const input = document.getElementById("roots-input");
        const path = input.value.trim();
        if (!path) return;
        try {
          const res = await api.post("/api/allow-roots", { path, reason: "dashboard" });
          if (res.ok) {
            roots.push({ path, reason: "dashboard", added_at: "" });
            input.value = "";
            _renderRoots();
            toast("Dossier autorisé", "ok");
          } else toast(res.message || "Erreur", "err");
        } catch (e) { toast("Erreur : " + e.message, "err"); }
      };
      document.getElementById("roots-input").addEventListener("keydown", e => {
        if (e.key === "Enter") document.getElementById("roots-add-btn").click();
      });
      document.getElementById("roots-browse-btn").onclick = () => {
        openFolderPicker(path => {
          document.getElementById("roots-input").value = path;
        });
      };

      // ── save settings ──────────────────────────────────────────────────
      document.getElementById("btn-save-settings").onclick = () => {
        Modal.close();
      };
    },
  });
};

document.getElementById("btn-chat").onclick = async () => {
  const overlay = document.getElementById("chat-overlay");
  if (!overlay.classList.contains("hidden")) {
    ChatPanel.close();
    return;
  }
  try {
    const d = await api.get("/api/agents");
    const agents = d.agents || [];
    if (!agents.length) { toast("Aucun agent configuré", "err"); return; }
    const agent = agents.find(a => a.running) || agents.find(a => a.is_admin) || agents[0];
    ChatPanel.open({ name: agent.name });
  } catch (e) { toast("Erreur : " + e.message, "err"); }
};

const initial = location.hash.replace("#", "") || "agents";
navigate(initial);
