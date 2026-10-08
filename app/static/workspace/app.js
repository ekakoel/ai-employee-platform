(function () {
  const $ = (id) => document.getElementById(id);

  const state = {
    apiBase: localStorage.getItem("ws_apiBase") || "/api/v1",
    companyId: localStorage.getItem("ws_companyId") || "",
    userId: localStorage.getItem("ws_userId") || "",
    accessToken: localStorage.getItem("ws_accessToken") || "",
    userName: localStorage.getItem("ws_userName") || "",
  };

  const titles = {
    home: ["Home", "Command center"],
    inbox: ["Inbox", "Needs your attention"],
    chat: ["Chat", "Talk with AI employees"],
    tasks: ["Tasks", "Create and track work"],
    approvals: ["Approvals", "Human authority queue"],
    agents: ["AI Employees", "Hire and manage workforce"],
    marketplace: ["Marketplace", "Install public templates"],
    consult: ["Consult", "Recommendations without side effects"],
    directory: ["Directory", "Find capability across agents"],
    knowledge: ["Knowledge", "Company memory and search"],
    delegation: ["Delegation", "AI-to-AI handoff"],
    automation: ["Automation", "Rules and triggers"],
    notifications: ["Notifications", "Alerts and updates"],
    governance: ["Governance", "Metrics and audit"],
    policies: ["Policy Simulator", "Dry-run ALLOW / APPROVAL / DENY"],
    departments: ["Departments", "Org structure for agents and users"],
    skills: ["Skills", "Platform and company capabilities"],
    usage: ["Plan & Usage", "Quotas and metering"],
    tools: ["Tools", "Catalog side-effect and risk"],
    integrations: ["Integrations", "Webhooks, email, calendar"],
    workflows: ["Workflows", "Multi-step automation"],
    cost: ["LLM Cost", "Token usage and spend"],
    scopecheck: ["Scope Check", "Out-of-scope detection"],
  };

  function clearSession() {
    state.companyId = "";
    state.userId = "";
    state.accessToken = "";
    state.userName = "";
    ["ws_companyId", "ws_userId", "ws_accessToken", "ws_refreshToken", "ws_userName"].forEach((k) =>
      localStorage.removeItem(k)
    );
    showGate(true);
  }

  function headers(json = true, skipAuth = false) {
    const h = {};
    if (json) h["Content-Type"] = "application/json";
    if (!skipAuth) {
      if (state.accessToken) h["Authorization"] = "Bearer " + state.accessToken;
      if (state.userId) h["X-User-ID"] = state.userId;
    }
    return h;
  }

  async function api(path, opts = {}) {
    const base = (state.apiBase || "/api/v1").replace(/\/$/, "");
    const url = path.startsWith("http") ? path : base + path;
    const res = await fetch(url, {
      ...opts,
      headers: { ...headers(true, opts.skipAuth), ...(opts.headers || {}) },
    });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    if (!res.ok) {
      const detail =
        data && typeof data === "object"
          ? data.detail || JSON.stringify(data)
          : text || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showGate(show) {
    const gate = $("loginGate");
    const app = $("app");
    if (gate) gate.classList.toggle("hidden", !show);
    if (app) app.classList.toggle("hidden", show);
  }

  function setConnected(ok) {
    showGate(!ok);
    const box = $("sessionBox");
    const pill = $("statusPill");
    if (box) {
      box.innerHTML = ok
        ? `<div><strong>${escapeHtml(state.userName || "User")}</strong></div>
           <small>${escapeHtml(state.userId.slice(0, 8))}…</small><br/>
           <small>co ${escapeHtml(state.companyId.slice(0, 8))}…</small>`
        : "<small>Not connected</small>";
    }
    if (pill) {
      pill.textContent = ok ? "Online" : "Offline";
      pill.className = ok ? "pill ok" : "pill muted";
    }
    const sub = $("brandSub");
    if (sub) sub.textContent = ok ? "Workspace" : "Offline";
  }

  function setInboxBadge(n) {
    const b = $("inboxBadge");
    const nav = $("navInboxCount");
    if (b) {
      b.textContent = String(n);
      b.classList.toggle("hidden", !n);
    }
    if (nav) {
      nav.textContent = String(n);
      nav.classList.toggle("hidden", !n);
    }
  }

  function setNotifBadge(n) {
    const b = $("notifBadge");
    if (b) {
      b.textContent = String(n);
      b.classList.toggle("hidden", !n);
    }
  }

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    const view = $("view-" + name);
    if (view) view.classList.add("active");
    const btn = document.querySelector(`.nav-btn[data-view="${name}"]`);
    if (btn) btn.classList.add("active");
    const t = titles[name] || [name, ""];
    if ($("viewTitle")) $("viewTitle").textContent = t[0];
    if ($("viewSubtitle")) $("viewSubtitle").textContent = t[1];

    if (name === "home") loadHome();
    if (name === "inbox") loadInbox();
    if (name === "agents") loadAgents();
    if (name === "tasks") {
      loadAgentOptions();
      loadTasks();
    }
    if (name === "approvals") loadApprovals();
    if (name === "chat") loadChat();
    if (name === "consult") loadAgentOptions();
    if (name === "marketplace") loadMarketplace();
    if (name === "delegation") {
      loadAgentOptions();
      loadDelegations();
    }
    if (name === "automation") {
      loadAgentOptions();
      loadAutomations();
    }
    if (name === "notifications") loadNotifications();
    if (name === "governance") loadGovernance();
    if (name === "directory") listDirectory();
    if (name === "policies") { loadAgentOptions(); }
    if (name === "departments") loadDepartments();
    if (name === "skills") loadSkills();
    if (name === "usage") loadUsage();
    if (name === "tools") loadTools();
    if (name === "integrations") loadIntegrations();
    if (name === "workflows") { loadAgentOptions(); loadWorkflows(); }
    if (name === "cost") loadCost();
    if (name === "scopecheck") loadAgentOptions();
  }

  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });

  document.querySelectorAll("[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.jump));
  });

  // Login tabs
  document.querySelectorAll(".login-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".login-tabs .tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      const panel = $("tab-" + tab.dataset.tab);
      if (panel) panel.classList.add("active");
    });
  });

  async function applyAuthSession(body) {
    state.companyId = body.company_id;
    state.userId = body.user_id;
    state.accessToken = body.access_token || "";
    state.userName = body.name || body.email || "";
    localStorage.setItem("ws_companyId", state.companyId);
    localStorage.setItem("ws_userId", state.userId);
    localStorage.setItem("ws_accessToken", state.accessToken);
    localStorage.setItem("ws_userName", state.userName);
    if (body.refresh_token) localStorage.setItem("ws_refreshToken", body.refresh_token);
    if ($("companyId")) $("companyId").value = state.companyId;
    if ($("userId")) $("userId").value = state.userId;
    if ($("loginCompanyId")) $("loginCompanyId").value = state.companyId;
    setConnected(true);
    await refreshInboxBadge();
    showView("home");
  }

  // ----- Quick start -----
  $("btnQuickStart").onclick = async () => {
    const log = $("quickLog");
    try {
      log.textContent = "Creating company…";
      const co = await api("/companies", {
        method: "POST",
        body: JSON.stringify({ name: "Demo Co " + Date.now().toString(36) }),
        skipAuth: true,
      });
      log.textContent += "\nCompany " + co.id;
      const user = await api(`/companies/${co.id}/users`, {
        method: "POST",
        body: JSON.stringify({
          name: "Demo Owner",
          email: "owner@demo.local",
          role: "owner",
          password: "demo12345",
        }),
        skipAuth: true,
      });
      log.textContent += "\nUser " + user.id;
      state.companyId = co.id;
      state.userId = user.id;
      state.userName = user.name || "Demo Owner";
      localStorage.setItem("ws_companyId", state.companyId);
      localStorage.setItem("ws_userId", state.userId);
      localStorage.setItem("ws_userName", state.userName);

      // Try password login for JWT
      try {
        const tok = await api("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            company_id: co.id,
            email: "owner@demo.local",
            password: "demo12345",
          }),
          skipAuth: true,
        });
        state.accessToken = tok.access_token || "";
        localStorage.setItem("ws_accessToken", state.accessToken);
        if (tok.refresh_token) localStorage.setItem("ws_refreshToken", tok.refresh_token);
        log.textContent += "\nJWT session OK";
      } catch (e) {
        log.textContent += "\nJWT optional: " + e.message;
      }

      // Hire from catalog
      try {
        const catalog = await api("/agent-catalog", { skipAuth: true });
        for (const c of (catalog || []).slice(0, 2)) {
          await api(`/companies/${co.id}/agents/${c.id}/hire`, {
            method: "POST",
            body: JSON.stringify({ name: c.name.replace(/ AI Employee$/, "") + " (Demo)" }),
          });
          log.textContent += "\nHired " + c.slug;
        }
      } catch (e) {
        log.textContent += "\nHire: " + e.message;
      }

      if ($("loginCompanyId")) $("loginCompanyId").value = co.id;
      if ($("loginEmail")) $("loginEmail").value = "owner@demo.local";
      if ($("loginPassword")) $("loginPassword").value = "demo12345";
      if ($("companyId")) $("companyId").value = co.id;
      if ($("userId")) $("userId").value = user.id;

      setConnected(true);
      await refreshInboxBadge();
      showView("home");
      log.textContent += "\n\nWorkspace ready. Password: demo12345";
    } catch (err) {
      log.textContent = "Quick start failed: " + err.message;
    }
  };

  $("btnConnect").onclick = async () => {
    const log = $("setupLog");
    try {
      state.apiBase = ($("apiBase") && $("apiBase").value.trim()) || "/api/v1";
      state.companyId = $("companyId").value.trim();
      state.userId = $("userId").value.trim();
      if (!state.companyId || !state.userId) throw new Error("Company ID and User ID required");
      localStorage.setItem("ws_apiBase", state.apiBase);
      localStorage.setItem("ws_companyId", state.companyId);
      localStorage.setItem("ws_userId", state.userId);
      await api(`/companies/${state.companyId}`);
      setConnected(true);
      await refreshInboxBadge();
      showView("home");
      log.textContent = "Connected.";
    } catch (err) {
      log.textContent = "Connect failed: " + err.message;
      setConnected(false);
    }
  };

  $("btnClearSession").onclick = clearSession;
  if ($("btnLogout")) $("btnLogout").onclick = clearSession;

  $("btnLogin").onclick = async () => {
    const log = $("loginLog");
    try {
      const companyId = ($("loginCompanyId").value || $("companyId").value || "").trim();
      const body = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          company_id: companyId,
          email: $("loginEmail").value.trim(),
          password: $("loginPassword").value,
        }),
        skipAuth: true,
      });
      log.textContent = "Signed in as " + (body.email || body.user_id);
      await applyAuthSession(body);
    } catch (err) {
      log.textContent = "Login failed: " + err.message;
    }
  };

  $("btnRegister").onclick = async () => {
    const log = $("loginLog");
    try {
      const companyId = ($("loginCompanyId").value || $("companyId").value || "").trim();
      const email = $("loginEmail").value.trim();
      const body = await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          company_id: companyId,
          email,
          name: email.split("@")[0] || "User",
          password: $("loginPassword").value,
          role: "member",
        }),
        skipAuth: true,
      });
      log.textContent = "Registered " + (body.email || body.user_id);
      await applyAuthSession(body);
    } catch (err) {
      log.textContent = "Register failed: " + err.message;
    }
  };

  async function loadAgentOptions() {
    if (!state.companyId) return;
    try {
      const agents = await api(`/companies/${state.companyId}/agents`);
      const opts = (agents || [])
        .map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`)
        .join("");
      ["taskAgent", "consultAgent", "chatAgent", "delSource", "delTarget", "autoAgent", "simAgent", "scopeAgent", "wfAgent"].forEach(
        (id) => {
          const el = $(id);
          if (el) el.innerHTML = opts;
        }
      );
    } catch (_) {}
  }

  async function refreshInboxBadge() {
    if (!state.companyId) return;
    try {
      const [tasks, approvals, dels, notif] = await Promise.all([
        api(`/companies/${state.companyId}/tasks`).catch(() => []),
        api(`/companies/${state.companyId}/approvals`).catch(() => []),
        api(`/companies/${state.companyId}/delegation-requests`).catch(() => []),
        api(`/companies/${state.companyId}/notifications/unread-count`).catch(() => ({ count: 0 })),
      ]);
      const pendingTasks = (tasks || []).filter((t) =>
        ["pending", "waiting_approval", "planning"].includes(t.status)
      ).length;
      const pendingAppr = (approvals || []).filter((a) => a.status === "pending").length;
      const openDel = (dels || []).filter((d) =>
        ["pending", "accepted"].includes(d.status)
      ).length;
      setInboxBadge(pendingTasks + pendingAppr + openDel);
      setNotifBadge((notif && notif.count) || 0);
    } catch (_) {}
  }

  // ----- Home -----
  async function loadHome() {
    if (!state.companyId) return;
    try {
      const [agents, tasks, approvals] = await Promise.all([
        api(`/companies/${state.companyId}/agents`),
        api(`/companies/${state.companyId}/tasks`),
        api(`/companies/${state.companyId}/approvals`),
      ]);
      const active = (agents || []).filter((a) => a.status === "active").length;
      const openTasks = (tasks || []).filter((t) =>
        !["completed", "failed", "cancelled"].includes(t.status)
      ).length;
      const pendingAppr = (approvals || []).filter((a) => a.status === "pending").length;
      $("homeStats").innerHTML = [
        ["AI Employees", agents.length],
        ["Active", active],
        ["Open tasks", openTasks],
        ["Pending approvals", pendingAppr],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n">${n}</div><div class="l">${escapeHtml(l)}</div></div>`
        )
        .join("");

      const attention = [];
      (tasks || [])
        .filter((t) => ["pending", "waiting_approval"].includes(t.status))
        .slice(0, 4)
        .forEach((t) =>
          attention.push(
            `<div class="item"><span class="type-tag task">task</span>${escapeHtml(t.title || t.id)}<div class="meta">${escapeHtml(t.status)} · ${escapeHtml(t.mode || "")}</div></div>`
          )
        );
      (approvals || [])
        .filter((a) => a.status === "pending")
        .slice(0, 4)
        .forEach((a) =>
          attention.push(
            `<div class="item"><span class="type-tag approval">approval</span>${escapeHtml(a.action)}<div class="meta">${escapeHtml(a.reason || "")}</div></div>`
          )
        );
      $("homeInbox").innerHTML =
        attention.join("") || `<div class="empty">Nothing pending — you're clear.</div>`;

      $("homeAgents").innerHTML =
        (agents || [])
          .slice(0, 6)
          .map(
            (a) => `<div class="agent-card">
          <h4><span class="status-dot ${a.status !== "active" ? "inactive" : ""}"></span>${escapeHtml(a.name)}</h4>
          <div class="meta muted">${escapeHtml(a.status)} · v${escapeHtml(a.template_version || "")}</div>
        </div>`
          )
          .join("") || `<div class="empty">No agents yet. Hire from Marketplace.</div>`;
    } catch (err) {
      $("homeStats").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  // ----- Notifications -----
  async function loadNotifications() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/notifications`);
      const unread = (list || []).filter((n) => !n.read_at).length;
      $("notifStats").innerHTML = `<div class="stat"><div class="n">${unread}</div><div class="l">Unread</div></div>
        <div class="stat"><div class="n">${(list || []).length}</div><div class="l">Total</div></div>`;
      $("notifList").innerHTML =
        (list || [])
          .map(
            (n) => `<div class="item">
          <strong>${escapeHtml(n.type || "notification")}</strong>
          <div class="meta">${escapeHtml(JSON.stringify(n.payload || {}).slice(0, 120))} · ${n.read_at ? "read" : "unread"}</div>
          ${
            !n.read_at
              ? `<div class="actions"><button class="secondary btn-read-one" data-id="${n.id}">Mark read</button></div>`
              : ""
          }
        </div>`
          )
          .join("") || `<div class="empty">No notifications.</div>`;
      document.querySelectorAll(".btn-read-one").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/notifications/${b.dataset.id}/read`, {
            method: "POST",
            body: "{}",
          });
          await loadNotifications();
          await refreshInboxBadge();
        };
      });
      setNotifBadge(unread);
    } catch (err) {
      $("notifList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  if ($("btnNotifRefresh")) $("btnNotifRefresh").onclick = loadNotifications;
  if ($("btnNotifReadAll"))
    $("btnNotifReadAll").onclick = async () => {
      await api(`/companies/${state.companyId}/notifications/read-all`, {
        method: "POST",
        body: "{}",
      });
      await loadNotifications();
      await refreshInboxBadge();
    };
  if ($("btnTopNotif")) $("btnTopNotif").onclick = () => showView("notifications");

  // ----- Inbox -----
  async function loadInbox() {
    if (!state.companyId) return;
    try {
      const [tasks, approvals, dels] = await Promise.all([
        api(`/companies/${state.companyId}/tasks`),
        api(`/companies/${state.companyId}/approvals`),
        api(`/companies/${state.companyId}/delegation-requests`),
      ]);
      const pendingTasks = (tasks || []).filter((t) =>
        ["pending", "waiting_approval", "planning", "running"].includes(t.status)
      );
      const pendingAppr = (approvals || []).filter((a) => a.status === "pending");
      const openDel = (dels || []).filter((d) =>
        ["pending", "accepted"].includes(d.status)
      );
      $("inboxStats").innerHTML = [
        ["Tasks", pendingTasks.length],
        ["Approvals", pendingAppr.length],
        ["Delegations", openDel.length],
        ["Total", pendingTasks.length + pendingAppr.length + openDel.length],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`
        )
        .join("");

      const rows = [];
      pendingTasks.forEach((t) => {
        rows.push(`<div class="item">
          <span class="type-tag task">task</span><strong>${escapeHtml(t.title || t.id)}</strong>
          <div class="meta">${escapeHtml(t.status)} · ${escapeHtml(t.mode || "")}</div>
          <div class="actions">
            ${
              t.mode === "consult" && t.status === "pending"
                ? `<button class="primary btn-run-consult" data-id="${t.id}">Run consult</button>`
                : ""
            }
          </div>
        </div>`);
      });
      pendingAppr.forEach((a) => {
        rows.push(`<div class="item">
          <span class="type-tag approval">approval</span><strong>${escapeHtml(a.action)}</strong>
          <div class="meta">${escapeHtml(a.reason || "")}</div>
          <div class="actions">
            <button class="success btn-appr" data-id="${a.id}" data-d="approved">Approve</button>
            <button class="danger btn-appr" data-id="${a.id}" data-d="rejected">Reject</button>
          </div>
        </div>`);
      });
      openDel.forEach((d) => {
        rows.push(`<div class="item">
          <span class="type-tag delegation">delegation</span><strong>${escapeHtml(d.title || d.id)}</strong>
          <div class="meta">${escapeHtml(d.status)} · ${escapeHtml(d.capability || "")}</div>
          <div class="actions">
            ${
              d.status === "pending" || d.status === "accepted"
                ? `<button class="primary btn-exec-del" data-id="${d.id}">Execute</button>`
                : ""
            }
          </div>
        </div>`);
      });
      $("inboxList").innerHTML = rows.join("") || `<div class="empty">Inbox zero. Nice work.</div>`;

      document.querySelectorAll(".btn-run-consult").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/tasks/${b.dataset.id}/run`, {
            method: "POST",
            body: "{}",
          });
          loadInbox();
          refreshInboxBadge();
        };
      });
      document.querySelectorAll(".btn-appr").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/approvals/${b.dataset.id}/review`, {
            method: "POST",
            body: JSON.stringify({ status: b.dataset.d, comment: "workspace" }),
          });
          loadInbox();
          refreshInboxBadge();
        };
      });
      document.querySelectorAll(".btn-exec-del").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/delegation-requests/${b.dataset.id}/execute`, {
            method: "POST",
            body: "{}",
          });
          loadInbox();
          refreshInboxBadge();
        };
      });
      setInboxBadge(pendingTasks.length + pendingAppr.length + openDel.length);
    } catch (err) {
      $("inboxList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshInbox").onclick = loadInbox;

  // ----- Agents -----
  async function loadAgents() {
    if (!state.companyId) return;
    try {
      const [agents, catalog] = await Promise.all([
        api(`/companies/${state.companyId}/agents`),
        api("/agent-catalog"),
      ]);
      $("agentList").innerHTML =
        (agents || [])
          .map(
            (a) => `<div class="agent-card">
          <h4><span class="status-dot ${a.status !== "active" ? "inactive" : ""}"></span>${escapeHtml(a.name)}</h4>
          <div class="muted" style="font-size:.8rem">${escapeHtml(a.status)} · autonomy ${escapeHtml(a.autonomy || "")}</div>
          <div style="margin-top:.4rem">${(a.skills || []).slice(0, 5).map((s) => `<span class="tag">${escapeHtml(s)}</span>`).join("")}</div>
        </div>`
          )
          .join("") || `<div class="empty">No agents hired yet.</div>`;
      const sel = $("catalogSelect");
      if (sel)
        sel.innerHTML = (catalog || [])
          .map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`)
          .join("");
    } catch (err) {
      $("agentList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshAgents").onclick = loadAgents;
  $("btnHire").onclick = async () => {
    const log = $("hireLog");
    try {
      const catalogId = $("catalogSelect").value;
      const name = $("hireName").value.trim() || "New AI Employee";
      const inst = await api(`/companies/${state.companyId}/agents/${catalogId}/hire`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      log.textContent = "Hired " + inst.name + " (" + inst.id + ")";
      loadAgents();
      loadHome();
    } catch (err) {
      log.textContent = err.message;
    }
  };

  // ----- Marketplace -----
  async function loadMarketplace() {
    if (!state.companyId) return;
    try {
      const [templates, installs] = await Promise.all([
        api("/marketplace/templates"),
        api(`/companies/${state.companyId}/marketplace/installations`),
      ]);
      const installed = new Set((installs || []).map((i) => i.catalog_agent_id));
      $("marketList").innerHTML =
        (templates || [])
          .map(
            (t) => `<div class="agent-card">
          <h4>${escapeHtml(t.name)}</h4>
          <div class="muted" style="font-size:.8rem">${escapeHtml(t.role)} · v${escapeHtml(t.version)}</div>
          <p style="font-size:.85rem;color:var(--muted)">${escapeHtml((t.description || "").slice(0, 120))}</p>
          <div>${(t.skills || []).slice(0, 6).map((s) => `<span class="tag">${escapeHtml(s)}</span>`).join("")}</div>
          <div class="row">
            ${
              installed.has(t.id)
                ? `<span class="pill ok">Installed</span>`
                : `<button class="primary btn-install" data-id="${t.id}">Install</button>`
            }
          </div>
        </div>`
          )
          .join("") || `<div class="empty">No public templates.</div>`;
      $("installList").innerHTML =
        (installs || [])
          .map(
            (i) => `<div class="item"><strong>${escapeHtml(i.catalog_name)}</strong>
          <div class="meta">${escapeHtml(i.catalog_slug)} · v${escapeHtml(i.template_version)} · skills ${(i.installed_skill_ids || []).length}</div></div>`
          )
          .join("") || `<div class="empty">No installations yet.</div>`;
      document.querySelectorAll(".btn-install").forEach((b) => {
        b.onclick = async () => {
          b.disabled = true;
          try {
            await api(`/companies/${state.companyId}/marketplace/install/${b.dataset.id}`, {
              method: "POST",
              body: "{}",
            });
            loadMarketplace();
          } catch (err) {
            alert(err.message);
            b.disabled = false;
          }
        };
      });
    } catch (err) {
      $("marketList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshMarket")) $("btnRefreshMarket").onclick = loadMarketplace;

  // ----- Tasks -----
  async function loadTasks() {
    if (!state.companyId) return;
    try {
      let tasks = await api(`/companies/${state.companyId}/tasks`);
      const f = $("taskFilter").value;
      if (f === "pending") tasks = tasks.filter((t) => t.status === "pending");
      if (f === "completed") tasks = tasks.filter((t) => t.status === "completed");
      if (f === "consult") tasks = tasks.filter((t) => t.mode === "consult");
      if (f === "execute") tasks = tasks.filter((t) => t.mode === "execute");
      $("taskList").innerHTML =
        (tasks || [])
          .map(
            (t) => `<div class="item">
          <strong>${escapeHtml(t.title || t.id)}</strong>
          <div class="meta">${escapeHtml(t.status)} · ${escapeHtml(t.mode || "")}</div>
          ${
            t.mode === "consult" && t.status === "pending"
              ? `<div class="actions"><button class="primary btn-run-t" data-id="${t.id}">Run consult</button></div>`
              : ""
          }
        </div>`
          )
          .join("") || `<div class="empty">No tasks.</div>`;
      document.querySelectorAll(".btn-run-t").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/tasks/${b.dataset.id}/run`, {
            method: "POST",
            body: "{}",
          });
          loadTasks();
        };
      });
    } catch (err) {
      $("taskList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshTasks").onclick = loadTasks;
  $("taskFilter").onchange = loadTasks;
  $("btnCreateTask").onclick = async () => {
    try {
      await api(`/companies/${state.companyId}/tasks`, {
        method: "POST",
        body: JSON.stringify({
          agent_instance_id: $("taskAgent").value,
          title: $("taskTitle").value.trim() || "Task",
          instruction: $("taskInstruction").value.trim() || "",
          mode: $("taskMode").value,
        }),
      });
      $("taskTitle").value = "";
      $("taskInstruction").value = "";
      loadTasks();
      refreshInboxBadge();
    } catch (err) {
      alert(err.message);
    }
  };

  // ----- Approvals -----
  async function loadApprovals() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/approvals`);
      $("approvalList").innerHTML =
        (list || [])
          .map(
            (a) => `<div class="item">
          <strong>${escapeHtml(a.action)}</strong>
          <div class="meta">${escapeHtml(a.status)} · ${escapeHtml(a.reason || "")}</div>
          ${
            a.status === "pending"
              ? `<div class="actions">
            <button class="success btn-rev" data-id="${a.id}" data-d="approved">Approve</button>
            <button class="danger btn-rev" data-id="${a.id}" data-d="rejected">Reject</button>
          </div>`
              : ""
          }
        </div>`
          )
          .join("") || `<div class="empty">No approvals.</div>`;
      document.querySelectorAll(".btn-rev").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/approvals/${b.dataset.id}/review`, {
            method: "POST",
            body: JSON.stringify({ status: b.dataset.d, comment: "workspace" }),
          });
          loadApprovals();
          refreshInboxBadge();
        };
      });
    } catch (err) {
      $("approvalList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshApprovals").onclick = loadApprovals;

  // ----- Consult -----
  $("btnConsult").onclick = async () => {
    const log = $("consultResult");
    try {
      const task = await api(`/companies/${state.companyId}/tasks`, {
        method: "POST",
        body: JSON.stringify({
          agent_instance_id: $("consultAgent").value,
          title: $("consultTitle").value.trim() || "Consultation",
          instruction: $("consultQuestion").value.trim(),
          mode: "consult",
        }),
      });
      const ran = await api(`/companies/${state.companyId}/tasks/${task.id}/run`, {
        method: "POST",
        body: "{}",
      });
      log.textContent = JSON.stringify(ran, null, 2);
    } catch (err) {
      log.textContent = err.message;
    }
  };

  // ----- Directory -----
  async function listDirectory(skill) {
    if (!state.companyId) return;
    try {
      let path = `/companies/${state.companyId}/directory`;
      if (skill) path += `?skill=${encodeURIComponent(skill)}`;
      const list = await api(path);
      $("dirList").innerHTML =
        (list || [])
          .map(
            (e) => `<div class="agent-card">
          <h4>${escapeHtml(e.name || e.agent_name || e.id)}</h4>
          <div class="muted" style="font-size:.8rem">${escapeHtml((e.skills || []).join(", "))}</div>
        </div>`
          )
          .join("") || `<div class="empty">No matches.</div>`;
    } catch (err) {
      $("dirList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnListDir").onclick = () => listDirectory();
  $("btnSearchDir").onclick = () => listDirectory($("dirSkill").value.trim());

  // ----- Knowledge -----
  $("btnAddKnowledge").onclick = async () => {
    try {
      await api(`/companies/${state.companyId}/knowledge`, {
        method: "POST",
        body: JSON.stringify({
          title: $("knowTitle").value.trim(),
          content: $("knowContent").value.trim(),
        }),
      });
      $("knowTitle").value = "";
      $("knowContent").value = "";
      alert("Knowledge added");
    } catch (err) {
      alert(err.message);
    }
  };
  $("btnSearchKnow").onclick = async () => {
    try {
      const hits = await api(`/companies/${state.companyId}/knowledge/search`, {
        method: "POST",
        body: JSON.stringify({ query: $("knowQuery").value.trim() }),
      });
      $("knowResults").innerHTML =
        (hits || [])
          .map(
            (h) => `<div class="item"><strong>${escapeHtml(h.title || h.id)}</strong>
          <div class="meta">${escapeHtml((h.snippet || h.content || "").slice(0, 160))}</div></div>`
          )
          .join("") || `<div class="empty">No hits.</div>`;
    } catch (err) {
      $("knowResults").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  };

  // ----- Delegation -----
  async function loadDelegations() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/delegation-requests`);
      $("delList").innerHTML =
        (list || [])
          .map(
            (d) => `<div class="item">
          <strong>${escapeHtml(d.title || d.id)}</strong>
          <div class="meta">${escapeHtml(d.status)} · ${escapeHtml(d.capability || "")}</div>
          ${
            d.status === "pending" || d.status === "accepted"
              ? `<div class="actions"><button class="primary btn-exd" data-id="${d.id}">Execute</button></div>`
              : ""
          }
        </div>`
          )
          .join("") || `<div class="empty">No delegations.</div>`;
      document.querySelectorAll(".btn-exd").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/delegation-requests/${b.dataset.id}/execute`, {
            method: "POST",
            body: "{}",
          });
          loadDelegations();
        };
      });
    } catch (err) {
      $("delList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshDel").onclick = loadDelegations;
  $("btnCreateDel").onclick = async () => {
    try {
      await api(`/companies/${state.companyId}/delegation-requests`, {
        method: "POST",
        body: JSON.stringify({
          source_agent_instance_id: $("delSource").value,
          target_agent_instance_id: $("delTarget").value,
          capability: $("delCapability").value.trim(),
          title: $("delTitle").value.trim(),
          instruction: $("delInstruction").value.trim(),
        }),
      });
      loadDelegations();
    } catch (err) {
      alert(err.message);
    }
  };

  // ----- Automation -----
  async function loadAutomations() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/automations`);
      $("autoList").innerHTML =
        (list || [])
          .map(
            (r) => `<div class="item">
          <strong>${escapeHtml(r.name || r.id)}</strong>
          <div class="meta">${escapeHtml(r.trigger_type || "")} · ${escapeHtml(r.is_active ? "active" : "off")}</div>
        </div>`
          )
          .join("") || `<div class="empty">No rules.</div>`;
    } catch (err) {
      $("autoList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshAuto").onclick = loadAutomations;
  $("btnCreateAuto").onclick = async () => {
    try {
      const trigger = $("autoTrigger").value;
      const body = {
        name: $("autoName").value.trim() || "Rule",
        agent_instance_id: $("autoAgent").value,
        trigger_type: trigger,
        task_title_template: $("autoTitleTpl").value.trim() || "Auto task",
        task_instruction_template: $("autoInstrTpl").value.trim() || "Run automated work",
      };
      if (trigger === "schedule") body.cron = $("autoExpr").value.trim() || "0 8 * * *";
      else body.event_type = $("autoExpr").value.trim() || "demo.event";
      await api(`/companies/${state.companyId}/automations`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      loadAutomations();
    } catch (err) {
      alert(err.message);
    }
  };
  if ($("btnTickAuto"))
    $("btnTickAuto").onclick = async () => {
      try {
        await api(`/companies/${state.companyId}/automations/tick`, {
          method: "POST",
          body: "{}",
        });
        loadAutomations();
      } catch (err) {
        alert(err.message);
      }
    };
  if ($("btnFireEvent"))
    $("btnFireEvent").onclick = async () => {
      try {
        await api(`/companies/${state.companyId}/automations/events`, {
          method: "POST",
          body: JSON.stringify({
            event_type: $("autoExpr").value.trim() || "demo.event",
            payload: { booking_id: "B-DEMO" },
          }),
        });
        loadAutomations();
      } catch (err) {
        alert(err.message);
      }
    };

  // ----- Governance -----
  async function loadGovernance() {
    if (!state.companyId) return;
    try {
      const [overview, agents, audit] = await Promise.all([
        api(`/companies/${state.companyId}/governance/overview`).catch(() => null),
        api(`/companies/${state.companyId}/governance/agents`).catch(() => []),
        api(`/companies/${state.companyId}/governance/audit?limit=20`).catch(() => []),
      ]);
      const o = overview || {};
      $("govStats").innerHTML = [
        ["Agents", o.agent_count ?? "—"],
        ["Tasks", o.task_count ?? "—"],
        ["Approvals", o.approval_count ?? "—"],
        ["Experiences", o.experience_count ?? "—"],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n">${escapeHtml(String(n))}</div><div class="l">${l}</div></div>`
        )
        .join("");
      $("govAgents").innerHTML =
        (agents || [])
          .map(
            (a) =>
              `<div class="item">${escapeHtml(a.name || a.id)}<div class="meta">${escapeHtml(JSON.stringify(a).slice(0, 100))}</div></div>`
          )
          .join("") || `<div class="empty">No data</div>`;
      $("govAudit").innerHTML =
        (audit || [])
          .map(
            (a) =>
              `<div class="item">${escapeHtml(a.action)}<div class="meta">${escapeHtml(a.status)} · ${escapeHtml(a.resource_type || "")}</div></div>`
          )
          .join("") || `<div class="empty">No audit rows</div>`;
    } catch (err) {
      $("govStats").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshGov")) $("btnRefreshGov").onclick = loadGovernance;

  // ----- Chat -----
  let chatConversationId = null;

  async function loadChat() {
    await loadAgentOptions();
  }

  async function refreshChatMessages() {
    if (!chatConversationId || !state.companyId) return;
    try {
      const msgs = await api(
        `/companies/${state.companyId}/conversations/${chatConversationId}/messages`
      );
      const thread = $("chatThread");
      if (!thread) return;
      thread.innerHTML =
        (msgs || [])
          .map((m) => {
            const role = (m.role || "agent").toLowerCase();
            const cls =
              role === "human" || role === "user"
                ? "human"
                : role === "system"
                  ? "system"
                  : "agent";
            return `<div class="bubble ${cls}"><div class="who">${escapeHtml(role)}</div>${escapeHtml(m.content || "")}</div>`;
          })
          .join("") || `<div class="empty">No messages yet. Say hello.</div>`;
      thread.scrollTop = thread.scrollHeight;
    } catch (err) {
      const log = $("chatLog");
      if (log) {
        log.classList.remove("hidden-log");
        log.textContent = err.message;
      }
    }
  }

  $("btnChatStart").onclick = async () => {
    try {
      const agentId = $("chatAgent").value;
      const title = $("chatTitle").value || "Chat";
      const conv = await api(`/companies/${state.companyId}/conversations`, {
        method: "POST",
        body: JSON.stringify({ agent_instance_id: agentId, title }),
      });
      chatConversationId = conv.id;
      $("chatMeta").textContent = "Conversation " + conv.id.slice(0, 8) + "…";
      await refreshChatMessages();
    } catch (err) {
      const log = $("chatLog");
      log.classList.remove("hidden-log");
      log.textContent = err.message;
    }
  };

  function setChatBusy(busy) {
    const typing = $("chatTyping");
    const btn = $("btnChatSend");
    const input = $("chatInput");
    if (typing) typing.classList.toggle("hidden", !busy);
    if (btn) {
      btn.disabled = !!busy;
      btn.textContent = busy ? "Sending…" : "Send";
    }
    if (input) input.disabled = !!busy;
  }

  $("btnChatSend").onclick = async () => {
    if (!chatConversationId) {
      const log = $("chatLog");
      log.classList.remove("hidden-log");
      log.textContent = "Start a conversation first.";
      return;
    }
    const content = $("chatInput").value.trim();
    if (!content) return;
    setChatBusy(true);
    const log = $("chatLog");
    if (log) {
      log.classList.add("hidden-log");
      log.textContent = "";
    }
    // Optimistic human bubble while waiting for agent
    const thread = $("chatThread");
    if (thread) {
      thread.insertAdjacentHTML(
        "beforeend",
        `<div class="bubble human"><div class="who">human</div>${escapeHtml(content)}</div>`
      );
      thread.scrollTop = thread.scrollHeight;
    }
    $("chatInput").value = "";
    try {
      await api(`/companies/${state.companyId}/conversations/${chatConversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content,
          create_task: !!$("chatCreateTask").checked,
          task_mode: $("chatTaskMode").value || "consult",
        }),
      });
      await refreshChatMessages();
    } catch (err) {
      if (log) {
        log.classList.remove("hidden-log");
        log.textContent = err.message || "Chat failed";
      }
      // Refresh to drop optimistic-only state if server rejected
      try {
        await refreshChatMessages();
      } catch (_) {}
    } finally {
      setChatBusy(false);
    }
  };


  // ----- Policy simulate -----
  if ($("btnSimulate"))
    $("btnSimulate").onclick = async () => {
      const log = $("simResult");
      try {
        let args = {};
        try {
          args = JSON.parse($("simArgs").value || "{}");
        } catch {
          throw new Error("Arguments must be valid JSON");
        }
        const res = await api(`/companies/${state.companyId}/policies/simulate`, {
          method: "POST",
          body: JSON.stringify({
            agent_instance_id: $("simAgent").value,
            tool_name: $("simTool").value.trim(),
            arguments: args,
            context: {},
          }),
        });
        log.textContent = JSON.stringify(res, null, 2);
      } catch (err) {
        log.textContent = err.message;
      }
    };

  // ----- Departments -----
  async function loadDepartments() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/departments`);
      $("deptList").innerHTML =
        (list || [])
          .map(
            (d) =>
              `<div class="item"><strong>${escapeHtml(d.name)}</strong><div class="meta">${escapeHtml(d.id)}</div></div>`
          )
          .join("") || `<div class="empty">No departments.</div>`;
    } catch (err) {
      $("deptList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshDept")) $("btnRefreshDept").onclick = loadDepartments;
  if ($("btnCreateDept"))
    $("btnCreateDept").onclick = async () => {
      try {
        await api(`/companies/${state.companyId}/departments`, {
          method: "POST",
          body: JSON.stringify({ name: $("deptName").value.trim() }),
        });
        $("deptName").value = "";
        loadDepartments();
      } catch (err) {
        alert(err.message);
      }
    };

  // ----- Skills -----
  async function loadSkills() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/skills`);
      $("skillsList").innerHTML =
        (list || [])
          .map(
            (s) => `<div class="agent-card">
          <h4>${escapeHtml(s.name)}</h4>
          <div class="muted" style="font-size:.8rem">${escapeHtml(s.slug)} · ${s.company_id ? "company" : "platform"} · v${escapeHtml(s.version || "")}</div>
          <p style="font-size:.85rem;color:var(--muted)">${escapeHtml((s.description || "").slice(0, 100))}</p>
        </div>`
          )
          .join("") || `<div class="empty">No skills.</div>`;
    } catch (err) {
      $("skillsList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshSkills")) $("btnRefreshSkills").onclick = loadSkills;

  // ----- Usage -----
  async function loadUsage() {
    if (!state.companyId) return;
    try {
      const u = await api(`/companies/${state.companyId}/usage`);
      const plan = u.plan || u.plan_code || "—";
      $("usageStats").innerHTML = [
        ["Plan", plan],
        ["Agents", `${u.agents_used ?? u.agent_count ?? "—"} / ${u.max_agents ?? "∞"}`],
        ["Tasks today", `${u.tasks_today ?? "—"} / ${u.max_tasks_day ?? "∞"}`],
        ["Automations", `${u.automations_used ?? "—"} / ${u.max_automations ?? "∞"}`],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n" style="font-size:1.1rem">${escapeHtml(String(n))}</div><div class="l">${l}</div></div>`
        )
        .join("");
      $("usageDetail").textContent = JSON.stringify(u, null, 2);
    } catch (err) {
      $("usageStats").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshUsage")) $("btnRefreshUsage").onclick = loadUsage;

  // ----- Tools -----
  async function loadTools() {
    try {
      const list = await api("/tools");
      $("toolsList").innerHTML =
        (list || [])
          .map(
            (t) => `<div class="item">
          <strong>${escapeHtml(t.name || t.id)}</strong>
          <div class="meta">side_effect: ${escapeHtml(String(t.side_effect ?? "—"))} · risk: ${escapeHtml(String(t.risk ?? "—"))}</div>
        </div>`
          )
          .join("") || `<div class="empty">No tools registered.</div>`;
    } catch (err) {
      $("toolsList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshTools")) $("btnRefreshTools").onclick = loadTools;

  // ----- Integrations -----
  async function loadIntegrations() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/integrations`);
      $("integList").innerHTML =
        (list || [])
          .map(
            (i) => `<div class="item">
          <strong>${escapeHtml(i.name)}</strong>
          <div class="meta">${escapeHtml(i.type)} · ${escapeHtml(i.status || "")}</div>
        </div>`
          )
          .join("") || `<div class="empty">No integrations.</div>`;
    } catch (err) {
      $("integList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshInteg")) $("btnRefreshInteg").onclick = loadIntegrations;
  if ($("btnCreateInteg"))
    $("btnCreateInteg").onclick = async () => {
      const log = $("integLog");
      try {
        const body = await api(`/companies/${state.companyId}/integrations`, {
          method: "POST",
          body: JSON.stringify({
            name: $("integName").value.trim() || "Integration",
            type: $("integType").value,
            config: {},
            event_map: {},
          }),
        });
        log.textContent =
          "Created " +
          body.name +
          (body.webhook_secret ? "\nWebhook secret (once): " + body.webhook_secret : "");
        loadIntegrations();
      } catch (err) {
        log.textContent = err.message;
      }
    };

  // ----- Workflows -----
  async function loadWorkflows() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/workflows`);
      $("wfList").innerHTML =
        (list || [])
          .map(
            (w) => `<div class="item">
          <strong>${escapeHtml(w.name || w.id)}</strong>
          <div class="meta">steps: ${escapeHtml(String((w.steps || []).length))} · ${escapeHtml(w.id || "")}</div>
        </div>`
          )
          .join("") || `<div class="empty">No workflows.</div>`;
    } catch (err) {
      $("wfList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshWf")) $("btnRefreshWf").onclick = loadWorkflows;
  if ($("btnCreateWf"))
    $("btnCreateWf").onclick = async () => {
      const log = $("wfLog");
      try {
        const agentId = $("wfAgent").value;
        const body = await api(`/companies/${state.companyId}/workflows`, {
          method: "POST",
          body: JSON.stringify({
            name: $("wfName").value.trim() || "Demo workflow",
            steps: [
              {
                type: "create_task",
                agent_instance_id: agentId,
                title: "Workflow task",
                instruction: "Automated step from workflow",
                mode: "consult",
              },
              { type: "wait_approval" },
            ],
          }),
        });
        log.textContent = "Created " + JSON.stringify(body, null, 2);
        loadWorkflows();
      } catch (err) {
        log.textContent = err.message;
      }
    };

  // ----- Cost -----
  async function loadCost() {
    if (!state.companyId) return;
    try {
      const c = await api(`/companies/${state.companyId}/governance/cost`);
      $("costStats").innerHTML = [
        ["Calls", c.total_calls ?? c.call_count ?? "—"],
        ["Tokens", c.total_tokens ?? "—"],
        ["Est. cost", c.estimated_cost ?? c.total_cost ?? "—"],
        ["Budget", c.budget_status ?? c.soft_limit ?? "—"],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n" style="font-size:1.1rem">${escapeHtml(String(n))}</div><div class="l">${l}</div></div>`
        )
        .join("");
      $("costDetail").textContent = JSON.stringify(c, null, 2);
    } catch (err) {
      $("costStats").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshCost")) $("btnRefreshCost").onclick = loadCost;

  // ----- Scope check -----
  if ($("btnScopeCheck"))
    $("btnScopeCheck").onclick = async () => {
      const log = $("scopeResult");
      try {
        const res = await api(`/companies/${state.companyId}/scope-check`, {
          method: "POST",
          body: JSON.stringify({
            agent_instance_id: $("scopeAgent").value,
            instruction: $("scopeInstruction").value.trim(),
            auto_delegate: !!$("scopeAutoDel").checked,
          }),
        });
        log.textContent = JSON.stringify(res, null, 2);
      } catch (err) {
        log.textContent = err.message;
      }
    };


  // ----- Boot -----
  if ($("apiBase")) $("apiBase").value = state.apiBase;
  if ($("companyId")) $("companyId").value = state.companyId;
  if ($("userId")) $("userId").value = state.userId;
  if ($("loginCompanyId")) $("loginCompanyId").value = state.companyId;

  if (state.companyId && state.userId) {
    setConnected(true);
    refreshInboxBadge().then(() => showView("home"));
  } else {
    setConnected(false);
  }
})();
