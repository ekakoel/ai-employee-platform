(function () {
  const $ = (id) => document.getElementById(id);
  const developerMode = document.body.dataset.workspace === "developer";
  const developerViews = new Set(["tools", "policies", "scopecheck"]);
  const consoleViews = new Set([...developerViews, "integrations", "workflows", "cost", "audit", "tasks", "result-preview"]);
  const defaultView = developerMode ? "tools" : "home";

  if (developerMode) {
    document.title = "Developer Console | AI Employee Platform";
    $("brandSub").textContent = "Developer console";
    $("loginSubtitle").textContent = "Developer console";
    $("consoleLink").href = "/workspace";
    $("consoleLink").textContent = "User workspace";
  }
  
  const state = {
    apiBase: localStorage.getItem("ws_apiBase") || "/api/v1",
    companyId: localStorage.getItem("ws_companyId") || "",
    userId: localStorage.getItem("ws_userId") || "",
    accessToken: localStorage.getItem("ws_accessToken") || "",
    userName: localStorage.getItem("ws_userName") || "",
    role: localStorage.getItem("ws_role") || "",
    permissions: [],
    isPlatformAdmin: localStorage.getItem("ws_isPlatformAdmin") === "1",
  };
  try {
    state.permissions = JSON.parse(localStorage.getItem("ws_permissions") || "[]");
  } catch (_) {
    state.permissions = [];
  }

  /** View → any of these permissions required (empty = always for authenticated). */
  const VIEW_PERMISSIONS = {
    inventory: ["agent.read", "agent.manage", "task.create"],
    home: [],
    inbox: ["task.read", "approval.read"],
    chat: ["task.create", "task.read", "agent.read"],
    tasks: ["task.read", "task.create"],
    approvals: ["approval.read"],
    agents: ["agent.read"],
    marketplace: ["agent.hire", "agent.manage", "agent.read"],
    consult: ["task.create", "task.read"],
    directory: ["agent.read"],
    knowledge: ["knowledge.read"],
    delegation: ["task.create", "agent.manage"],
    automation: ["agent.manage", "task.create"],
    notifications: [],
    governance: ["governance.read", "audit.read"],
    "policy-management": ["policy.read", "policy.manage", "agent.manage"],
    users: ["team.manage"],
    departments: ["agent.manage", "team.manage"],
    teams: ["agent.manage", "team.manage"],
    skills: ["agent.manage", "agent.read"],
    learning: ["agent.manage", "knowledge.write"],
    usage: ["usage.read", "team.manage"],
    audit: ["audit.read"],
    integrations: ["integration.manage", "agent.manage"],
    workflows: ["agent.manage", "task.create"],
    cost: ["governance.read", "usage.read"],
    tools: ["__developer__"],
    policies: ["__developer__"],
    scopecheck: ["__developer__"],
    "result-preview": ["task.read"],
  };

  const ROLE_DEFAULT_VIEW = {
    owner: "home",
    ai_admin: "agents",
    manager: "inbox",
    reservation: "chat",
    member: "chat",
  };

  function hasPermission(key) {
    if (!key) return true;
    if (key === "__developer__") return !!(developerMode || state.isPlatformAdmin);
    return (state.permissions || []).includes(key);
  }

  function canAccessView(view) {
    if (developerMode) return consoleViews.has(view);
    if (developerViews.has(view)) return !!state.isPlatformAdmin;
    const need = VIEW_PERMISSIONS[view];
    if (!need || need.length === 0) return true;
    return need.some((p) => hasPermission(p));
  }

  function defaultLandingView() {
    if (developerMode) return "tools";
    const byRole = ROLE_DEFAULT_VIEW[state.role] || "home";
    if (canAccessView(byRole)) return byRole;
    return canAccessView("home") ? "home" : "chat";
  }

  function applyNavGating() {
    if (developerMode) {
      document.querySelectorAll(".nav-btn").forEach((button) => {
        button.classList.toggle("hidden", !consoleViews.has(button.dataset.view));
      });
      document.querySelectorAll(".nav-group").forEach((group) => {
        group.classList.toggle("hidden", !group.classList.contains("developer-only"));
      });
      const link = $("consoleLink");
      if (link) link.classList.remove("hidden");
      return;
    }
    document.querySelectorAll(".nav-btn").forEach((button) => {
      const view = button.dataset.view;
      button.classList.toggle("hidden", !canAccessView(view));
    });
    document.querySelectorAll(".nav-group").forEach((group) => {
      let el = group.nextElementSibling;
      let any = false;
      while (el && !el.classList.contains("nav-group")) {
        if (el.classList.contains("nav-btn") && !el.classList.contains("hidden")) any = true;
        el = el.nextElementSibling;
      }
      group.classList.toggle("hidden", !any);
    });
    const link = $("consoleLink");
    if (link) link.classList.toggle("hidden", !state.isPlatformAdmin);
  }


  let focusedTaskId = "";
  let contextualSidebar = null;
  const getMainTitles = () => Array.from(document.querySelectorAll(".view.active strong, .view.active h2, .view.active h4"))
    .map((element) => element.textContent.trim()).filter(Boolean);
  const getMainText = () => document.querySelector(".view.active")?.textContent || "";

  const titles = {
    home: ["Home", "Your work and AI team at a glance"],
    inbox: ["Inbox", "Needs your attention"],
    chat: ["Chat", "Talk with AI employees"],
    tasks: ["Tasks", "Create and track work"],
    approvals: ["Approvals", "Human authority queue"],
    agents: ["AI Employees", "Hire and manage workforce"],
    inventory: ["Inventory", "Availability products"],
    marketplace: ["Marketplace", "Install public templates"],
    consult: ["Consult", "Recommendations without side effects"],
    directory: ["Directory", "Find capability across agents"],
    knowledge: ["Knowledge", "Company memory and search"],
    delegation: ["Delegation", "AI-to-AI handoff"],
    automation: ["Automation", "Rules and triggers"],
    notifications: ["Notifications", "Alerts and updates"],
    governance: ["Governance", "Metrics and audit"],
    policies: ["Policy Simulator", "Dry-run ALLOW / APPROVAL / DENY"],
    "policy-management": ["Policies", "Rules that control AI actions"],
    users: ["Users & Roles", "Company members and role assignment"],
    departments: ["Departments", "Org structure for agents and users"],
    teams: ["Teams", "Group AI employees into pods"],
    skills: ["Skills", "Platform and company capabilities"],
    learning: ["Learning", "Agent memory and reusable experience"],
    usage: ["Plan & Usage", "Quotas and metering"],
    audit: ["Audit Log", "Trace platform activity"],
    tools: ["Tools", "Catalog side-effect and risk"],
    integrations: ["Integrations", "Webhooks, email, calendar"],
    workflows: ["Workflows", "Multi-step automation"],
    cost: ["LLM Cost", "Token usage and spend"],
    scopecheck: ["Scope Check", "Out-of-scope detection"],
    "result-preview": ["AI Work Results", "Preview"],
  };

  const resultLibrary = WorkspaceResults.create({
    getSession: () => state, api, escapeHtml, getMainTitles, getMainText,
    openPreview: () => showView("result-preview"),
    openTask: (task) => { focusedTaskId = task.id; $("taskFilter").selectedIndex = 0; showView("tasks"); },
    revise: async (task) => {
      showView("tasks");
      await loadAgentOptions();
      $("taskAgent").value = task.agent_instance_id;
      $("taskTitle").value = "Revision: " + task.title;
      $("taskMode").value = task.mode;
      $("taskInstruction").value = `Revise the result of task ${task.id}.\nOriginal instruction:\n${task.instruction}\n\nPrevious result:\n${task.result}\n\nRequested changes:\n`;
      $("taskInstruction").focus();
    },
  });

  const homeDashboard = WorkspaceHome.create({
    api, getSession: () => state, escapeHtml,
    navigate: (view) => {
      if (view === "results") contextualSidebar.results();
      else showView(view);
    },
    openTask: (task) => { focusedTaskId = task.id; $("taskFilter").selectedIndex = 0; showView("tasks"); },
    openResult: (task) => showOutputCenter(task),
  });

  const inboxDashboard = WorkspaceInbox.create({
    api, getSession: () => state, escapeHtml,
    navigate: showView,
    openTask: (task) => { focusedTaskId = task.id; $("taskFilter").selectedIndex = 0; showView("tasks"); },
    onChanged: () => { refreshInboxBadge(); resultLibrary.refresh(); contextualSidebar.refresh(); },
  });

  contextualSidebar = WorkspaceSidebar.create({
    api, getSession: () => state, escapeHtml, getMainTitles, getMainText,
    getSelectedTaskId: () => resultLibrary.getSelectedTaskId(),
    canNavigate: (view) => developerMode ? consoleViews.has(view) : !developerViews.has(view),
    getAgentId: (view) => {
      const selectors = { chat: "chatAgent", consult: "consultAgent", policies: "simAgent", scopecheck: "scopeAgent" };
      return $(selectors[view])?.value || "";
    },
    navigate: showView,
    openTask: (task) => { focusedTaskId = task.id; $("taskFilter").selectedIndex = 0; showView("tasks"); },
    openResult: showOutputCenter,
    showResults: (resetFilters) => resetFilters ? resultLibrary.showAll() : resultLibrary.refresh(),
  });
  const chatWorkspace = WorkspaceChat.create({
    api, getSession: () => state, escapeHtml,
    openResult: showOutputCenter,
    onAgentChanged: () => contextualSidebar.refresh(),
    onTaskCreated: () => { refreshInboxBadge(); contextualSidebar.refresh(); },
    openTask: (id) => { focusedTaskId = id; $("taskFilter").selectedIndex = 0; showView("tasks"); },
  });
  ["consultAgent", "simAgent", "scopeAgent"].forEach((id) => {
    $(id)?.addEventListener("change", () => contextualSidebar.refresh());
  });
  new MutationObserver(() => {
    contextualSidebar.reconcile();
    resultLibrary.reconcile();
  }).observe(document.querySelector("main"), { childList: true, subtree: true, characterData: true });

  function showOutputCenter(task) {
    if (task.result) resultLibrary.select(task);
  }

  function clearSession() {
    chatWorkspace.reset();
    inboxDashboard.reset();
    contextualSidebar.reset();
    homeDashboard.reset();
    resultLibrary.reset();
    state.companyId = "";
    state.userId = "";
    state.accessToken = "";
    state.userName = "";
    state.role = "";
    state.permissions = [];
    state.isPlatformAdmin = false;
    ["ws_companyId", "ws_userId", "ws_accessToken", "ws_refreshToken", "ws_userName", "ws_role", "ws_permissions", "ws_isPlatformAdmin"].forEach((k) =>
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
    if (opts.method && opts.method.toUpperCase() !== "GET" && !path.endsWith("/result-pin") && !opts.skipSidebarRefresh) contextualSidebar?.refresh();
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
    if (ok) resultLibrary.refresh();
    const box = $("sessionBox");
    const pill = $("statusPill");
    if (box) {
      box.innerHTML = ok
        ? `<div><strong>${escapeHtml(state.userName || "User")}</strong></div>
           <small>${developerMode ? escapeHtml(state.companyId) : escapeHtml(state.role || "member")}${state.role ? " · company workspace" : ""}</small>`
        : "<small>Not connected</small>";
    }
    if (pill) {
      pill.textContent = ok ? "Online" : "Offline";
      pill.className = ok ? "pill ok" : "pill muted";
    }
    const sub = $("brandSub");
    if (sub) sub.textContent = developerMode ? "Developer console" : (ok ? "Workspace" : "Offline");
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
    if (!canAccessView(name)) {
      name = defaultLandingView();
    }
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    const view = $("view-" + name);
    if (view) view.classList.add("active");
    const btn = document.querySelector(`.nav-btn[data-view="${name}"]`);
    if (btn) btn.classList.add("active");
    const t = titles[name] || [name, ""];
    if ($("viewTitle")) $("viewTitle").textContent = t[0];
    if ($("viewSubtitle")) $("viewSubtitle").textContent = t[1];
    contextualSidebar.show(name);

    if (name === "home") loadHome();
    if (name === "inbox") loadInbox();
    if (name === "agents") loadAgents();
    if (name === "inventory") loadInventory();
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
    if (name === "policy-management") loadPolicies();
    if (name === "users") loadUsers();
    if (name === "departments") loadDepartments();
    if (name === "teams") { loadAgentOptions(); loadTeams(); }
    if (name === "skills") loadSkills();
    if (name === "learning") { loadAgentOptions(); loadLearning(); }
    if (name === "usage") loadUsage();
    if (name === "audit") loadAudit();
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

  async function loadMeProfile() {
    try {
      const me = await api("/auth/me");
      state.role = me.role || state.role || "";
      state.permissions = me.permissions || [];
      state.isPlatformAdmin = !!me.is_platform_admin;
      state.userName = me.name || me.email || state.userName;
      localStorage.setItem("ws_role", state.role);
      localStorage.setItem("ws_permissions", JSON.stringify(state.permissions));
      localStorage.setItem("ws_isPlatformAdmin", state.isPlatformAdmin ? "1" : "0");
      localStorage.setItem("ws_userName", state.userName);
    } catch (err) {
      console.warn("loadMeProfile", err);
    }
  }


  /** Job 45 — after login/connect, reload durable inventory into process connector. */
  async function bootstrapSessionEnvironment() {
    if (!state.companyId) return;
    try {
      await api(`/companies/${state.companyId}/inventory/hydrate`, {
        method: "POST",
        body: "{}",
        skipSidebarRefresh: true,
      });
    } catch (_) {
      // No agent.manage or empty inventory — ignore
    }
  }

  async function applyAuthSession(body) {
    state.companyId = body.company_id;
    state.userId = body.user_id;
    state.accessToken = body.access_token || "";
    state.userName = body.name || body.email || "";
    state.role = body.role || "";
    state.permissions = body.permissions || [];
    state.isPlatformAdmin = !!body.is_platform_admin;
    localStorage.setItem("ws_companyId", state.companyId);
    localStorage.setItem("ws_userId", state.userId);
    localStorage.setItem("ws_accessToken", state.accessToken);
    localStorage.setItem("ws_userName", state.userName);
    localStorage.setItem("ws_role", state.role);
    localStorage.setItem("ws_permissions", JSON.stringify(state.permissions));
    localStorage.setItem("ws_isPlatformAdmin", state.isPlatformAdmin ? "1" : "0");
    if (body.refresh_token) localStorage.setItem("ws_refreshToken", body.refresh_token);
    if ($("companyId")) $("companyId").value = state.companyId;
    if ($("userId")) $("userId").value = state.userId;
    if ($("loginCompanyId")) $("loginCompanyId").value = state.companyId;
    if (!state.permissions.length) await loadMeProfile();
    applyNavGating();
    setConnected(true);
    await bootstrapSessionEnvironment();
    await refreshInboxBadge();
    showView(defaultLandingView());
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

      if (state.accessToken) await loadMeProfile();
      else {
        state.role = "owner";
        state.permissions = [];
      }
      applyNavGating();
      setConnected(true);
      await bootstrapSessionEnvironment();
      await refreshInboxBadge();
      showView(defaultLandingView());
      
      // Seed persona users for role testing (Job 36)
      for (const [role, email] of [
        ["ai_admin", "aiadmin@demo.local"],
        ["reservation", "reservation@demo.local"],
        ["manager", "manager@demo.local"],
      ]) {
        try {
          await api(`/companies/${co.id}/users`, {
            method: "POST",
            body: JSON.stringify({
              name: role.replace("_", " "),
              email,
              role,
              password: "demo12345",
            }),
          });
          log.textContent += "\nUser " + email + " (" + role + ")";
        } catch (e) {
          log.textContent += "\nUser " + email + ": " + e.message;
        }
      }

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
      await loadMeProfile();
      applyNavGating();
      setConnected(true);
      await bootstrapSessionEnvironment();
      await refreshInboxBadge();
      showView(defaultLandingView());
      log.textContent = "Connected.";
    } catch (err) {
      log.textContent = "Connect failed: " + err.message;
      setConnected(false);
    }
  };

  $("btnClearSession").onclick = clearSession;
  if ($("btnLogout")) $("btnLogout").onclick = clearSession;

  

  
  if ($("btnCreateCompany"))
    $("btnCreateCompany").onclick = async () => {
      const log = $("loginLog");
      try {
        const name = ($("newCompanyName") && $("newCompanyName").value.trim()) || "";
        if (!name) throw new Error("Isi nama company baru");
        const co = await api("/companies", {
          method: "POST",
          body: JSON.stringify({ name }),
          skipAuth: true,
        });
        if ($("loginCompanyId")) $("loginCompanyId").value = co.id;
        if ($("companyId")) $("companyId").value = co.id;
        log.textContent =
          "Company dibuat.\nID: " + co.id +
          "\n\nLanjut: isi Email + Password (min 8 karakter), lalu klik Register.\n" +
          "Role default register = member. Untuk owner + demo agents, pakai Quick start.";
      } catch (err) {
        log.textContent = "Create company failed: " + err.message;
      }
    };

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
      ["taskAgent", "consultAgent", "delSource", "delTarget", "autoAgent", "simAgent", "scopeAgent", "wfAgent", "memoryAgent", "experienceAgent", "teamAgents"].forEach(
        (id) => {
          const el = $(id);
          if (el) el.innerHTML = opts;
        }
      );
      contextualSidebar.refresh();
    } catch (_) { }
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
      const actionCount = WorkspaceInbox.buildQueue({ tasks, approvals, delegations: dels })
        .filter((item) => item.group === "action").length;
      setInboxBadge(actionCount);
      setNotifBadge((notif && notif.count) || 0);
    } catch (_) { }
  }

  // ----- Home -----
  async function loadHome() {
    await homeDashboard.load();
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
          ${!n.read_at
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
    await inboxDashboard.load();
  }

  // ----- Agents -----

  async function loadInventory() {
    if (!state.companyId) return;
    const log = $("inventoryLog");
    try {
      const data = await api(`/companies/${state.companyId}/inventory`);
      const items = data.items || [];
      if ($("inventoryStats")) {
        $("inventoryStats").innerHTML = `<div class="stat"><span class="n">${items.length}</span><span class="l">Products</span></div>`;
      }
      $("inventoryList").innerHTML =
        items
          .map(
            (row) => `<div class="item">
          <strong>${escapeHtml(row.location || row.room_type || row.id || "Product")}</strong>
          <div class="meta">${escapeHtml(row.room_type || "")} · cap ${escapeHtml(String(row.capacity ?? ""))} · ${escapeHtml(String(row.rate ?? ""))} ${escapeHtml(row.currency || "")}</div>
          <div class="meta">${escapeHtml(row.valid_from || "")} → ${escapeHtml(row.valid_to || "")} · <code>${escapeHtml(row.id || "")}</code></div>
        </div>`
          )
          .join("") || `<div class="empty">No inventory. Seed demo data below.</div>`;
    } catch (err) {
      $("inventoryList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshInventory")) $("btnRefreshInventory").onclick = loadInventory;
  if ($("btnInvSeed"))
    $("btnInvSeed").onclick = async () => {
      const log = $("inventoryLog");
      try {
        const res = await api(`/companies/${state.companyId}/demo/seed-reservation`, {
          method: "POST",
          body: "{}",
        });
        if (log) log.textContent = JSON.stringify(res, null, 2);
        loadInventory();
      } catch (err) {
        if (log) log.textContent = err.message;
      }
    };
  if ($("btnInvHydrate"))
    $("btnInvHydrate").onclick = async () => {
      const log = $("inventoryLog");
      try {
        const res = await api(`/companies/${state.companyId}/inventory/hydrate`, {
          method: "POST",
          body: "{}",
        });
        if (log) log.textContent = JSON.stringify(res, null, 2);
        loadInventory();
      } catch (err) {
        if (log) log.textContent = err.message;
      }
    };

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
      const accessAgent = $("accessAgentSelect");
      if (accessAgent) {
        accessAgent.innerHTML = (agents || [])
          .map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`)
          .join("");
      }
      const sel = $("catalogSelect");
      if (sel)
        sel.innerHTML = (catalog || [])
          .map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`)
          .join("");
      loadSubscriptions();
      loadAccessPanel();
    } catch (err) {
      $("agentList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  
  async function loadAccessPanel() {
    if (!state.companyId) return;
    const log = $("accessLog");
    try {
      // users (team.manage) — owner only; fallback empty
      let users = [];
      try {
        users = await api(`/companies/${state.companyId}/users`);
      } catch (_) {
        users = [];
      }
      const userSel = $("accessUserSelect");
      if (userSel) {
        userSel.innerHTML = (users || [])
          .map(
            (u) =>
              `<option value="${u.id}">${escapeHtml(u.name)} (${escapeHtml(u.role || "")})</option>`
          )
          .join("");
      }
      const agentId = $("accessAgentSelect") && $("accessAgentSelect").value;
      if (!agentId) {
        $("accessList").innerHTML = `<div class="empty">Hire an agent first.</div>`;
        return;
      }
      const list = await api(`/companies/${state.companyId}/agents/${agentId}/access`);
      $("accessList").innerHTML =
        (list || [])
          .map(
            (a) => `<div class="item">
          <strong>${escapeHtml(a.user_id)}</strong>
          <div class="meta">use: ${a.can_use} · manage: ${a.can_manage} · approve: ${a.can_approve}</div>
        </div>`
          )
          .join("") || `<div class="empty">No access rows for this agent.</div>`;
    } catch (err) {
      if ($("accessList"))
        $("accessList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshAccess")) $("btnRefreshAccess").onclick = loadAccessPanel;
  if ($("accessAgentSelect"))
    $("accessAgentSelect").onchange = loadAccessPanel;
  if ($("btnGrantAccess"))
    $("btnGrantAccess").onclick = async () => {
      const log = $("accessLog");
      try {
        const agentId = $("accessAgentSelect").value;
        const userId = $("accessUserSelect").value;
        if (!agentId || !userId) throw new Error("Select agent and user");
        await api(`/companies/${state.companyId}/agents/${agentId}/access`, {
          method: "POST",
          body: JSON.stringify({
            user_id: userId,
            can_use: true,
            can_manage: false,
            can_approve: false,
            is_supervisor: false,
          }),
        });
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = "Granted can_use";
        }
        loadAccessPanel();
      } catch (err) {
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = err.message;
        }
      }
    };
  if ($("btnSeedReservationDemo"))
    $("btnSeedReservationDemo").onclick = async () => {
      const log = $("accessLog");
      try {
        const res = await api(`/companies/${state.companyId}/demo/seed-reservation`, {
          method: "POST",
          body: "{}",
        });
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = "Demo reservation data: " + JSON.stringify(res, null, 2);
        }
      } catch (err) {
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = err.message;
        }
      }
    };
  if ($("btnGrantOperationalAccess"))
    $("btnGrantOperationalAccess").onclick = async () => {
      const log = $("accessLog");
      try {
        const res = await api(`/companies/${state.companyId}/agents/access/grant-operational`, {
          method: "POST",
          body: "{}",
        });
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = JSON.stringify(res, null, 2);
        }
        loadAccessPanel();
      } catch (err) {
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = err.message;
        }
      }
    };


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

  async function loadSubscriptions() {
    if (!state.companyId || !$("subList")) return;
    try {
      const list = await api(`/companies/${state.companyId}/subscriptions`);
      $("subList").innerHTML =
        (list || [])
          .map(
            (s) => `<div class="item">
          <strong>${escapeHtml(s.id)}</strong>
          <div class="meta">${escapeHtml(s.status || "")} · catalog ${escapeHtml(s.catalog_agent_id || "")}</div>
          ${s.status !== "cancelled"
                ? `<div class="actions"><button class="danger btn-cancel-sub" data-id="${s.id}">Cancel</button></div>`
                : ""
              }
        </div>`
          )
          .join("") || `<div class="empty">No subscriptions.</div>`;
      document.querySelectorAll(".btn-cancel-sub").forEach((b) => {
        b.onclick = async () => {
          await api(`/companies/${state.companyId}/subscriptions/${b.dataset.id}/cancel`, {
            method: "POST",
            body: "{}",
          });
          loadSubscriptions();
          loadAgents();
        };
      });
    } catch (err) {
      $("subList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshSubs")) $("btnRefreshSubs").onclick = loadSubscriptions;

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
            ${installed.has(t.id)
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

  function taskArtifactTags(task) {
    if (!task || !task.result) return "";
    let value = task.result;
    try { value = JSON.parse(task.result); } catch (_) { return ""; }
    if (!value || typeof value !== "object") return "";
    const tools = Array.isArray(value.tool_results) ? value.tool_results : [];
    const tags = [];
    for (const item of tools) {
      const name = item.tool || item.name || "";
      if (name === "draft_quotation") tags.push("quotation");
      else if (name === "search_availability") tags.push("availability");
      else if (name === "create_reservation") tags.push("reservation");
    }
    return [...new Set(tags)].map((t) => `<span class="tag">${t}</span>`).join(" ");
  }

  async function loadTasks() {
    if (!state.companyId) return;
    try {
      let tasks = await api(`/companies/${state.companyId}/tasks`);
      const f = $("taskFilter").value;
      if (f === "pending") tasks = tasks.filter((t) => t.status === "pending");
      if (f === "completed") tasks = tasks.filter((t) => t.status === "completed");
      if (f === "consult") tasks = tasks.filter((t) => t.mode === "consult");
      if (f === "execute") tasks = tasks.filter((t) => t.mode === "execute");
      // Job 46 — single action row; correct endpoints (/consult, /execute)
      $("taskList").innerHTML =
        (tasks || [])
          .map((t) => {
            const actions = [];
            if (t.result && String(t.result).trim()) {
              actions.push(`<button class="secondary btn-view-output" data-id="${t.id}">View result</button>`);
            }
            if (t.status === "pending" && t.mode === "consult") {
              actions.push(`<button class="primary btn-run-consult" data-id="${t.id}">Run consult</button>`);
            }
            if (t.status === "pending" && t.mode === "execute") {
              actions.push(`<button class="primary btn-run-execute" data-id="${t.id}">Run execute</button>`);
            }
            if (t.status === "waiting_approval") {
              actions.push(`<button class="secondary btn-open-approvals" data-id="${t.id}">Open approvals</button>`);
            }
            return `<div class="item" data-task-id="${escapeHtml(t.id)}" tabindex="-1">
          <strong>${escapeHtml(t.title || t.id)}</strong>
          <div class="meta">${escapeHtml(t.status)} · ${escapeHtml(t.mode || "")} ${taskArtifactTags(t)}</div>
          <div class="meta muted" style="font-size:.75rem">${escapeHtml((t.instruction || "").slice(0, 120))}</div>
          <div class="actions">${actions.join(" ")}</div>
        </div>`;
          })
          .join("") || `<div class="empty">No tasks.</div>`;

      document.querySelectorAll(".btn-view-output").forEach((b) => {
        b.onclick = () => {
          const task = tasks.find((t) => t.id === b.dataset.id);
          if (task) showOutputCenter(task);
        };
      });
      document.querySelectorAll(".btn-open-approvals").forEach((b) => {
        b.onclick = () => showView("approvals");
      });
      if (focusedTaskId) {
        const target = Array.from($("taskList").querySelectorAll("[data-task-id]")).find(
          (item) => item.dataset.taskId === focusedTaskId
        );
        if (target) {
          target.focus();
          target.scrollIntoView({ block: "center" });
        }
        focusedTaskId = "";
      }
      resultLibrary.refresh();

      document.querySelectorAll(".btn-run-consult").forEach((b) => {
        b.onclick = async () => {
          const id = b.dataset.id;
          b.disabled = true;
          b.textContent = "Running…";
          try {
            const result = await api(`/companies/${state.companyId}/tasks/${id}/consult`, {
              method: "POST",
              body: "{}",
            });
            showOutputCenter(result);
            await loadTasks();
            refreshInboxBadge();
          } catch (err) {
            alert(err.message);
            b.disabled = false;
            b.textContent = "Run consult";
          }
        };
      });
      document.querySelectorAll(".btn-run-execute").forEach((b) => {
        b.onclick = async () => {
          const id = b.dataset.id;
          b.disabled = true;
          b.textContent = "Running…";
          try {
            // Prefer policy-aware execute; fall back to execute-llm if needed
            let result;
            try {
              result = await api(`/companies/${state.companyId}/tasks/${id}/execute`, {
                method: "POST",
                body: "{}",
              });
            } catch (e1) {
              result = await api(`/companies/${state.companyId}/tasks/${id}/execute-llm`, {
                method: "POST",
                body: "{}",
              });
            }
            showOutputCenter(result);
            await loadTasks();
            refreshInboxBadge();
          } catch (err) {
            alert(err.message);
            b.disabled = false;
            b.textContent = "Run execute";
          }
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
      const task = await api(`/companies/${state.companyId}/tasks`, {
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
          ${a.status === "pending"
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
      const ran = await api(`/companies/${state.companyId}/tasks/${task.id}/consult`, {
        method: "POST",
        body: "{}",
      });
      log.textContent = JSON.stringify(ran, null, 2);
      resultLibrary.refresh();
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
          ${d.status === "pending" || d.status === "accepted"
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
  async function loadChat() {
    await chatWorkspace.load();
  }


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

  // ----- Policy management -----
  async function loadPolicies() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/policies`);
      $("policyList").innerHTML =
        (list || [])
          .map((p) => {
            const cfg = p.configuration || {};
            return `<div class="item">
          <strong>${escapeHtml(p.name)}</strong>
          <div class="meta">${escapeHtml(cfg.effect || "")} · ${escapeHtml(cfg.tool || cfg.action || "")} · ${escapeHtml(p.is_active ? "active" : "off")}</div>
        </div>`;
          })
          .join("") || `<div class="empty">No policies.</div>`;
    } catch (err) {
      $("policyList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshPolicies")) $("btnRefreshPolicies").onclick = loadPolicies;
  if ($("btnCreatePolicy"))
    $("btnCreatePolicy").onclick = async () => {
      const log = $("policyLog");
      try {
        await api(`/companies/${state.companyId}/policies`, {
          method: "POST",
          body: JSON.stringify({
            name: $("policyName").value.trim(),
            description: $("policyDescription").value.trim(),
            configuration: {
              tool: $("policyTool").value.trim(),
              effect: $("policyEffect").value,
            },
            is_active: true,
          }),
        });
        log.textContent = "Policy created.";
        loadPolicies();
      } catch (err) {
        log.textContent = err.message;
      }
    };

  // ----- Departments -----
  
  async function loadUsers() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/users`);
      $("usersList").innerHTML =
        (list || [])
          .map(
            (u) => `<div class="item">
          <strong>${escapeHtml(u.name)}</strong>
          <div class="meta">${escapeHtml(u.email)} · role: <code>${escapeHtml(u.role || u.role_id)}</code> · ${escapeHtml(u.status || "")}</div>
          <div class="row" style="margin-top:.35rem">
            <select data-user-role="${escapeHtml(u.id)}">
              ${["owner","ai_admin","manager","reservation","member"].map((r) =>
                `<option value="${r}" ${u.role === r ? "selected" : ""}>${r}</option>`
              ).join("")}
            </select>
            <button class="secondary btn-set-role" data-id="${escapeHtml(u.id)}">Update role</button>
          </div>
        </div>`
          )
          .join("") || `<div class="empty">No users.</div>`;
      document.querySelectorAll(".btn-set-role").forEach((b) => {
        b.onclick = async () => {
          const sel = document.querySelector(`select[data-user-role="${b.dataset.id}"]`);
          try {
            await api(`/companies/${state.companyId}/users/${b.dataset.id}`, {
              method: "PATCH",
              body: JSON.stringify({ role: sel.value }),
            });
            loadUsers();
          } catch (err) {
            alert(err.message);
          }
        };
      });
    } catch (err) {
      $("usersList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;
  if ($("btnCreateUser"))
    $("btnCreateUser").onclick = async () => {
      const log = $("userAdminLog");
      try {
        const body = await api(`/companies/${state.companyId}/users`, {
          method: "POST",
          body: JSON.stringify({
            name: ($("userNameInput").value || "").trim() || "New User",
            email: ($("userEmailInput").value || "").trim(),
            role: $("userRoleInput").value || "member",
            password: ($("userPasswordInput").value || "demo12345"),
          }),
        });
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = "Created " + body.email + " as " + (body.role || "");
        }
        $("userEmailInput").value = "";
        loadUsers();
      } catch (err) {
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = err.message;
        }
      }
    };

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

  // ----- Teams -----
  async function loadTeams() {
    if (!state.companyId) return;
    try {
      await loadAgentOptions();
      const list = await api(`/companies/${state.companyId}/teams`);
      $("teamList").innerHTML =
        (list || [])
          .map(
            (t) => `<div class="item">
          <strong>${escapeHtml(t.name)}</strong>
          <div class="meta">${escapeHtml(t.is_active ? "active" : "off")} · members: ${escapeHtml(String((t.member_agent_ids || []).length))}</div>
          <div class="meta">${escapeHtml(t.description || "")}</div>
        </div>`
          )
          .join("") || `<div class="empty">No teams.</div>`;
    } catch (err) {
      $("teamList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshTeams")) $("btnRefreshTeams").onclick = loadTeams;
  if ($("btnCreateTeam"))
    $("btnCreateTeam").onclick = async () => {
      try {
        const agentIds = Array.from($("teamAgents").selectedOptions || []).map((o) => o.value);
        await api(`/companies/${state.companyId}/teams`, {
          method: "POST",
          body: JSON.stringify({
            name: $("teamName").value.trim(),
            description: $("teamDescription").value.trim(),
            agent_instance_ids: agentIds,
          }),
        });
        $("teamName").value = "";
        $("teamDescription").value = "";
        loadTeams();
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
  if ($("btnCreateSkill"))
    $("btnCreateSkill").onclick = async () => {
      const log = $("skillLog");
      try {
        await api(`/companies/${state.companyId}/skills`, {
          method: "POST",
          body: JSON.stringify({
            slug: $("skillSlug").value.trim(),
            name: $("skillName").value.trim(),
            description: $("skillDescription").value.trim(),
          }),
        });
        log.textContent = "Skill created.";
        $("skillSlug").value = "";
        $("skillName").value = "";
        $("skillDescription").value = "";
        loadSkills();
      } catch (err) {
        log.textContent = err.message;
      }
    };

  // ----- Learning -----
  async function loadLearning() {
    if (!state.companyId) return;
    await Promise.all([loadMemories(), loadExperiences()]);
  }

  async function loadMemories() {
    const agentId = $("memoryAgent") && $("memoryAgent").value;
    if (!state.companyId || !agentId || !$("memoryList")) return;
    try {
      const list = await api(`/companies/${state.companyId}/agents/${agentId}/memories`);
      $("memoryList").innerHTML =
        (list || [])
          .map(
            (m) => `<div class="item">
          <strong>${escapeHtml(m.title)}</strong>
          <div class="meta">${escapeHtml(m.category || "")}</div>
          <div class="meta">${escapeHtml((m.content || "").slice(0, 180))}</div>
        </div>`
          )
          .join("") || `<div class="empty">No memories for this agent.</div>`;
    } catch (err) {
      $("memoryList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadExperiences() {
    if (!state.companyId || !$("experienceList")) return;
    try {
      const list = await api(`/companies/${state.companyId}/experiences`);
      $("experienceList").innerHTML =
        (list || [])
          .map(
            (e) => `<div class="item">
          <strong>${escapeHtml(e.problem || e.id)}</strong>
          <div class="meta">${escapeHtml(e.validation_status || "")} · confidence ${escapeHtml(String(e.confidence ?? ""))}</div>
          <div class="meta">${escapeHtml((e.lesson || e.result || "").slice(0, 180))}</div>
        </div>`
          )
          .join("") || `<div class="empty">No experiences.</div>`;
    } catch (err) {
      $("experienceList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshMemory")) $("btnRefreshMemory").onclick = loadMemories;
  if ($("memoryAgent")) $("memoryAgent").onchange = loadMemories;
  if ($("btnRefreshExperiences")) $("btnRefreshExperiences").onclick = loadExperiences;
  if ($("btnCreateMemory"))
    $("btnCreateMemory").onclick = async () => {
      try {
        await api(`/companies/${state.companyId}/agents/${$("memoryAgent").value}/memories`, {
          method: "POST",
          body: JSON.stringify({
            title: $("memoryTitle").value.trim(),
            content: $("memoryContent").value.trim(),
            category: $("memoryCategory").value.trim() || "context",
          }),
        });
        $("memoryTitle").value = "";
        $("memoryContent").value = "";
        loadMemories();
      } catch (err) {
        alert(err.message);
      }
    };
  if ($("btnCreateExperience"))
    $("btnCreateExperience").onclick = async () => {
      try {
        await api(`/companies/${state.companyId}/experiences`, {
          method: "POST",
          body: JSON.stringify({
            agent_instance_id: $("experienceAgent").value || null,
            problem: $("experienceProblem").value.trim(),
            lesson: $("experienceLesson").value.trim(),
            confidence: Number($("experienceConfidence").value || 0.4),
          }),
        });
        $("experienceProblem").value = "";
        $("experienceLesson").value = "";
        loadExperiences();
      } catch (err) {
        alert(err.message);
      }
    };

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

  // ----- Audit -----
  async function loadAudit() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/audit-logs`);
      $("auditList").innerHTML =
        (list || [])
          .slice(0, 100)
          .map(
            (a) => `<div class="item">
          <strong>${escapeHtml(a.action || a.id)}</strong>
          <div class="meta">${escapeHtml(a.status || "")} · ${escapeHtml(a.resource_type || "")} · ${escapeHtml(a.created_at || "")}</div>
        </div>`
          )
          .join("") || `<div class="empty">No audit logs.</div>`;
    } catch (err) {
      $("auditList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshAudit")) $("btnRefreshAudit").onclick = loadAudit;

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

  (async function bootSession() {
    applyNavGating();
    if (state.companyId && state.userId) {
      if (state.accessToken || state.userId) {
        try { await loadMeProfile(); } catch (_) {}
      }
      applyNavGating();
      setConnected(true);
      await bootstrapSessionEnvironment();
      await refreshInboxBadge();
      showView(defaultLandingView());
    } else {
      setConnected(false);
    }
  })();
})();
