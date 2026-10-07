/* Phase 8 — Human/AI Workspace client */
(function () {
  const state = {
    apiBase: localStorage.getItem("ws_apiBase") || "/api/v1",
    companyId: localStorage.getItem("ws_companyId") || "",
    userId: localStorage.getItem("ws_userId") || "",
    connected: false,
  };

  const $ = (id) => document.getElementById(id);

  function headers(json = true) {
    const h = {};
    if (json) h["Content-Type"] = "application/json";
    if (state.userId) h["X-User-ID"] = state.userId;
    return h;
  }

  async function api(path, opts = {}) {
    const url = state.apiBase.replace(/\/$/, "") + path;
    const res = await fetch(url, {
      ...opts,
      headers: { ...headers(!(opts.body instanceof FormData)), ...(opts.headers || {}) },
    });
    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : text || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function setConnected(ok) {
    state.connected = ok;
    $("statusPill").textContent = ok ? "Connected" : "Offline";
    $("statusPill").className = "pill " + (ok ? "ok" : "muted");
    $("sessionBox").innerHTML = ok
      ? `<div><strong>Company</strong><br>${state.companyId}</div>
         <div style="margin-top:0.4rem"><strong>User</strong><br>${state.userId}</div>`
      : "<small>Not connected</small>";
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      if (btn.dataset.view === "setup") return;
      btn.disabled = !ok;
    });
  }

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    const view = $("view-" + name);
    if (view) view.classList.add("active");
    const btn = document.querySelector(`.nav-btn[data-view="${name}"]`);
    if (btn) btn.classList.add("active");
    const titles = {
      setup: "Setup",
      dashboard: "Dashboard",
      agents: "AI Workforce",
      tasks: "Task Center",
      approvals: "Approvals",
      consult: "Consultation",
      directory: "Agent Directory",
      knowledge: "Knowledge",
    };
    $("viewTitle").textContent = titles[name] || name;
    if (state.connected) {
      if (name === "dashboard") loadDashboard();
      if (name === "agents") loadAgents();
      if (name === "tasks") { loadAgentOptions(); loadTasks(); }
      if (name === "approvals") loadApprovals();
      if (name === "consult") loadAgentOptions();
      if (name === "directory") listDirectory();
    }
  }

  document.getElementById("nav").addEventListener("click", (e) => {
    const btn = e.target.closest(".nav-btn");
    if (!btn || btn.disabled) return;
    showView(btn.dataset.view);
  });

  // ---- Setup ----
  $("apiBase").value = state.apiBase;
  $("companyId").value = state.companyId;
  $("userId").value = state.userId;

  $("btnConnect").onclick = async () => {
    state.apiBase = $("apiBase").value.trim() || "/api/v1";
    state.companyId = $("companyId").value.trim();
    state.userId = $("userId").value.trim();
    localStorage.setItem("ws_apiBase", state.apiBase);
    localStorage.setItem("ws_companyId", state.companyId);
    localStorage.setItem("ws_userId", state.userId);
    try {
      await api(`/companies/${state.companyId}/agents`);
      setConnected(true);
      $("setupLog").textContent = "Connected.";
      showView("dashboard");
    } catch (err) {
      setConnected(false);
      $("setupLog").textContent = "Connect failed: " + err.message;
    }
  };

  $("btnQuickStart").onclick = async () => {
    state.apiBase = $("apiBase").value.trim() || "/api/v1";
    localStorage.setItem("ws_apiBase", state.apiBase);
    const log = $("setupLog");
    try {
      log.textContent = "Creating company...";
      const co = await api("/companies", {
        method: "POST",
        body: JSON.stringify({ name: "Workspace Demo Co" }),
      });
      log.textContent += `\nCompany ${co.id}`;
      const user = await api(`/companies/${co.id}/users`, {
        method: "POST",
        body: JSON.stringify({
          name: "Workspace Owner",
          email: `owner-${Date.now()}@demo.local`,
          role: "owner",
        }),
      });
      state.companyId = co.id;
      state.userId = user.id;
      $("companyId").value = co.id;
      $("userId").value = user.id;
      localStorage.setItem("ws_companyId", co.id);
      localStorage.setItem("ws_userId", user.id);

      const catalog = await api("/agent-catalog");
      const res = catalog.find((c) => c.slug === "reservation") || catalog[0];
      if (res) {
        await api(`/companies/${co.id}/agents/${res.id}/hire`, {
          method: "POST",
          body: JSON.stringify({ name: "Desk AI" }),
        });
      }
      setConnected(true);
      log.textContent += `\nUser ${user.id}\nHired agent.\nReady.`;
      showView("dashboard");
    } catch (err) {
      log.textContent += "\nError: " + err.message;
      setConnected(false);
    }
  };

  // ---- Dashboard ----
  async function loadDashboard() {
    try {
      const [agents, tasks, approvals] = await Promise.all([
        api(`/companies/${state.companyId}/agents`),
        api(`/companies/${state.companyId}/tasks`),
        api(`/companies/${state.companyId}/approvals`).catch(() => []),
      ]);
      const pending = (approvals || []).filter((a) => a.status === "pending");
      $("dashStats").innerHTML = [
        ["Agents", agents.length],
        ["Tasks", tasks.length],
        ["Pending approvals", pending.length],
        ["Completed", tasks.filter((t) => t.status === "completed").length],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`
        )
        .join("");

      $("dashTasks").innerHTML = tasks
        .slice(0, 8)
        .map(
          (t) =>
            `<div class="item"><strong>${escapeHtml(t.title)}</strong>
             <div class="meta">${t.mode || "execute"} · ${t.status}</div></div>`
        )
        .join("") || '<div class="muted">No tasks yet</div>';

      $("dashApprovals").innerHTML = pending
        .slice(0, 8)
        .map(
          (a) =>
            `<div class="item"><strong>${escapeHtml(a.action)}</strong>
             <div class="meta">${a.id}</div></div>`
        )
        .join("") || '<div class="muted">No pending approvals</div>';
    } catch (err) {
      $("dashStats").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  // ---- Agents ----
  async function loadAgents() {
    try {
      const agents = await api(`/companies/${state.companyId}/agents`);
      $("agentList").innerHTML = agents
        .map(
          (a) => `<div class="agent-card">
            <h4>${escapeHtml(a.name)}</h4>
            <div class="meta">${a.status} · autonomy ${a.autonomy || "-"}</div>
            <div style="margin-top:0.4rem">
              ${(a.skills || []).slice(0, 6).map((s) => `<span class="tag">${escapeHtml(s)}</span>`).join("")}
            </div>
            <div class="meta" style="margin-top:0.35rem">${a.id}</div>
          </div>`
        )
        .join("") || '<div class="muted">No agents hired</div>';

      const catalog = await api("/agent-catalog");
      $("catalogSelect").innerHTML = catalog
        .map((c) => `<option value="${c.id}">${escapeHtml(c.name)} (${c.slug})</option>`)
        .join("");
    } catch (err) {
      $("agentList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  $("btnRefreshAgents").onclick = loadAgents;
  $("btnHire").onclick = async () => {
    try {
      const catalogId = $("catalogSelect").value;
      const name = $("hireName").value.trim() || "New AI";
      const inst = await api(
        `/companies/${state.companyId}/agents/${catalogId}/hire`,
        { method: "POST", body: JSON.stringify({ name }) }
      );
      $("hireLog").textContent = "Hired: " + JSON.stringify(inst, null, 2);
      loadAgents();
    } catch (err) {
      $("hireLog").textContent = err.message;
    }
  };

  // ---- Tasks ----
  async function loadAgentOptions() {
    const agents = await api(`/companies/${state.companyId}/agents`);
    const opts = agents
      .map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`)
      .join("");
    $("taskAgent").innerHTML = opts;
    $("consultAgent").innerHTML = opts;
  }

  async function loadTasks() {
    try {
      const tasks = await api(`/companies/${state.companyId}/tasks`);
      $("taskList").innerHTML = tasks
        .map((t) => {
          const actions =
            t.mode === "consult" && t.status === "pending"
              ? `<button class="secondary" data-consult="${t.id}">Run consult</button>`
              : t.status === "pending"
              ? `<button class="secondary" data-exec="${t.id}">Mark note</button>`
              : "";
          return `<div class="item">
            <div class="row between">
              <div><strong>${escapeHtml(t.title)}</strong>
                <div class="meta">${t.mode || "execute"} · ${t.status} · ${t.id}</div>
              </div>
              <div class="row">${actions}</div>
            </div>
            ${t.result ? `<pre class="log" style="max-height:120px">${escapeHtml(String(t.result).slice(0, 800))}</pre>` : ""}
          </div>`;
        })
        .join("") || '<div class="muted">No tasks</div>';

      $("taskList").querySelectorAll("[data-consult]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            const t = await api(
              `/companies/${state.companyId}/tasks/${btn.dataset.consult}/consult`,
              { method: "POST" }
            );
            alert("Consultation completed");
            loadTasks();
          } catch (err) {
            alert(err.message);
          }
        };
      });
    } catch (err) {
      $("taskList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  $("btnRefreshTasks").onclick = loadTasks;
  $("btnCreateTask").onclick = async () => {
    try {
      const body = {
        agent_instance_id: $("taskAgent").value,
        title: $("taskTitle").value.trim(),
        instruction: $("taskInstruction").value.trim(),
        mode: $("taskMode").value,
      };
      await api(`/companies/${state.companyId}/tasks`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      $("taskTitle").value = "";
      $("taskInstruction").value = "";
      loadTasks();
    } catch (err) {
      alert(err.message);
    }
  };

  // ---- Approvals ----
  async function loadApprovals() {
    try {
      const approvals = await api(`/companies/${state.companyId}/approvals`);
      $("approvalList").innerHTML = approvals
        .map((a) => {
          const pending = a.status === "pending";
          return `<div class="item">
            <div class="row between">
              <div>
                <strong>${escapeHtml(a.action)}</strong>
                <div class="meta">${a.status} · ${a.id}</div>
                <div class="meta">${escapeHtml(a.reason || "")}</div>
              </div>
              ${
                pending
                  ? `<div class="row">
                      <button class="success" data-approve="${a.id}">Approve</button>
                      <button class="danger" data-reject="${a.id}">Reject</button>
                    </div>`
                  : ""
              }
            </div>
          </div>`;
        })
        .join("") || '<div class="muted">No approvals</div>';

      $("approvalList").querySelectorAll("[data-approve]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/approvals/${btn.dataset.approve}/approve`,
              { method: "POST", body: JSON.stringify({ comment: "Approved from workspace" }) }
            );
            loadApprovals();
          } catch (err) {
            alert(err.message);
          }
        };
      });
      $("approvalList").querySelectorAll("[data-reject]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/approvals/${btn.dataset.reject}/reject`,
              { method: "POST", body: JSON.stringify({ comment: "Rejected from workspace" }) }
            );
            loadApprovals();
          } catch (err) {
            alert(err.message);
          }
        };
      });
    } catch (err) {
      $("approvalList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshApprovals").onclick = loadApprovals;

  // ---- Consult ----
  $("btnConsult").onclick = async () => {
    const out = $("consultResult");
    try {
      out.textContent = "Creating consultation task...";
      const task = await api(`/companies/${state.companyId}/tasks`, {
        method: "POST",
        body: JSON.stringify({
          agent_instance_id: $("consultAgent").value,
          title: $("consultTitle").value.trim() || "Consultation",
          instruction: $("consultQuestion").value.trim(),
          mode: "consult",
        }),
      });
      out.textContent = "Running...";
      const done = await api(
        `/companies/${state.companyId}/tasks/${task.id}/consult`,
        { method: "POST" }
      );
      let result = done.result;
      try { result = JSON.stringify(JSON.parse(done.result), null, 2); } catch {}
      out.textContent = result;
    } catch (err) {
      out.textContent = err.message;
    }
  };

  // ---- Directory ----
  async function listDirectory(skill) {
    try {
      const path = skill
        ? `/companies/${state.companyId}/directory/search?skill=${encodeURIComponent(skill)}`
        : `/companies/${state.companyId}/directory`;
      const entries = await api(path);
      $("dirList").innerHTML = entries
        .map(
          (e) => `<div class="agent-card">
            <h4>${escapeHtml(e.name)}</h4>
            <div class="meta">${escapeHtml(e.role)} · ${e.status}</div>
            <div style="margin-top:0.4rem">
              ${(e.capabilities || []).slice(0, 10).map((c) => `<span class="tag">${escapeHtml(c)}</span>`).join("")}
            </div>
          </div>`
        )
        .join("") || '<div class="muted">No agents</div>';
    } catch (err) {
      $("dirList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnListDir").onclick = () => listDirectory();
  $("btnSearchDir").onclick = () => listDirectory($("dirSkill").value.trim());

  // ---- Knowledge ----
  $("btnAddKnowledge").onclick = async () => {
    try {
      await api(`/companies/${state.companyId}/knowledge`, {
        method: "POST",
        body: JSON.stringify({
          title: $("knowTitle").value.trim(),
          content: $("knowContent").value.trim(),
          category: "general",
        }),
      });
      $("knowTitle").value = "";
      $("knowContent").value = "";
      $("knowResults").innerHTML = '<div class="item">Knowledge added.</div>';
    } catch (err) {
      alert(err.message);
    }
  };
  $("btnSearchKnow").onclick = async () => {
    try {
      const hits = await api(`/companies/${state.companyId}/knowledge/search`, {
        method: "POST",
        body: JSON.stringify({ query: $("knowQuery").value.trim(), limit: 10 }),
      });
      $("knowResults").innerHTML = hits
        .map(
          (h) =>
            `<div class="item"><div class="meta">${h.source} · score ${h.score}</div>${escapeHtml((h.content || h.title || "").slice(0, 300))}</div>`
        )
        .join("") || '<div class="muted">No hits</div>';
    } catch (err) {
      $("knowResults").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  };

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Auto-connect if stored
  if (state.companyId && state.userId) {
    $("btnConnect").click();
  }
})();
