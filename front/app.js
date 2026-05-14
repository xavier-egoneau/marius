/* Marius Dashboard — vanilla JS, no build step */
"use strict";

const API_BASE = "";   // same origin

// ── API ───────────────────────────────────────────────────────────────────────

const api = {
  async get(path) {
    const r = await fetch(API_BASE + path);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(API_BASE + path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  async patch(path, body) {
    const r = await fetch(API_BASE + path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  async del(path) {
    const r = await fetch(API_BASE + path, { method: "DELETE" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
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
      ${agent.last_session ? `
        <div class="panel-section">
          <div class="panel-label">DERNIÈRE SESSION</div>
          <div class="panel-value">${esc(agent.last_session)}</div>
        </div>` : ""}
    `;

    document.getElementById("panel-footer").innerHTML = `
      <button class="btn primary" id="btn-panel-chat">Ouvrir le chat</button>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button class="btn" id="btn-panel-edit" style="flex:1">Éditer</button>
        ${!agent.is_admin ? `<button class="btn danger" id="btn-panel-del">Del</button>` : ""}
      </div>
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

  return { open, close };
})();

// ── ChatPanel ────────────────────────────────────────────────────────────────

const ChatPanel = (() => {
  const overlay   = document.getElementById("chat-overlay");
  const frame     = document.getElementById("chat-frame");
  const loading   = document.getElementById("chat-loading");
  const loadingMsg = document.getElementById("chat-loading-msg");
  const statusDot = document.getElementById("chat-status-dot");
  const statusMsg = document.getElementById("chat-status-msg");

  document.getElementById("chat-close").onclick = close;
  let _chatMdOutside = false;
  let _draft = "";
  let _syncTimer = null;
  overlay.addEventListener("mousedown", e => {
    const panel = document.getElementById("chat-panel");
    _chatMdOutside = panel ? !panel.contains(e.target) : true;
  });
  overlay.addEventListener("mouseup", e => {
    const panel = document.getElementById("chat-panel");
    if (_chatMdOutside && panel && !panel.contains(e.target)) close();
  });

  async function open(agent, opts = {}) {
    _draft = opts.draft || "";
    document.getElementById("chat-agent-name").textContent = agent.name.toUpperCase();
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
      frame.src = _draft ? `${res.url}#draft=${encodeURIComponent(_draft)}` : res.url;
      frame.onload = () => {
        loading.classList.add("hidden");
        frame.style.display = "block";
        if (_draft) {
          injectDraft();
          setTimeout(injectDraft, 300);
          setTimeout(injectDraft, 1000);
        }
      };
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

  return { open, close };
})();

// ── router ────────────────────────────────────────────────────────────────────

const VIEWS = ["agents", "control", "tasks", "routines", "skills"];
let currentView = null;
let pollTimer   = null;

window.addEventListener("message", event => {
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
    agents:   "MESH · <b>AGENTS</b>",
    control:  "MESH · <b>MISSION CONTROL</b>",
    tasks:    "MESH · <b>TASK.BOARD</b>",
    routines: "MESH · <b>ROUTINES.CRON</b>",
    skills:   "MESH · <b>SKILLS</b>",
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
        if (this._selected) await _skillsOpenSkill(this, this._selected);
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

function _buildGraphDOM(el) {
  el.innerHTML = `
    <div id="agent-graph-wrap">
      <div id="agent-graph-toolbar">
        <span id="graph-label" style="color:var(--muted);font-size:12px;letter-spacing:.09em">AGENTS</span>
        <span class="badge" id="graph-count">0</span>
      </div>
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
  document.getElementById("agent-graph").addEventListener("click", e => {
    if (!e.target.closest(".agent-node")) AgentPanel.close();
  });
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
}

// ── render: missions table ────────────────────────────────────────────────────

const _expandedMissions = new Set(); // tracks expanded row keys across polls

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

  // daily token histogram for sparkline in stats
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

    // click to expand: show full recent turns
    const rowKey = `${s.agent}|${s.started_at}`;
    if (isLive || (s.recent_turns && s.recent_turns.length)) {
      tr.style.cursor = "pointer";
      tr.addEventListener("click", () => {
        _expandedMissions.has(rowKey) ? _expandedMissions.delete(rowKey) : _expandedMissions.add(rowKey);
        _expandMissionRow(tr, s);
      });
    }
    tbody.appendChild(tr);

    // restore expanded state after poll rebuild
    if (_expandedMissions.has(rowKey)) {
      _expandMissionRow(tr, s, true);
    }
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
    `MESH · <b>TASK.BOARD</b> <span style="color:var(--dim);font-size:10px;margin-left:8px">${total} tasks · ${inflight} inflight · ${pct}% done</span>`;

  // project bar
  const projBar = _buildProjectBar(projects, selectedProject);

  el.innerHTML = `${projBar}<div id="kanban"></div>`;

  const board = document.getElementById("kanban");

  // wire project chips
  document.querySelectorAll(".project-chip").forEach(chip => {
    chip.addEventListener("click", () => Views.tasks.setProject(chip.dataset.path));
  });

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
  if (!projects || !projects.length) return "";
  const chips = [
    `<button class="project-chip${selected === "all" ? " active" : ""}" data-path="all">Tous</button>`,
    ...projects.map(p => {
      const isActive = p.active ? " active-project" : "";
      const isSel    = selected === p.path ? " active" : "";
      return `<button class="project-chip${isActive}${isSel}" data-path="${esc(p.path)}" title="${esc(p.path)}">${esc(p.name)}</button>`;
    }),
  ].join("");
  return `<div id="project-bar"><span id="project-bar-label">PROJET</span>${chips}</div>`;
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

  // action buttons: frame/launch for actionable tasks, view for running
  const canAct = t.agent && ["backlog","queued","failed"].includes(t.status);
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
  const actHtml = canAct ? `
    <div class="task-actions" onclick="event.stopPropagation()">
      <button class="task-btn task-btn-plan">Plan</button>
      <button class="task-btn primary task-btn-launch">Launch →</button>
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
  card.querySelector(".task-btn-launch")?.addEventListener("click", e => { e.stopPropagation(); launchTask(t); });
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
  let projectPath = "";
  if (!t.project_path && !t.project && Views.tasks?.selectedProject && Views.tasks.selectedProject !== "all") {
    projectPath = Views.tasks.selectedProject;
    t = { ...t, project_path: projectPath };
    api.patch(`/api/tasks/${t.id}`, { project_path: projectPath }).catch(() => {});
  }
  ChatPanel.open({ name: t.agent }, { draft: _taskPlanningMessage(t, projectPath) });
  toast(`Message de cadrage prêt dans le chat → ${t.agent}`, "ok");
  if (projectPath) Views.tasks.reload().catch(() => {});
}

async function launchTask(t) {
  try {
    const res = await api.post(`/api/tasks/${t.id}/launch`, {});
    if (res.failed) {
      toast(`Échec après retry : ${res.error || "gateway indisponible"}`, "err");
    } else if (res.retry_scheduled) {
      toast(`Gateway indisponible, retry programmé → ${t.agent}`, "ok");
    } else if (!res.ok) {
      toast(`Envoi échoué : ${res.error || "gateway indisponible"}`, "err");
    } else if (res.scheduled) {
      toast(`Tâche programmée → ${t.agent}`, "ok");
    } else if (res.locked) {
      toast(`Envoi déjà en cours → ${t.agent}`, "ok");
    } else {
      toast(`Tâche lancée → ${t.agent}`, "ok");
      ChatPanel.open({ name: t.agent });
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
          const res = await api.post(`/api/agents/${encodeURIComponent(r.agent)}/send`, { message: r.prompt });
          if (res.ok) {
            toast(`Prompt envoyé à ${r.agent}`, "ok");
            ChatPanel.open({ name: r.agent });
          } else {
            toast(res.error || "Erreur envoi", "err");
          }
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
    is_admin: false, role: "agent", skills: [], tools: [],
  };

  Modal.open({
    title: "NEW AGENT",
    body: `
      <div class="form-row">
        <label class="form-label">NAME</label>
        <input class="form-input" id="f-name" placeholder="ex: researcher" autocomplete="off">
      </div>
      ${_agentFormHtml(blank, providers, allSkills, new Set(), providers[0] || null, allTools, adminOnly, { configured: false }, true)}
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
        const name = val("f-name").trim();
        if (!name) { toast("Le nom est requis", "err"); return; }
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
    body: _agentFormHtml(agent, providers, allSkills, activeSkills, currentProv, allTools, adminOnly, tgData),
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

// tool groups — [label, resolver, description]
const _TOOL_GROUPS = [
  ["Filesystem",  ["read_file","list_dir","write_file","make_dir","move_path"],
    "Lecture, écriture et déplacement de fichiers"],
  ["Explore",     t => t.filter(x => x.startsWith("explore_")),
    "Parcours et recherche dans l'arborescence"],
  ["Shell",       ["run_bash"],
    "Exécution de commandes shell"],
  ["Web",         t => t.filter(x => x.startsWith("web_")),
    "Recherche web et récupération de pages"],
  ["Vision",      ["vision"],
    "Analyse d'images locales via Ollama"],
  ["Skill authoring", t => t.filter(x => x.startsWith("skill_")),
    "Lire, créer et recharger des fichiers de skills (authoring uniquement)"],
  ["Host",        t => t.filter(x => x.startsWith("host_")),
    "Permissions pour interroger Marius lui-même : lister les agents, lire les logs, diagnostics, redémarrer le gateway"],
  ["Projects",    t => t.filter(x => x.startsWith("project_")),
    "Gestion et sélection du projet actif"],
  ["Security",    t => t.filter(x => x.startsWith("approval_") || x.startsWith("secret_ref_")),
    "Permissions pour gérer les approbations d'actions et les références de secrets (pas les secrets eux-mêmes)"],
  ["Provider",    t => t.filter(x => x.startsWith("provider_")),
    "Permissions pour lister ou modifier les providers LLM configurés"],
  ["Dreaming",    ["dreaming_run","daily_digest"],
    "Déclencher manuellement la consolidation mémoire ou le briefing quotidien"],
  ["Self-update", t => t.filter(x => x.startsWith("self_update_")),
    "Permissions pour proposer, appliquer ou rollback des mises à jour de Marius"],
  ["Watch",       t => t.filter(x => x.startsWith("watch_")),
    "Veille automatisée sur des sujets web"],
  ["RAG",         t => t.filter(x => x.startsWith("rag_")),
    "Sources Markdown indexées, recherche sémantique, checklists"],
  ["Calendar",    t => t.filter(x => x.startsWith("caldav_")),
    "Calendrier CalDAV via khal/vdirsyncer"],
  ["Sentinelle",  ["sentinelle_scan"],
    "Audit local : ports ouverts, services, Docker, dérive système"],
  ["Agents",      ["spawn_agent"],
    "Délégation de tâches parallèles à des sous-agents"],
  ["Web UI",      ["open_marius_web"],
    "Ouverture de l'interface web Marius"],
];

function _resolveGroup(defOrFn, allTools) {
  return typeof defOrFn === "function" ? defOrFn(allTools) : defOrFn.filter(t => allTools.includes(t));
}

function _agentFormHtml(agent, providers, allSkills, activeSkills, currentProv, allTools, adminOnly, tgData, hideNameRow = false) {
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
  const isAdmin     = agent.is_admin;
  const coreTools   = new Set((typeof toolData !== "undefined" ? toolData.core : null) || []);

  // collect core tools list for the hidden input
  const coreList = allTools.filter(t => coreTools.has(t));

  const toolsHtml = `
    <input type="hidden" id="f-always-tools" value="${esc(coreList.join(","))}">
    <div class="tool-toggles">
      ${_TOOL_GROUPS.map(([label, def, desc]) => {
        const items = _resolveGroup(def, allTools);
        // filter: remove core, remove admin-only if not admin
        const available = items.filter(t =>
          !coreTools.has(t) && (isAdmin || !adminOnly.has(t))
        );
        if (!available.length) return "";
        const isOn = available.some(t => activeTools.has(t));
        return `
          <label class="toggle-row tool-toggle-row">
            <span class="toggle-label-block">
              <span class="toggle-label">${esc(label)}</span>
              ${desc ? `<span class="toggle-desc">${esc(desc)}</span>` : ""}
            </span>
            <span class="toggle-wrap">
              <input type="checkbox" class="toggle-input tool-group-toggle"
                data-tools="${esc(available.join(","))}"
                ${isOn ? "checked" : ""}>
              <span class="toggle-slider"></span>
            </span>
          </label>`;
      }).filter(Boolean).join("")}
    </div>`;

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

  return `
    ${hideNameRow ? "" : `
    <div class="form-row">
      <label class="form-label">NAME</label>
      <div class="form-input" style="opacity:.45;cursor:default">${esc(agent.name)}</div>
    </div>`}
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

  // core tools always included
  const alwaysEl = document.getElementById("f-always-tools");
  const always   = alwaysEl ? alwaysEl.value.split(",").filter(Boolean) : [];
  // group toggles
  const toggled  = [...document.querySelectorAll(".tool-group-toggle:checked")]
    .flatMap(t => t.dataset.tools.split(",").filter(Boolean));
  const tools    = [...new Set([...always, ...toggled])];

  return {
    provider_id: provEl  ? provEl.value  : "",
    model:       modelEl ? modelEl.value : "",
    skills,
    tools,
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
  if (isNew && isRoutine) task = { recurring: true, cadence: "daily" };

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
            const res = await api.post(`/api/agents/${encodeURIComponent(task.agent)}/send`, { message: task.prompt });
            if (res.ok) {
              toast(`Prompt envoyé à ${task.agent}`, "ok");
              Modal.close();
              ChatPanel.open({ name: task.agent });
            } else {
              toast(res.error || "Erreur envoi", "err");
            }
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
  { value: "daily",   label: "Chaque jour (minuit)" },
  { value: "hourly",  label: "Toutes les heures" },
  { value: "4h",      label: "Toutes les 4h" },
  { value: "6h",      label: "Toutes les 6h" },
  { value: "12h",     label: "Toutes les 12h" },
  { value: "weekly",  label: "Chaque semaine" },
  { value: "custom",  label: "Personnalisé…" },
];

function _parseCadencePreset(cadence) {
  if (!cadence) return { preset: "daily", time: "08:00", custom: "" };
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
  const preset = document.getElementById("tf-cadence-preset")?.value || "daily";
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

// ── boot ──────────────────────────────────────────────────────────────────────

document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => navigate(btn.dataset.view);
});

document.getElementById("btn-settings").onclick = async () => {
  const [cfgData, provData] = await Promise.all([
    api.get("/api/config").catch(() => ({})),
    api.get("/api/providers").catch(() => ({ providers: [] })),
  ]);
  const cfg       = cfgData;
  const providers = provData.providers || [];

  const permOptions = ["safe", "limited", "power"];

  Modal.open({
    title: "SETTINGS",
    body: `
      <div class="form-row">
        <label class="form-label">PERMISSION MODE</label>
        <div style="display:flex;gap:8px">
          ${permOptions.map(p => `
            <label class="perm-option ${p === cfg.permission_mode ? "active" : ""}">
              <input type="radio" name="perm" value="${p}" ${p === cfg.permission_mode ? "checked" : ""} style="display:none">
              <span>${p.toUpperCase()}</span>
            </label>`).join("")}
        </div>
        <div style="margin-top:7px;font-size:11px;color:var(--dim)">
          safe — lecture seule &nbsp;·&nbsp; limited — écriture locale (recommandé) &nbsp;·&nbsp; power — sans restriction
        </div>
      </div>

      <div class="form-row" style="margin-top:4px">
        <label class="form-label">PROVIDERS</label>
        <div id="providers-list">
          ${providers.length ? providers.map(p => `
            <div class="provider-row" data-id="${esc(p.id)}">
              <span class="provider-dot"></span>
              <span class="provider-name">${esc(p.name)}</span>
              <span class="provider-kind">${esc(p.provider)}</span>
              <span class="provider-model">${esc(p.model)}</span>
              <button class="icon-btn danger provider-del" data-id="${esc(p.id)}" data-name="${esc(p.name)}">del</button>
            </div>`).join("")
          : `<div style="color:var(--dim);font-size:13px">Aucun provider configuré — lancez <code>marius add provider</code></div>`}
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
      <button class="btn" onclick="Modal.close()">Fermer</button>
      <button class="btn primary" id="btn-save-settings">Sauvegarder</button>
    `,
    onOpen() {
      // radio styling
      document.querySelectorAll(".perm-option input").forEach(input => {
        input.addEventListener("change", () => {
          document.querySelectorAll(".perm-option").forEach(el => el.classList.remove("active"));
          input.closest(".perm-option").classList.add("active");
        });
      });

      // delete provider
      document.querySelectorAll(".provider-del").forEach(btn => {
        btn.onclick = async () => {
          const id   = btn.dataset.id;
          const name = btn.dataset.name;
          if (!confirm(`Supprimer le provider "${name}" ?`)) return;
          try {
            const res = await api.del(`/api/providers/${encodeURIComponent(id)}`);
            if (res.ok) {
              btn.closest(".provider-row").remove();
              toast(`Provider ${name} supprimé`, "ok");
            } else {
              toast(res.message || "Erreur", "err");
            }
          } catch (e) { toast("Erreur: " + e.message, "err"); }
        };
      });

      document.getElementById("btn-save-settings").onclick = async () => {
        const checked = document.querySelector('input[name="perm"]:checked');
        if (!checked) return;
        try {
          const res = await api.patch("/api/config", { permission_mode: checked.value });
          if (res.ok) {
            toast("Paramètres sauvegardés", "ok");
            Modal.close();
          } else {
            toast(res.message || "Erreur", "err");
          }
        } catch (e) { toast("Erreur: " + e.message, "err"); }
      };
    },
  });
};

const initial = location.hash.replace("#", "") || "agents";
navigate(initial);
