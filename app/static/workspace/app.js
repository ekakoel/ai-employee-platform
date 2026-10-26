(function () {
  const $ = (id) => document.getElementById(id);
  const themeToggle = $("btnThemeToggle");
  const savedTheme = localStorage.getItem("ws_theme");
  document.documentElement.dataset.theme = savedTheme === "dark" ? "dark" : "light";
  function updateThemeToggle() {
    const isDark = document.documentElement.dataset.theme === "dark";
    const label = isDark ? "Use light theme" : "Use dark theme";
    if (themeToggle) {
      themeToggle.setAttribute("aria-label", label);
      themeToggle.setAttribute("title", label);
      themeToggle.setAttribute("aria-pressed", String(isDark));
    }
  }
  updateThemeToggle();
  if (themeToggle) {
    themeToggle.onclick = () => {
      const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = theme;
      localStorage.setItem("ws_theme", theme);
      updateThemeToggle();
    };
  }
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
    onboardingStatus: "complete",
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
    skills: ["agent.manage", "agent.read"],  // assign only; catalog upgrade = platform developer
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
    contract_manager: "knowledge",
    administration: "users",
    member: "chat",
    accounting: "home",
  };

  function hasPermission(key) {
    if (!key) return true;
    if (key === "__developer__") return !!(developerMode || state.isPlatformAdmin);
    return (state.permissions || []).includes(key);
  }

  function canAccessView(view) {
    if (developerMode) return consoleViews.has(view);
    if (state.onboardingStatus !== "complete") return view === "company";
    if (developerViews.has(view)) return !!state.isPlatformAdmin;
    const need = VIEW_PERMISSIONS[view];
    if (!need || need.length === 0) return true;
    return need.some((p) => hasPermission(p));
  }

  function defaultLandingView() {
    if (developerMode) return "tools";
    if (state.onboardingStatus !== "complete") return "company";
    const byRole = ROLE_DEFAULT_VIEW[state.role] || "home";
    if (canAccessView(byRole)) return byRole;
    return canAccessView("home") ? "home" : "chat";
  }

  function updateNavSections() {
    document.querySelectorAll(".nav-section").forEach((section) => {
      const buttons = Array.from(section.querySelectorAll(".nav-btn"));
      const hasVisibleView = buttons.some((button) => !button.classList.contains("hidden"));
      section.classList.toggle("hidden", !hasVisibleView);
      if (!hasVisibleView) section.open = false;
    });
  }

  function applyNavGating() {
    if (developerMode) {
      document.querySelectorAll(".nav-btn").forEach((button) => {
        button.classList.toggle("hidden", !consoleViews.has(button.dataset.view));
      });
      updateNavSections();
      const link = $("consoleLink");
      if (link) link.classList.remove("hidden");
      return;
    }
    document.querySelectorAll(".nav-btn").forEach((button) => {
      const view = button.dataset.view;
      button.classList.toggle("hidden", !canAccessView(view));
    });
    updateNavSections();
    const link = $("consoleLink");
    if (link) link.classList.toggle("hidden", !state.isPlatformAdmin);
  }


  let focusedTaskId = "";
  let contextualSidebar = null;
  const getMainTitles = () => Array.from(document.querySelectorAll(".view.active strong, .view.active h2, .view.active h4"))
    .map((element) => element.textContent.trim()).filter(Boolean);
  const getMainText = () => document.querySelector(".view.active")?.textContent || "";

  const titles = {
    company: ["Company profile", "Organization details"],
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

  let sessionVersion = 0;

  function clearSession() {
    sessionVersion++;
    hideOnboardingWizard();
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
    state.onboardingStatus = "complete";
    state.permissions = [];
    state.isPlatformAdmin = false;
    ["ws_companyId", "ws_userId", "ws_accessToken", "ws_refreshToken", "ws_userName", "ws_role", "ws_permissions", "ws_isPlatformAdmin"].forEach((k) =>
      localStorage.removeItem(k)
    );
    focusedTaskId = "";
    ["companyId", "userId"].forEach((id) => {
      if ($(id)) $(id).value = "";
    });
    setInboxBadge(0);
    setNotifBadge(0);
    applyNavGating();
    setConnected(false);
  }

  function headers(json = true, skipAuth = false) {
    const h = {};
    if (json) h["Content-Type"] = "application/json";
    if (!skipAuth) {
      if (state.accessToken) h["Authorization"] = "Bearer " + state.accessToken;
    }
    return h;
  }

  async function logoutSession() {
    const token = state.accessToken;
    clearSession();
    const version = sessionVersion;
    if (!token) return;
    let confirmed = false;
    try {
      await api("/auth/logout", { method: "POST", skipAuth: true, skipSidebarRefresh: true,
        headers: { Authorization: "Bearer " + token } });
      confirmed = true;
    } catch (_) {}
    if (version !== sessionVersion) return;
    if ($("loginLog")) {
      $("loginLog").classList.toggle("error", !confirmed);
      $("loginLog").textContent = confirmed
        ? "Signed out. Server session revoked."
        : "Signed out locally. Server session revocation was not confirmed.";
    }
  }

  function expireCurrentSession(version, token) {
    if (!token || version !== sessionVersion || token !== state.accessToken) return;
    clearSession();
    if ($("loginLog")) {
      $("loginLog").classList.add("error");
      $("loginLog").textContent = "Session expired. Please sign in again.";
    }
  }

  async function api(path, opts = {}) {
    const base = (state.apiBase || "/api/v1").replace(/\/$/, "");
    const url = path.startsWith("http") ? path : base + path;
    const version = sessionVersion;
    const token = state.accessToken;
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
      if (res.status === 401 && !opts.skipAuth && path !== "/auth/me") expireCurrentSession(version, token);
      const detail =
        data && typeof data === "object"
          ? data.detail || JSON.stringify(data)
          : text || res.statusText;
      const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      error.status = res.status;
      throw error;
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
    if (btn) {
      btn.classList.add("active");
      const section = btn.closest(".nav-section");
      if (section) section.open = true;
    }
    const t = titles[name] || [name, ""];
    if ($("viewTitle")) $("viewTitle").textContent = t[0];
    if ($("viewSubtitle")) $("viewSubtitle").textContent = t[1];
    contextualSidebar.show(name);

    if (name === "home") loadHome();
    if (name === "company") loadCompanyProfile();
    if (name === "inbox") loadInbox();
    if (name === "agents") { applyAgentActionGating(); loadAgents(); }
    if (name === "inventory") { applyInventoryGating(); loadInventory(); }
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
    if (name === "knowledge") { applyKnowledgeWriteGating(); loadKnowledge(); }
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

  function isCompanyProfileOwner(company) {
    const ownerId = company && company.owner_user_id != null ? String(company.owner_user_id) : "";
    const userId = state.userId != null ? String(state.userId) : "";
    if (!ownerId || !userId || ownerId !== userId) return false;
    // Prefer explicit owner role; allow empty role only when user id matches owner
    if (state.role && state.role !== "owner") return false;
    return true;
  }

  function applyCompanyProfileMode(company) {
    const owner = isCompanyProfileOwner(company);
    const edit = $("companyProfileEdit");
    const read = $("companyProfileRead");
    // Explicit show/hide (avoid toggle edge cases with stale class lists)
    if (edit) {
      if (owner) edit.classList.remove("hidden");
      else edit.classList.add("hidden");
    }
    if (read) {
      if (owner) read.classList.add("hidden");
      else read.classList.remove("hidden");
    }

    const complete = company && company.onboarding_status === "complete";
    // Checklist only while owner still needs to finish onboarding
    if ($("companyOnboardingHint")) {
      if (owner && !complete) $("companyOnboardingHint").classList.remove("hidden");
      else $("companyOnboardingHint").classList.add("hidden");
    }
    if ($("companyOnboardingSteps")) {
      if (owner && !complete) $("companyOnboardingSteps").classList.remove("hidden");
      else $("companyOnboardingSteps").classList.add("hidden");
    }
    if ($("companyOwnerEditHeading")) {
      if (owner) $("companyOwnerEditHeading").classList.remove("hidden");
      else $("companyOwnerEditHeading").classList.add("hidden");
    }

    if (owner) {
      if ($("companyProfileNameInput")) $("companyProfileNameInput").value = company.name || "";
      if ($("companyContactEmail")) $("companyContactEmail").value = company.contact_email || "";
      if ($("companyIndustry")) $("companyIndustry").value = company.industry || "";
      if ($("onboardCompanyName")) $("onboardCompanyName").value = company.name || "";
      if ($("onboardCompanyEmail")) $("onboardCompanyEmail").value = company.contact_email || "";
      if ($("onboardCompanyIndustry")) $("onboardCompanyIndustry").value = company.industry || "";
      if ($("btnSaveCompanyProfile")) $("btnSaveCompanyProfile").classList.remove("hidden");
    } else {
      if ($("companyReadName")) $("companyReadName").textContent = company.name || "—";
      if ($("companyReadEmail")) $("companyReadEmail").textContent = company.contact_email || "—";
      if ($("companyReadIndustry")) $("companyReadIndustry").textContent = company.industry || "—";
      if ($("companyReadStatus")) {
        $("companyReadStatus").textContent =
          company.onboarding_status === "complete" ? "Complete" : (company.onboarding_status || "Pending");
      }
    }
  }

  async function loadCompanyProfile() {
    if (!state.companyId || developerMode) return true;
    const version = sessionVersion;
    const token = state.accessToken;
    const log = $("companyProfileLog");
    try {
      const company = await api(`/companies/${state.companyId}/profile`, { skipSidebarRefresh: true });
      if (version !== sessionVersion || token !== state.accessToken) return false;
      state.onboardingStatus = company.onboarding_status;
      state.ownerUserId = company.owner_user_id || null;
      if ($("companyProfileName")) $("companyProfileName").textContent = company.name || "Company profile";
      if ($("companyOnboardingStatus")) {
        if (isCompanyProfileOwner(company)) {
          $("companyOnboardingStatus").textContent =
            company.onboarding_status === "complete"
              ? "Status: complete. You can update organization details below, or open Users & positions to invite staff."
              : "Status: pending. Fill name, contact email, and industry, then Save. Other menus stay hidden until this is complete.";
        } else {
          $("companyOnboardingStatus").textContent =
            company.onboarding_status === "complete"
              ? "Organization profile is complete (read-only for your role)."
              : "Organization profile is still pending completion by the Owner.";
        }
      }
      applyCompanyProfileMode(company);
      applyNavGating();
      if (log) log.textContent = "";
      return true;
    } catch (err) {
      if (version !== sessionVersion || token !== state.accessToken) return false;
      state.onboardingStatus = "unknown";
      applyNavGating();
      if (log) log.textContent = err.message || "Company profile unavailable";
      return false;
    }
  }

  async function saveCompanyProfile(values, log) {
    if (state.role && state.role !== "owner") {
      if (log) log.textContent = "Only the company Owner can update the profile.";
      return false;
    }
    const name = String(values.name || "").trim();
    const contactEmail = String(values.contact_email || "").trim();
    const industry = String(values.industry || "").trim();
    if (name.length < 2 || contactEmail.length < 3 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contactEmail) || industry.length < 2) {
      if (log) log.textContent = "Enter a company name, valid contact email, and industry before continuing.";
      return false;
    }
    try {
      await api(`/companies/${state.companyId}/profile`, { method: "PUT", body: JSON.stringify({
        name,
        contact_email: contactEmail,
        industry,
      }) });
      if (!await loadCompanyProfile()) throw new Error("Company profile was saved, but could not be reloaded. Please retry.");
      applyNavGating();
      if (log) log.textContent = "Company profile saved.";
      if (state.onboardingStatus === "complete" && isCompanyProfileOwner({ owner_user_id: state.ownerUserId })) {
        await routePostLoginOnboarding();
      }
      return true;
    } catch (err) {
      if (log) log.textContent = err.message || "Unable to save profile";
      return false;
    }
  }

  if ($("btnSaveCompanyProfile")) $("btnSaveCompanyProfile").onclick = async () => {
    await saveCompanyProfile({
      name: $("companyProfileNameInput").value,
      contact_email: $("companyContactEmail").value,
      industry: $("companyIndustry").value,
    }, $("companyProfileLog"));
  };

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

  function openLoginTab(name) {
    document.querySelector(`.login-tabs .tab[data-tab="${name}"]`)?.click();
  }

  if ($("btnRegisterCompany")) $("btnRegisterCompany").onclick = async () => {
    const button = $("btnRegisterCompany");
    const log = $("registrationLog");
    button.disabled = true;
    try {
      const email = $("registrationEmail").value.trim();
      const result = await api("/auth/register", { method: "POST", skipAuth: true,
        body: JSON.stringify({ company_name: $("registrationCompany").value.trim(),
          owner_name: $("registrationName").value.trim(), email,
          password: $("registrationPassword").value }) });
      $("registrationPassword").value = "";
      log.textContent = result.message || "Company created.";
      if ($("verificationPanel")) $("verificationPanel").classList.remove("hidden");
      
      // Job 93 fix — dedicated "check your email" notice + login CTA
      try {
        if ($("registerSuccessEmail")) $("registerSuccessEmail").textContent = email;
        if ($("registerSuccessPanel")) {
          document.querySelectorAll(".login-tabs .tab, .tab-panel").forEach((el) => el.classList.remove("active"));
          $("registerSuccessPanel").classList.add("active");
        }
        if ($("verificationPanel")) $("verificationPanel").classList.add("hidden");
      } catch (_) {}

      if ($("activationBanner")) {
        $("activationBanner").textContent =
          "We sent an activation link to " + email + ". Open it, then sign in. (Dev: token may appear in API logs.)";
      }
      // Dev convenience only — never block UI on token paste
      if (result.verification_token && $("verificationToken")) {
        $("verificationToken").value = result.verification_token;
      }
      if ($("loginEmail")) $("loginEmail").value = email;
    } catch (err) {
      log.textContent = err.message || "Registration failed";
    } finally {
      button.disabled = false;
    }
  };

  if ($("btnVerifyEmail")) $("btnVerifyEmail").onclick = async () => {
    const log = $("registrationLog");
    try {
      const result = await api("/auth/verify-email", { method: "POST", skipAuth: true,
        body: JSON.stringify({ token: $("verificationToken").value.trim() }) });
      $("verificationToken").value = "";
      log.textContent = result.message;
      openLoginTab("login");
      $("loginLog").textContent = result.message;
    } catch (err) {
      log.textContent = err.message || "Verification failed";
    }
  };

  if ($("btnResendVerification")) $("btnResendVerification").onclick = async () => {
    const log = $("registrationLog");
    try {
      const result = await api("/auth/request-verification", { method: "POST", skipAuth: true,
        body: JSON.stringify({ email: $("registrationEmail").value.trim() }) });
      log.textContent = result.message;
      $("verificationPanel").classList.remove("hidden");
      if (result.verification_token) $("verificationToken").value = result.verification_token;
    } catch (err) {
      log.textContent = err.message || "Unable to request verification";
    }
  };

  if ($("btnAcceptInvite")) $("btnAcceptInvite").onclick = async () => {
    const button = $("btnAcceptInvite");
    const log = $("inviteLog");
    button.disabled = true;
    try {
      const result = await api("/auth/accept-invitation", { method: "POST", skipAuth: true,
        body: JSON.stringify({ token: $("inviteToken").value.trim(),
          name: $("inviteName").value.trim(), password: $("invitePassword").value }) });
      $("invitePassword").value = "";
      $("inviteToken").value = "";
      log.textContent = result.message;
      openLoginTab("login");
      $("loginLog").textContent = result.message;
    } catch (err) {
      log.textContent = err.message || "Invitation could not be accepted";
    } finally {
      button.disabled = false;
    }
  };

  const incoming = typeof URLSearchParams === "undefined"
    ? { has: () => false }
    : new URLSearchParams(typeof location === "undefined" ? "" : location.search);
  if (incoming.has("verify")) {
    openLoginTab("register");
    $("verificationPanel").classList.remove("hidden");
    $("verificationToken").value = incoming.get("verify") || "";
  } else if (incoming.has("invite")) {
    openLoginTab("invite");
    $("inviteToken").value = incoming.get("invite") || "";
  }
  if ((incoming.has("verify") || incoming.has("invite")) && typeof history !== "undefined") {
    history.replaceState(null, "", location.pathname);
  }

  async function loadMeProfile() {
    const version = sessionVersion;
    const token = state.accessToken;
    try {
      const me = await api("/auth/me");
      if (version !== sessionVersion || token !== state.accessToken) return false;
      state.companyId = me.company_id;
      state.userId = me.user_id;
      state.role = me.role || "";
      state.permissions = me.permissions || [];
      state.isPlatformAdmin = !!me.is_platform_admin;
      state.userName = me.name || me.email || "";
      localStorage.setItem("ws_companyId", state.companyId);
      localStorage.setItem("ws_userId", state.userId);
      if ($("companyId")) $("companyId").value = state.companyId;
      if ($("userId")) $("userId").value = state.userId;
      localStorage.setItem("ws_role", state.role);
      localStorage.setItem("ws_permissions", JSON.stringify(state.permissions));
      localStorage.setItem("ws_isPlatformAdmin", state.isPlatformAdmin ? "1" : "0");
      localStorage.setItem("ws_userName", state.userName);
      return true;
    } catch (err) {
      if (version !== sessionVersion || token !== state.accessToken) return false;
      if (err.status === 401) clearSession();
      else setConnected(false);
      if ($("loginLog")) {
        $("loginLog").classList.add("error");
        $("loginLog").textContent = err.status === 401
          ? "Session expired. Please sign in again."
          : "Unable to verify session. Please try again later.";
      }
      return false;
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
    const version = sessionVersion;
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
    if (!state.permissions.length && !await loadMeProfile()) return;
    if (version !== sessionVersion) return;
    const profileLoaded = await loadCompanyProfile();
    if (version !== sessionVersion) return;
    if (!profileLoaded) {
      if (state.accessToken) {
        setConnected(true);
        showOnboardingRecovery("We could not load the company profile. Your workspace is still available; open Company profile to retry.");
      }
      return;
    }
    applyNavGating();
    setConnected(true);
    if (await routePostLoginOnboarding()) return;
    if (version !== sessionVersion) return;
    await bootstrapSessionEnvironment();
    if (version !== sessionVersion) return;
    await refreshInboxBadge();
    if (version !== sessionVersion) return;
    showView(defaultLandingView());
  }

  // ----- Quick start (Job 60: debug bootstrap API) -----
  $("btnQuickStart").onclick = async () => {
    const log = $("quickLog");
    try {
      if (log) log.textContent = "Bootstrapping demo workspace (debug only)…";
      const body = await api("/demo/bootstrap", {
        method: "POST",
        body: "{}",
        skipAuth: true,
      });
      const ownerEmail = body.owner_email || (body.users && body.users[0] && body.users[0].email);
      if (log) {
        log.textContent =
          "Company: " + (body.company_name || body.company_id) +
          "\nID: " + body.company_id +
          "\nPassword: " + (body.password || "demo12345") +
          "\nAccounts:";
        (body.users || []).forEach((u) => {
          log.textContent += "\n  " + u.email + " (" + u.role + ")";
        });
        (body.agents || []).forEach((a) => {
          if (a.name) log.textContent += "\nHired: " + a.name;
          if (a.error) log.textContent += "\nHire note: " + a.error;
        });
      }
      if ($("loginEmail") && ownerEmail) $("loginEmail").value = ownerEmail;
      if ($("loginPassword")) $("loginPassword").value = body.password || "demo12345";

      // Auto sign-in as owner
      const tok = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: ownerEmail,
          password: body.password || "demo12345",
        }),
        skipAuth: true,
      });
      if (log) log.textContent += "\nSigned in as " + ownerEmail;
      await applyAuthSession(tok);
    } catch (err) {
      if (log) {
        log.textContent =
          "Quick start failed: " + err.message +
          "\n\nChecklist: hard-refresh app.js; DEBUG=true or APP_ENV=development; restart uvicorn; use /developer." +
          "\nAPI must be POST /api/v1/demo/bootstrap without Bearer token." +
          "\nIf still 401, app.js cache is stale — Ctrl+F5.";
      }
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
      if (!await loadMeProfile()) throw new Error("Session verification failed");
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

  $("btnClearSession").onclick = logoutSession;
  if ($("btnLogout")) $("btnLogout").onclick = logoutSession;

  

  
  // Job 58 — simplified email + password login (no public register)
  function togglePasswordVisibility(inputId, btnId) {
    const input = $(inputId);
    const btn = $(btnId);
    if (!input || !btn) return;
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.textContent = show ? "Hide" : "Show";
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  }

  if ($("btnToggleLoginPassword")) {
    $("btnToggleLoginPassword").onclick = () =>
      togglePasswordVisibility("loginPassword", "btnToggleLoginPassword");
  }
  if ($("btnToggleResetPassword")) {
    $("btnToggleResetPassword").onclick = () =>
      togglePasswordVisibility("resetPassword", "btnToggleResetPassword");
  }

  // Remember email
  try {
    const saved = localStorage.getItem("ws_login_email");
    if (saved && $("loginEmail")) $("loginEmail").value = saved;
    if (saved && $("loginRemember")) $("loginRemember").checked = true;
  } catch (_) {}

  if ($("btnForgotPassword") && $("btnForgotPassword").tagName === "BUTTON") {
    $("btnForgotPassword").onclick = () => {
      if ($("forgotPanel")) $("forgotPanel").classList.remove("hidden");
      if ($("forgotEmail") && $("loginEmail")) $("forgotEmail").value = $("loginEmail").value;
    };
  } else if ($("btnForgotPassword") && $("btnForgotPassword").tagName === "A" && $("loginEmail")) {
    // Pass email to dedicated page
    $("btnForgotPassword").addEventListener("click", (e) => {
      const email = ($("loginEmail").value || "").trim();
      if (email) {
        e.preventDefault();
        location.href = "/forgot-password?email=" + encodeURIComponent(email);
      }
    });
  }
  if ($("btnBackToLogin")) {
    $("btnBackToLogin").onclick = () => {
      if ($("forgotPanel")) $("forgotPanel").classList.add("hidden");
    };
  }

  if ($("btnRequestReset")) {
    $("btnRequestReset").onclick = async () => {
      const log = $("forgotLog");
      try {
        const email = (($("forgotEmail") && $("forgotEmail").value) || "").trim();
        const res = await api("/auth/forgot-password", {
          method: "POST",
          body: JSON.stringify({ email }),
          skipAuth: true,
        });
        if (log) log.textContent = res.message || "If the account exists, instructions were issued.";
        if (res.reset_token) {
          if ($("resetTokenWrap")) $("resetTokenWrap").classList.remove("hidden");
          if ($("resetPasswordWrap")) $("resetPasswordWrap").classList.remove("hidden");
          if ($("btnDoReset")) $("btnDoReset").classList.remove("hidden");
          if ($("resetToken")) $("resetToken").value = res.reset_token;
          if (log) log.textContent += "\n\n[Dev] Reset token filled below. Set a new password.";
        }
      } catch (err) {
        if (log) {
          log.textContent = err.message;
          log.classList.add("error");
        }
      }
    };
  }

  if ($("btnDoReset")) {
    $("btnDoReset").onclick = async () => {
      const log = $("forgotLog");
      try {
        const res = await api("/auth/reset-password", {
          method: "POST",
          body: JSON.stringify({
            token: ($("resetToken") && $("resetToken").value.trim()) || "",
            new_password: ($("resetPassword") && $("resetPassword").value) || "",
          }),
          skipAuth: true,
        });
        if (log) {
          log.classList.remove("error");
          log.textContent = res.message || "Password updated.";
        }
      } catch (err) {
        if (log) {
          log.classList.add("error");
          log.textContent = err.message;
        }
      }
    };
  }

  if ($("btnCreateCompany")) {
    $("btnCreateCompany").onclick = async () => {
      const log = $("loginLog");
      if (log) {
        log.textContent =
          "Create company is restricted to platform developers.\nOpen /developer → Provision company.";
      }
    };
  }


  // Job 93 — post-login onboarding wizard
  let onboardHiredAgentId = null;
  let onboardHiredAgentName = "";
  let onboardCatalogItems = [];
  function setOnboardStep(n) {
    document.querySelectorAll("#onboardingWizard .onboard-steps span").forEach((el) => {
      el.classList.toggle("active", String(el.getAttribute("data-step")) === String(n));
    });
    ["1", "2", "3"].forEach((i) => {
      const p = $("onboardPanel" + i);
      if (p) p.classList.toggle("hidden", String(i) !== String(n));
    });
  }
  function showOnboardingWizard(step) {
    const w = $("onboardingWizard");
    if (!w) {
      console.warn("onboardingWizard missing");
      return;
    }
    w.classList.remove("hidden");
    w.style.display = "grid";
    w.style.visibility = "visible";
    w.style.opacity = "1";
    w.style.zIndex = "9999";
    document.documentElement.classList.add("onboarding-open");
    document.body.classList.add("onboarding-open");
    const notice = $("onboardRecoveryNotice");
    if (notice) {
      notice.classList.add("hidden");
      notice.textContent = "";
    }
    // The workspace stays rendered behind the modal. This guarantees that a
    // recoverable wizard/UI error can never leave an authenticated user on a
    // blank page.
    setOnboardStep(step || 1);
  }
  function hideOnboardingWizard() {
    const w = $("onboardingWizard");
    if (w) {
      w.classList.add("hidden");
      w.style.display = "none";
    }
    document.documentElement.classList.remove("onboarding-open");
    document.body.classList.remove("onboarding-open");
  }
  function showOnboardingRecovery(message) {
    showOnboardingWizard(1);
    const notice = $("onboardRecoveryNotice");
    if (!notice) return;
    notice.classList.remove("hidden");
    notice.textContent = message;
  }
  async function routePostLoginOnboarding() {
    const version = sessionVersion;
    const token = state.accessToken;
    try {
      if (!state.companyId) {
        // No company yet — still show step 1 if wizard exists
        showOnboardingWizard(1);
        return true;
      }
      if (state.onboardingStatus !== "complete") {
        showOnboardingWizard(1);
        return true;
      }
      const agents = await api(`/companies/${state.companyId}/agents`);
      if (version !== sessionVersion || token !== state.accessToken) return true;
      if (!agents || !agents.length) {
        showOnboardingWizard(2);
        await loadOnboardingCatalog();
        return true;
      }
      hideOnboardingWizard();
      return false;
    } catch (err) {
      if (version !== sessionVersion || token !== state.accessToken) return true;
      console.warn("routePostLoginOnboarding", err);
      hideOnboardingWizard();
      return false;
    }
  }
  if ($("btnOnboardGoCompany")) {
    $("btnOnboardGoCompany").onclick = () => {
      hideOnboardingWizard();
      try { showView("company"); } catch (_) {}
    };
  }
  if ($("btnOnboardSaveCompany")) {
    $("btnOnboardSaveCompany").onclick = async () => {
      const button = $("btnOnboardSaveCompany");
      if (button) button.disabled = true;
      try {
        const ok = await saveCompanyProfile({
          name: $("onboardCompanyName").value,
          contact_email: $("onboardCompanyEmail").value,
          industry: $("onboardCompanyIndustry").value,
        }, $("onboardCompanyLog"));
        if (ok) {
          // Profile PUT marks onboarding complete — continue wizard to hire
          setOnboardStep(2);
          await loadOnboardingCatalog();
        }
      } finally {
        if (button) button.disabled = false;
      }
    };
  }
  async function loadOnboardingCatalog() {
    const select = $("onboardAgentCatalog");
    const description = $("onboardAgentDescription");
    const log = $("onboardHireLog");
    const hireButton = $("btnOnboardHire");
    if (!select) return false;
    const version = sessionVersion;
    const token = state.accessToken;
    if (hireButton) hireButton.disabled = true;
    if (log) log.textContent = "Loading available AI employees…";
    try {
      const catalog = await api("/agent-catalog");
      if (version !== sessionVersion || token !== state.accessToken) return false;
      onboardCatalogItems = Array.isArray(catalog) ? catalog : [];
      select.innerHTML = onboardCatalogItems.map((item) =>
        `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`
      ).join("");
      if (onboardCatalogItems.length) {
        select.value = onboardCatalogItems[0].id;
        if (description) description.textContent = onboardCatalogItems[0].description || "";
        if (hireButton) hireButton.disabled = false;
        if (log) log.textContent = "";
        return true;
      }
      if (description) description.textContent = "";
      if (log) log.textContent = "No AI Employees are currently available in the catalog. Reload to try again.";
      return false;
    } catch (err) {
      if (version !== sessionVersion || token !== state.accessToken) return false;
      if (description) description.textContent = "";
      if (log) log.textContent = `Could not load AI Employee catalog: ${err.message}. Reload to try again.`;
      return false;
    }
  }
  if ($("onboardAgentCatalog")) {
    $("onboardAgentCatalog").addEventListener("change", () => {
      const selected = onboardCatalogItems.find((item) => item.id === $("onboardAgentCatalog").value);
      if ($("onboardAgentDescription")) $("onboardAgentDescription").textContent = selected?.description || "";
    });
  }
  if ($("btnOnboardRetryCatalog")) $("btnOnboardRetryCatalog").onclick = loadOnboardingCatalog;
  if ($("btnOnboardHire")) {
    $("btnOnboardHire").onclick = async () => {
      const log = $("onboardHireLog");
      const button = $("btnOnboardHire");
      const selected = onboardCatalogItems.find((item) => item.id === $("onboardAgentCatalog").value);
      if (!selected) {
        if (log) log.textContent = "Choose an AI Employee from the available catalog.";
        return;
      }
      const version = sessionVersion;
      const token = state.accessToken;
      try {
        if (button) button.disabled = true;
        if (log) log.textContent = "Hiring…";
        const nameInput = $("onboardAgentName");
        const hireName = (nameInput && nameInput.value.trim()) || selected.name;
        const hired = await api(`/companies/${state.companyId}/agents/${selected.id}/hire`, {
          method: "POST",
          body: JSON.stringify({ name: hireName }),
        });
        if (version !== sessionVersion || token !== state.accessToken) return;
        onboardHiredAgentId = hired.id || hired.agent_instance_id || "";
        if (!onboardHiredAgentId) throw new Error("Agent was hired, but the server response did not include its ID.");
        onboardHiredAgentName = hireName;
        if (log) log.textContent = "Hired. Configure next.";
        if ($("onboardAgentNameAfterHire")) $("onboardAgentNameAfterHire").value = hireName;
        setOnboardStep(3);
      } catch (err) {
        if (log) log.textContent = err.message || "Hire failed";
      } finally {
        if (button && onboardCatalogItems.length) button.disabled = false;
      }
    };
  }
  async function finishOnboardConfig() {
    const log = $("onboardConfigLog");
    try {
      const name = ($("onboardAgentNameAfterHire") && $("onboardAgentNameAfterHire").value.trim()) || "";
      if (onboardHiredAgentId && name && name !== onboardHiredAgentName) {
        await api(`/companies/${state.companyId}/agents/${onboardHiredAgentId}`, {
          method: "PATCH",
          body: JSON.stringify({ name }),
        });
        onboardHiredAgentName = name;
      }
      // Ensure client state reflects completed onboarding (server already set on profile save)
      state.onboardingStatus = "complete";
      try { applyNavGating(); } catch (_) {}
      hideOnboardingWizard();

      // Job 97b — open chat with hired agent + owner concierge welcome
      if (onboardHiredAgentId) {
        try {
          showView("chat");
          const created = await api(`/companies/${state.companyId}/conversations`, {
            method: "POST",
            body: JSON.stringify({
              agent_instance_id: onboardHiredAgentId,
              title: "Getting started with your AI Employee",
              owner_concierge: true,
            }),
          });
          if (typeof chatWorkspace !== "undefined" && chatWorkspace && chatWorkspace.openAgent) {
            await chatWorkspace.openAgent(onboardHiredAgentId, { forceNew: true });
          } else if (typeof chatWorkspace !== "undefined" && chatWorkspace && chatWorkspace.load) {
            await chatWorkspace.load(true);
          }
          if (log) log.textContent = "Setup complete. Your AI Employee is ready in Chat.";
        } catch (chatErr) {
          console.warn("concierge chat", chatErr);
          try { showView("home"); } catch (_) {}
          if (log) log.textContent = "Setup complete. Open Chat to meet your AI Employee.";
        }
      } else {
        try { showView("home"); } catch (_) { try { showView("agents"); } catch (__) {} }
      }
    } catch (err) {
      if (log) log.textContent = err.message || "Could not finish";
    }
  }
  if ($("btnOnboardFinish")) $("btnOnboardFinish").onclick = () => finishOnboardConfig();
  if ($("btnOnboardSkipConfig")) $("btnOnboardSkipConfig").onclick = async () => {
    state.onboardingStatus = "complete";
    try { applyNavGating(); } catch (_) {}
    hideOnboardingWizard();
    if (onboardHiredAgentId) {
      try {
        showView("chat");
        await api(`/companies/${state.companyId}/conversations`, {
          method: "POST",
          body: JSON.stringify({
            agent_instance_id: onboardHiredAgentId,
            title: "Getting started with your AI Employee",
            owner_concierge: true,
          }),
        });
        if (chatWorkspace && chatWorkspace.openAgent) {
          await chatWorkspace.openAgent(onboardHiredAgentId, { forceNew: true });
        } else if (chatWorkspace && chatWorkspace.load) {
          await chatWorkspace.load(true);
        }
      } catch (_) {
        try { showView("home"); } catch (__) {}
      }
    } else {
      try { showView("home"); } catch (_) {}
    }
  };
  if ($("btnGoLoginAfterRegister")) {
    $("btnGoLoginAfterRegister").onclick = () => {
      if ($("registerSuccessPanel")) $("registerSuccessPanel").classList.remove("active");
      openLoginTab("login");
    };
  }
  if ($("btnResendFromNotice")) {
    $("btnResendFromNotice").onclick = () => {
      if ($("btnResendVerification")) $("btnResendVerification").click();
      const log = $("registerSuccessLog");
      if (log) log.textContent = "If the account needs activation, another email was requested.";
    };
  }

  
  // Job 94 — brand orb follows pointer (subtle)
  
  // Job 94 fix — pupils follow pointer inside brand orb
  (function brandPupils() {
    const orb = document.getElementById("brandOrb");
    if (!orb || typeof orb.querySelectorAll !== "function") return;
    const pupils = orb.querySelectorAll(".ae-pupil");
    if (!pupils.length) return;
    window.addEventListener("pointermove", (e) => {
      const r = orb.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      if (!r.width || !r.height) return;
      let dx = (e.clientX - cx) / (r.width / 2);
      let dy = (e.clientY - cy) / (r.height / 2);
      if (!Number.isFinite(dx) || !Number.isFinite(dy)) return;
      dx = Math.max(-1, Math.min(1, dx)) * 2.5;
      dy = Math.max(-1, Math.min(1, dy)) * 2;
      pupils.forEach((p) => {
        p.style.animation = "none";
        p.setAttribute("transform", "translate(" + dx + ", " + dy + ")");
      });
    });
  })();

  (function bindBrandOrb() {
    const gate = document.getElementById("loginGate");
    const orb = document.getElementById("brandOrb");
    if (!gate || !orb) return;
    let raf = 0;
    let tx = 0, ty = 0, cx = 0, cy = 0;
    function tick() {
      cx += (tx - cx) * 0.12;
      cy += (ty - cy) * 0.12;
      gate.style.setProperty("--mx", cx.toFixed(4));
      gate.style.setProperty("--my", cy.toFixed(4));
      raf = requestAnimationFrame(tick);
    }
    gate.addEventListener("pointermove", (e) => {
      const r = gate.getBoundingClientRect();
      tx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      ty = ((e.clientY - r.top) / r.height - 0.5) * 2;
      tx = Math.max(-1, Math.min(1, tx));
      ty = Math.max(-1, Math.min(1, ty));
    });
    gate.addEventListener("pointerleave", () => { tx = 0; ty = 0; });
    raf = requestAnimationFrame(tick);
  })();

  // Job 94 — smoother tab panel transitions
  document.querySelectorAll(".login-tabs .tab, .auth-rail .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.getAttribute("data-tab");
      if (!name) return;
      document.querySelectorAll(".tab-panel").forEach((p) => {
        if (p.classList.contains("active")) {
          p.classList.remove("active");
        }
      });
      // re-trigger animation
      requestAnimationFrame(() => {
        const panel = document.getElementById("tab-" + name) || document.getElementById(name);
        // registerSuccessPanel special
        const target = document.getElementById("tab-" + name);
        if (target) {
          void target.offsetWidth;
          target.classList.add("active");
        }
      });
    });
  });

  
  function showActivatePanel(email) {
    const em = (email || "").trim();
    if (em && $("activateEmail")) $("activateEmail").value = em;
    if (em && $("loginEmail")) $("loginEmail").value = em;
    if (em && $("registerSuccessEmail")) $("registerSuccessEmail").textContent = em;
    if (em && $("registrationEmail")) $("registrationEmail").value = em;
    openLoginTab("activate");
    const first = document.querySelector("#otpRow .otp-digit");
    if (first) setTimeout(() => first.focus(), 50);
  }
  function collectOtpCode() {
    return Array.from(document.querySelectorAll("#otpRow .otp-digit"))
      .map((el) => (el.value || "").replace(/\D/g, ""))
      .join("");
  }
  (function bindOtpDigitsOnce() {
    if (typeof window === "undefined" || typeof document.addEventListener !== "function") return;
    if (window.__otpBound) return;
    window.__otpBound = true;
    const digits = () => Array.from(document.querySelectorAll("#otpRow .otp-digit"));
    document.addEventListener("input", (e) => {
      if (!e.target.classList.contains("otp-digit")) return;
      const list = digits();
      const idx = list.indexOf(e.target);
      e.target.value = (e.target.value || "").replace(/\D/g, "").slice(0, 1);
      if (e.target.value && idx >= 0 && idx < list.length - 1) list[idx + 1].focus();
    });
    document.addEventListener("keydown", (e) => {
      if (!e.target.classList.contains("otp-digit")) return;
      const list = digits();
      const idx = list.indexOf(e.target);
      if (e.key === "Backspace" && !e.target.value && idx > 0) list[idx - 1].focus();
    });
    document.addEventListener("paste", (e) => {
      if (!e.target.classList.contains("otp-digit")) return;
      const nums = ((e.clipboardData || window.clipboardData).getData("text") || "").replace(/\D/g, "").slice(0, 6);
      if (!nums) return;
      e.preventDefault();
      const list = digits();
      nums.split("").forEach((ch, i) => { if (list[i]) list[i].value = ch; });
      list[Math.min(nums.length, 6) - 1]?.focus();
    });
  })();

  if ($("btnActivateOtp")) {
    $("btnActivateOtp").onclick = async () => {
      const log = $("registerSuccessLog");
      const code = collectOtpCode();
      if (code.length !== 6) {
        if (log) { log.classList.add("error"); log.textContent = "Enter all 6 digits"; }
        return;
      }
      try {
        if (log) { log.classList.remove("error"); log.textContent = "Activating…"; }
        const result = await api("/auth/verify-email", {
          method: "POST", skipAuth: true,
          body: JSON.stringify({ token: code }),
        });
        if (log) log.textContent = result.message || "Activated.";
        openLoginTab("login");
        if ($("loginLog")) $("loginLog").textContent = result.message || "Account activated. Sign in.";
      } catch (err) {
        if (log) { log.classList.add("error"); log.textContent = err.message || "Invalid or expired code"; }
      }
    };
  }
  if ($("btnGoLoginAfterRegister")) {
    $("btnGoLoginAfterRegister").onclick = () => openLoginTab("login");
  }
  if ($("btnResendFromNotice")) {
    $("btnResendFromNotice").onclick = async () => {
      const log = $("registerSuccessLog");
      const email = (
        ($("activateEmail") && $("activateEmail").value) ||
        ($("loginEmail") && $("loginEmail").value) ||
        ($("registrationEmail") && $("registrationEmail").value) || ""
      ).trim();
      if (!email) {
        if (log) { log.classList.add("error"); log.textContent = "Enter your email above, then resend."; }
        return;
      }
      try {
        const result = await api("/auth/request-verification", {
          method: "POST", skipAuth: true,
          body: JSON.stringify({ email }),
        });
        if (log) { log.classList.remove("error"); log.textContent = result.message || "Code sent if eligible."; }
        if (result.verification_token && /^\d{6}$/.test(String(result.verification_token))) {
          const list = document.querySelectorAll("#otpRow .otp-digit");
          String(result.verification_token).split("").forEach((ch, i) => { if (list[i]) list[i].value = ch; });
        }
      } catch (err) {
        if (log) { log.classList.add("error"); log.textContent = err.message || "Could not resend"; }
      }
    };
  }

  $("btnLogin").onclick = async () => {
    const log = $("loginLog");
    const btn = $("btnLogin");
    clearSession();
    const version = sessionVersion;
    try {
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Signing in…";
      }
      if (log) {
        log.classList.remove("error");
        log.textContent = "";
      }
      const email = (($("loginEmail") && $("loginEmail").value) || "").trim();
      const password = ($("loginPassword") && $("loginPassword").value) || "";
      if (!email || !password) throw new Error("Email/username/phone and password are required");
      const body = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
        skipAuth: true,
      });
      if (version !== sessionVersion) return;
      try {
        if ($("loginRemember") && $("loginRemember").checked) {
          localStorage.setItem("ws_login_email", email);
        } else {
          localStorage.removeItem("ws_login_email");
        }
      } catch (_) {}
      if (log) log.textContent = "Welcome" + (body.name ? ", " + body.name : "");
      await applyAuthSession(body);
    } catch (err) {
      if (log) {
        log.classList.add("error");
        log.textContent = err.message || "Sign in failed";
        if (/not activated|6-digit|activation/i.test(String(err.message || ""))) {
          showActivatePanel((($("loginEmail") && $("loginEmail").value) || "").trim());
        }
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Sign in";
      }
    }
  };

  // Enter key submits login
  ["loginEmail", "loginPassword"].forEach((id) => {
    const el = $(id);
    if (el) {
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && $("btnLogin")) $("btnLogin").click();
      });
    }
  });


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
  // Job 48 — actionable notifications (title/body + deep link)
  function notificationTarget(n) {
    const p = n.payload || {};
    if (p.approval_id || n.type === "approval_required" || n.type === "approval.pending") {
      return { view: "approvals", label: "Open approvals" };
    }
    if (p.task_id) {
      return { view: "tasks", taskId: p.task_id, label: "Open task" };
    }
    if (n.type && String(n.type).includes("task")) {
      return { view: "tasks", taskId: p.task_id || null, label: "Open tasks" };
    }
    if (n.type && String(n.type).includes("result")) {
      return { view: "results", label: "Open results" };
    }
    return null;
  }

  async function markNotificationRead(id) {
    await api(`/companies/${state.companyId}/notifications/${id}/read`, {
      method: "POST",
      body: "{}",
    });
  }

  async function loadNotifications() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/notifications`);
      const filterEl = $("notifFilter");
      const f = filterEl ? filterEl.value : "all";
      let rows = list || [];
      if (f === "unread") rows = rows.filter((n) => !n.read_at);

      const unread = (list || []).filter((n) => !n.read_at).length;
      $("notifStats").innerHTML = `<div class="stat"><div class="n">${unread}</div><div class="l">Unread</div></div>
        <div class="stat"><div class="n">${rows.length}</div><div class="l">Shown</div></div>`;
      $("notifList").innerHTML =
        rows
          .map((n) => {
            const target = notificationTarget(n);
            const title = n.title || n.type || "Notification";
            const body = n.body || "";
            const when = n.created_at ? new Date(n.created_at).toLocaleString() : "";
            const unreadCls = n.read_at ? "" : " notif-unread";
            return `<div class="item${unreadCls}" data-notif-id="${escapeHtml(n.id)}">
          <strong>${escapeHtml(title)}</strong>
          <div class="meta">${escapeHtml(n.type || "")}${n.read_at ? " · read" : " · unread"}${when ? " · " + escapeHtml(when) : ""}</div>
          ${body ? `<div class="meta">${escapeHtml(body.slice(0, 200))}</div>` : ""}
          <div class="actions">
            ${target ? `<button class="primary btn-notif-open" data-id="${n.id}" data-view="${escapeHtml(target.view)}" data-task="${escapeHtml(target.taskId || "")}">${escapeHtml(target.label)}</button>` : ""}
            ${!n.read_at ? `<button class="secondary btn-read-one" data-id="${n.id}">Mark read</button>` : ""}
          </div>
        </div>`;
          })
          .join("") || `<div class="empty">No notifications.</div>`;

      document.querySelectorAll(".btn-read-one").forEach((b) => {
        b.onclick = async () => {
          try {
            await markNotificationRead(b.dataset.id);
            await loadNotifications();
            await refreshInboxBadge();
          } catch (err) {
            alert(err.message);
          }
        };
      });
      document.querySelectorAll(".btn-notif-open").forEach((b) => {
        b.onclick = async () => {
          try {
            await markNotificationRead(b.dataset.id);
          } catch (_) {}
          const view = b.dataset.view;
          const taskId = b.dataset.task;
          if (taskId) focusedTaskId = taskId;
          if (view === "results") {
            contextualSidebar.results();
          } else if (view) {
            showView(view);
          }
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
  if ($("notifFilter")) $("notifFilter").onchange = loadNotifications;
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


  async function runDemoPlaybook() {
    if (!state.companyId) return;
    const log = $("playbookLog") || $("inventoryLog") || $("homeNotice");
    try {
      if (log && log.id === "homeNotice") {
        log.classList.remove("hidden");
        log.textContent = "Running demo playbook…";
      } else if (log) {
        log.textContent = "Running demo playbook…";
      }
      const res = await api(`/companies/${state.companyId}/demo/playbook-reservation`, {
        method: "POST",
        body: "{}",
      });
      const msg =
        (res.task_id
          ? "Playbook ready. Task: " + res.task_id + " (" + (res.agent_name || "agent") + "). " + (res.next_step || "")
          : "Playbook partial: " + (res.error || JSON.stringify(res)));
      if (log && log.id === "homeNotice") {
        log.textContent = msg;
      } else if (log) {
        log.textContent = JSON.stringify(res, null, 2);
      }
      if (res.task_id) {
        focusedTaskId = res.task_id;
        if ($("taskFilter")) $("taskFilter").selectedIndex = 0;
        showView("tasks");
        loadTasks();
      }
      if (typeof loadInventory === "function") loadInventory();
      refreshInboxBadge();
    } catch (err) {
      if (log) log.textContent = err.message;
      else alert(err.message);
    }
  }
  if ($("btnDemoPlaybook")) $("btnDemoPlaybook").onclick = runDemoPlaybook;
  if ($("btnInvPlaybook")) $("btnInvPlaybook").onclick = runDemoPlaybook;

  function applyInventoryGating() {
    const canManage = hasPermission("agent.manage") || hasPermission("knowledge.write");
    if ($("inventoryActionsCard")) $("inventoryActionsCard").classList.toggle("hidden", !canManage);
  }

  async function loadInventory() {
    if (!state.companyId) return;
    applyInventoryGating();
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
        if (log) {
          log.textContent =
            "Seeded availability.\n" +
            JSON.stringify(res, null, 2) +
            "\nNext: create an execute Task asking the agent to search availability, or use Chat + Also create Task.";
        }
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


  function applyAgentActionGating() {
    const canHire = hasPermission("agent.hire") || hasPermission("agent.manage");
    const canManage = hasPermission("agent.manage");
    if ($("hireCard")) $("hireCard").classList.toggle("hidden", !canHire);
    if ($("agentAccessCard")) $("agentAccessCard").classList.toggle("hidden", !canManage);
  }


  function openAgentSkills(agentId) {
    showView("skills");
    const sel = $("skillAssignAgent");
    if (sel && agentId) {
      sel.value = agentId;
      if (typeof loadAgentAssignedSkills === "function") {
        loadAgentAssignedSkills(agentId);
      }
    }
    if (typeof loadSkills === "function") {
      loadSkills();
    }
  }


  if ($("agentList") && !$("agentList").dataset.manageSkillsWired) {
    $("agentList").dataset.manageSkillsWired = "1";
    $("agentList").addEventListener("click", (ev) => {
      const btn = ev.target && ev.target.closest && ev.target.closest(".btn-manage-skills");
      if (!btn) return;
      const id = btn.getAttribute("data-agent-id");
      if (id) openAgentSkills(id);
    });
  }

  async function loadAgents() {
    if (!state.companyId) return;
    applyAgentActionGating();
    try {
      const [agents, catalog] = await Promise.all([
        api(`/companies/${state.companyId}/agents`),
        api("/agent-catalog"),
      ]);
      $("agentList").innerHTML =
        (agents || [])
          .map(
            (a) => {
            const skillChips = (a.skills || [])
              .slice(0, 8)
              .map((s) => {
                const dom = typeof skillDomain === "function" ? skillDomain(s) : "Other";
                const cls = typeof domainBadgeClass === "function" ? domainBadgeClass(dom) : "";
                return `<span class="tag ${cls}" title="${escapeHtml(dom)}">${escapeHtml(s)}</span>`;
              })
              .join("");
            const manageBtn = hasPermission("agent.manage")
              ? `<button type="button" class="secondary btn-manage-skills" data-agent-id="${escapeHtml(a.id)}" style="margin-top:.5rem">Manage skills</button>`
              : "";
            return `<div class="agent-card" data-agent-id="${escapeHtml(a.id)}">
          <h4><span class="status-dot ${a.status !== "active" ? "inactive" : ""}"></span>${escapeHtml(a.name)}</h4>
          <div class="muted" style="font-size:.8rem">${escapeHtml(a.status)} · autonomy ${escapeHtml(a.autonomy || "")}</div>
          <div style="margin-top:.4rem;display:flex;flex-wrap:wrap;gap:.25rem">${skillChips || `<span class="muted" style="font-size:.8rem">No skills</span>`}</div>
          ${manageBtn}
        </div>`;
          }
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
      const canInstall = hasPermission("agent.hire") || hasPermission("agent.manage");
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
                : canInstall
                  ? `<button class="primary btn-install" data-id="${t.id}">Install</button>`
                  : `<span class="meta">Install requires Owner/AI Admin</span>`
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

  function applyTaskActionGating() {
    const canCreate = hasPermission("task.create");
    if ($("taskCreateCard")) $("taskCreateCard").classList.toggle("hidden", !canCreate);
  }

  async function loadTasks() {
    if (!state.companyId) return;
    applyTaskActionGating();
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
  if ($("btnCreateTask")) $("btnCreateTask").onclick = async () => {
    const log = $("taskCreateLog");
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
      if (log) {
        log.classList.remove("hidden-log");
        log.textContent =
          "Task created: " + (task.title || task.id) +
          "\nMode: " + (task.mode || $("taskMode").value) +
          "\nNext: use Consult or Execute on the task row. If policy requires approval, open Approvals.";
      }
      loadTasks();
      refreshInboxBadge();
    } catch (err) {
      if (log) {
        log.classList.remove("hidden-log");
        log.textContent = err.message;
      } else {
        alert(err.message);
      }
    }
  };

  // ----- Approvals (Job 47: /approve + /reject, not /review) -----
  function approvalPayloadSummary(a) {
    const p = a.payload || {};
    const bits = [];
    if (p.tool || p.tool_name) bits.push("tool: " + (p.tool || p.tool_name));
    if (p.amount != null) bits.push("amount: " + p.amount);
    if (p.currency) bits.push(String(p.currency));
    if (p.guest_name) bits.push("guest: " + p.guest_name);
    if (p.location) bits.push(String(p.location));
    if (!bits.length && p && typeof p === "object") {
      try {
        const s = JSON.stringify(p);
        if (s && s !== "{}") return s.slice(0, 160);
      } catch (_) {}
    }
    return bits.join(" · ");
  }

  async function loadApprovals() {
    if (!state.companyId) return;
    try {
      let list = await api(`/companies/${state.companyId}/approvals`);
      const filterEl = $("approvalFilter");
      const f = filterEl ? filterEl.value : "pending";
      if (f === "pending") list = (list || []).filter((a) => a.status === "pending");
      else if (f === "approved") list = (list || []).filter((a) => a.status === "approved");
      else if (f === "rejected") list = (list || []).filter((a) => a.status === "rejected");

      const pendingCount = (list || []).filter((a) => a.status === "pending").length;
      if ($("approvalStats")) {
        $("approvalStats").innerHTML =
          `<div class="stat"><span class="n">${(list || []).length}</span><span class="l">Shown</span></div>` +
          (f === "all" || f === "pending"
            ? `<div class="stat"><span class="n">${pendingCount}</span><span class="l">Pending in view</span></div>`
            : "");
      }

      $("approvalList").innerHTML =
        (list || [])
          .map((a) => {
            const summary = approvalPayloadSummary(a);
            const canApprove = hasPermission("approval.manage");
            const actions =
              a.status === "pending" && canApprove
                ? `<div class="actions">
            <button class="success btn-approve" data-id="${a.id}">Approve</button>
            <button class="danger btn-reject" data-id="${a.id}">Reject</button>
            ${a.task_id ? `<button class="secondary btn-appr-task" data-task="${a.task_id}">Open task</button>` : ""}
          </div>`
                : a.status === "pending" && !canApprove
                ? `<div class="meta">Waiting for manager/owner approval.</div>`
                : `<div class="actions">
            ${a.task_id ? `<button class="secondary btn-appr-task" data-task="${a.task_id}">Open task</button>` : ""}
            <span class="meta">Reviewed: ${escapeHtml(a.review_comment || a.status)}</span>
          </div>`;
            return `<div class="item" data-approval-id="${escapeHtml(a.id)}">
          <strong>${escapeHtml(a.action || "Action")}</strong>
          <div class="meta">${escapeHtml(a.status)} · ${escapeHtml(a.reason || "")}</div>
          ${summary ? `<div class="meta">${escapeHtml(summary)}</div>` : ""}
          ${a.task_id ? `<div class="meta">Task: <code>${escapeHtml(a.task_id)}</code></div>` : ""}
          ${actions}
        </div>`;
          })
          .join("") || `<div class="empty">No approvals${f && f !== "all" ? " (" + f + ")" : ""}.</div>`;

      document.querySelectorAll(".btn-approve").forEach((b) => {
        b.onclick = async () => {
          b.disabled = true;
          try {
            await api(`/companies/${state.companyId}/approvals/${b.dataset.id}/approve`, {
              method: "POST",
              body: JSON.stringify({ comment: "Approved from workspace" }),
            });
            loadApprovals();
            refreshInboxBadge();
            resultLibrary.refresh();
            loadTasks();
          } catch (err) {
            alert(err.message);
            b.disabled = false;
          }
        };
      });
      document.querySelectorAll(".btn-reject").forEach((b) => {
        b.onclick = async () => {
          const comment = prompt("Rejection reason (optional):", "Rejected from workspace") || "Rejected from workspace";
          b.disabled = true;
          try {
            await api(`/companies/${state.companyId}/approvals/${b.dataset.id}/reject`, {
              method: "POST",
              body: JSON.stringify({ comment }),
            });
            loadApprovals();
            refreshInboxBadge();
            loadTasks();
          } catch (err) {
            alert(err.message);
            b.disabled = false;
          }
        };
      });
      document.querySelectorAll(".btn-appr-task").forEach((b) => {
        b.onclick = () => {
          focusedTaskId = b.dataset.task;
          if ($("taskFilter")) $("taskFilter").selectedIndex = 0;
          showView("tasks");
        };
      });
    } catch (err) {
      $("approvalList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshApprovals")) $("btnRefreshApprovals").onclick = loadApprovals;
  if ($("approvalFilter")) $("approvalFilter").onchange = loadApprovals;

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

  // ----- Knowledge (Job 52: list, filter, extract badge) -----
  function isExtractedKnowledge(item) {
    const c = String(item.content || "");
    const cat = String(item.category || "").toLowerCase();
    return (
      cat === "document" ||
      /not retained/i.test(c) ||
      /Extracted from /i.test(c) ||
      /file not retained/i.test(c)
    );
  }

  function applyKnowledgeWriteGating() {
    const canWrite = hasPermission("knowledge.write");
    if ($("knowledgeWriteCard")) $("knowledgeWriteCard").classList.toggle("hidden", !canWrite);
    if ($("knowledgeNoteCard")) $("knowledgeNoteCard").classList.toggle("hidden", !canWrite);
  }

  async function loadKnowledge() {
    if (!state.companyId) return;
    applyKnowledgeWriteGating();
    const listEl = $("knowList");
    if (!listEl) return;
    try {
      const all = await api(`/companies/${state.companyId}/knowledge`);
      let items = all || [];
      const f = ($("knowFilter") && $("knowFilter").value) || "all";
      if (f === "extract") items = items.filter(isExtractedKnowledge);
      else if (f === "manual") items = items.filter((i) => !isExtractedKnowledge(i));
      else if (f === "document") {
        items = items.filter((i) => String(i.category || "").toLowerCase() === "document");
      }
      const extractCount = (all || []).filter(isExtractedKnowledge).length;
      if ($("knowStats")) {
        $("knowStats").innerHTML =
          `<div class="stat"><span class="n">${(items || []).length}</span><span class="l">Shown</span></div>` +
          `<div class="stat"><span class="n">${extractCount}</span><span class="l">Extracts</span></div>`;
      }
      listEl.innerHTML =
        (items || [])
          .map((k) => {
            const extracted = isExtractedKnowledge(k);
            const badge = extracted
              ? `<span class="tag-extract">from extract</span>`
              : `<span class="tag-manual">manual</span>`;
            const preview = escapeHtml(String(k.content || "").slice(0, 180));
            return `<div class="item" data-know-id="${escapeHtml(k.id)}">
          <strong>${escapeHtml(k.title || k.id)}</strong>${badge}
          <div class="meta">${escapeHtml(k.category || "general")} · ${k.is_active === false ? "inactive" : "active"}</div>
          <div class="meta">${preview}</div>
        </div>`;
          })
          .join("") || `<div class="empty">No knowledge items. Extract a document or add a note.</div>`;
    } catch (err) {
      listEl.innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  if ($("btnRefreshKnowledge")) $("btnRefreshKnowledge").onclick = loadKnowledge;
  if ($("knowFilter")) $("knowFilter").onchange = loadKnowledge;

  if ($("btnAddKnowledge"))
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
        await loadKnowledge();
      } catch (err) {
        alert(err.message);
      }
    };

  if ($("btnSearchKnow"))
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

  if ($("btnKnowledgeIngest"))
    $("btnKnowledgeIngest").onclick = async () => {
      const log = $("knowledgeIngestLog");
      const btn = $("btnKnowledgeIngest");
      const fileInput = $("knowledgeIngestFile");
      if (!fileInput || !fileInput.files || !fileInput.files[0]) {
        if (log) log.textContent = "Choose a file first";
        return;
      }
      if (!hasPermission("knowledge.write")) {
        if (log) log.textContent = "You do not have knowledge.write permission.";
        return;
      }
      try {
        if (btn) { btn.disabled = true; btn.textContent = "Extracting…"; }
        if (log) log.textContent = "Uploading and extracting (file will not be stored)…";
        const fd = new FormData();
        fd.append("file", fileInput.files[0]);
        const title = ($("knowledgeIngestTitle") && $("knowledgeIngestTitle").value.trim()) || "";
        if (title) fd.append("title", title);
        const cat = ($("knowledgeIngestCategory") && $("knowledgeIngestCategory").value) || "document";
        fd.append("category", cat);
        const base = (state.apiBase || "/api/v1").replace(/\/$/, "");
        const version = sessionVersion;
        const token = state.accessToken;
        const res = await fetch(base + `/companies/${state.companyId}/knowledge/ingest-extract`, {
          method: "POST",
          headers: token ? { Authorization: "Bearer " + token } : {},
          body: fd,
        });
        const text = await res.text();
        let data;
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }
        if (!res.ok) {
          if (res.status === 401) expireCurrentSession(version, token);
          throw new Error(typeof data === "object" ? data.detail || JSON.stringify(data) : text);
        }
        if (log) {
          log.textContent =
            "Saved as knowledge (file discarded): " + (data.title || data.id) +
            "\nCategory: " + (data.category || cat) +
            "\nAI Employees can use this in chat/tasks within policy.";
        }
        if ($("knowFilter")) $("knowFilter").value = "extract";
        if (fileInput) fileInput.value = "";
        if ($("knowledgeIngestTitle")) $("knowledgeIngestTitle").value = "";
        await loadKnowledge();
      } catch (err) {
        if (log) log.textContent = err.message;
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Extract to knowledge"; }
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
    if ($("policyCreateCard")) {
      $("policyCreateCard").classList.toggle(
        "hidden",
        !(hasPermission("policy.manage") || hasPermission("agent.manage"))
      );
    }
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
        log.textContent =
          "Policy created. Unmatched tools remain denied by default. Run a Task execute or Policy Simulator to verify.";
        loadPolicies();
      } catch (err) {
        log.textContent = err.message;
      }
    };

  // ----- Departments -----
  
  async function loadUsers() {
    if (!state.companyId) return;
    const roleOptions = [
      ["member", "Member"],
      ["reservation", "Reservation"],
      ["manager", "Manager"],
      ["contract_manager", "Contract Manager"],
      ["administration", "Administration"],
      ["accounting", "Accounting"],
    ];
    if (state.role === "owner") {
      roleOptions.splice(3, 0, ["ai_admin", "AI Administrator"]);
    }
    try {
      // refresh job-role select from API when available
      try {
        const rolesBody = await api(`/companies/${state.companyId}/job-roles`);
        const sel = $("userRoleInput");
        if (sel && rolesBody.roles && rolesBody.roles.length) {
          const current = sel.value;
          const roles = rolesBody.roles.filter(
            (r) => state.role === "owner" || r.name !== "ai_admin"
          );
          sel.innerHTML = roles
            .map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.label || r.name)}</option>`)
            .join("");
          if ([...sel.options].some((o) => o.value === current)) sel.value = current;
        }
      } catch (_) {}

      const list = await api(`/companies/${state.companyId}/users`);
      $("usersList").innerHTML =
        (list || [])
          .map((u) => {
            const isOwner = u.role === "owner";
            const roleSelect =
              hasPermission("team.manage") && !isOwner
                ? `<label class="inline-role">Position
                    <select class="user-role-select" data-id="${escapeHtml(u.id)}">
                      ${roleOptions
                        .map(
                          ([v, lab]) =>
                            `<option value="${v}" ${u.role === v ? "selected" : ""}>${lab}</option>`
                        )
                        .join("")}
                    </select>
                  </label>
                  <button class="secondary btn-save-role" data-id="${escapeHtml(u.id)}">Save position</button>`
                : "";
            const adminBtn =
              state.role === "owner" && !isOwner
                ? `<button class="secondary btn-set-role" data-id="${escapeHtml(u.id)}" data-admin="${
                    u.role === "ai_admin" ? "1" : "0"
                  }">${u.role === "ai_admin" ? "Remove AI admin" : "Make AI administrator"}</button>`
                : "";
            return `<div class="item">
          <strong>${escapeHtml(u.name)}</strong>
          <div class="meta">${escapeHtml(u.email)} · role: <code>${escapeHtml(u.role || u.role_id)}</code> · ${escapeHtml(u.status || "")}</div>
          <div class="row" style="margin-top:.35rem;gap:.5rem;flex-wrap:wrap">${roleSelect}${adminBtn}</div>
        </div>`;
          })
          .join("") || `<div class="empty">No employees yet. Send an invitation above.</div>`;

      document.querySelectorAll(".btn-set-role").forEach((b) => {
        b.onclick = async () => {
          try {
            await api(`/companies/${state.companyId}/administrators/${b.dataset.id}`, {
              method: "PUT",
              body: JSON.stringify({ administrator: b.dataset.admin !== "1" }),
            });
            loadUsers();
          } catch (err) {
            alert(err.message);
          }
        };
      });
      document.querySelectorAll(".btn-save-role").forEach((b) => {
        b.onclick = async () => {
          const select = document.querySelector(`.user-role-select[data-id="${b.dataset.id}"]`);
          if (!select) return;
          try {
            await api(`/companies/${state.companyId}/users/${b.dataset.id}/role`, {
              method: "PUT",
              body: JSON.stringify({ role_name: select.value }),
            });
            if ($("userAdminLog")) {
              $("userAdminLog").classList.remove("hidden-log");
              $("userAdminLog").textContent = "Job position updated. Employee must sign in again.";
            }
            loadUsers();
          } catch (err) {
            if ($("userAdminLog")) {
              $("userAdminLog").classList.remove("hidden-log");
              $("userAdminLog").textContent = err.message;
            }
          }
        };
      });
      if (hasPermission("team.manage") && $("invitationsList")) {
        const invitations = await api(`/companies/${state.companyId}/invitations`);
        $("invitationsList").innerHTML =
          invitations
            .map(
              (invitation) =>
                `<div class="item"><strong>${escapeHtml(invitation.email)}</strong>
           <span class="meta">${escapeHtml(invitation.status)} · position: <code>${escapeHtml(
                  invitation.role_name || "member"
                )}</code></span>
           ${
             invitation.status === "pending"
               ? `<button class="secondary btn-revoke-invite" data-id="${escapeHtml(
                   invitation.id
                 )}">Revoke</button>`
               : ""
           }</div>`
            )
            .join("") || `<div class="empty">No invitations.</div>`;
        document.querySelectorAll(".btn-revoke-invite").forEach((button) => {
          button.onclick = async () => {
            try {
              await api(`/companies/${state.companyId}/invitations/${button.dataset.id}/revoke`, {
                method: "POST",
              });
              loadUsers();
            } catch (err) {
              $("userAdminLog").textContent = err.message;
            }
          };
        });
      }
    } catch (err) {
      $("usersList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;
  if ($("btnCreateUser"))
    $("btnCreateUser").onclick = async () => {
      const log = $("userAdminLog");
      try {
        const body = await api(`/companies/${state.companyId}/invitations`, {
          method: "POST",
          body: JSON.stringify({
            email: ($("userEmailInput").value || "").trim(),
            role_name: ($("userRoleInput") && $("userRoleInput").value) || "member",
          }),
        });
        if (log) {
          log.classList.remove("hidden-log");
          const role = body.role_name || ($("userRoleInput") && $("userRoleInput").value) || "member";
          log.textContent =
            (body.message || "Invitation created.") +
            " Position: " + role +
            (body.invitation_token
              ? "\nDev token (Accept invitation tab): " + body.invitation_token
              : "\nEmployee will receive an email when SMTP is configured.");
        }
        if ($("inviteDebugTokenWrap")) $("inviteDebugTokenWrap").classList.toggle("hidden", !body.invitation_token);
        if ($("inviteDebugToken")) $("inviteDebugToken").value = body.invitation_token || "";
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

  // ----- Job 78: Skills domain map + filter + assign -----
  const SKILL_DOMAIN_MAP = {
    availability_check: "Reservation",
    reservation_management: "Reservation",
    booking_support: "Reservation",
    quotation_preparation: "Reservation",
    customer_follow_up: "Sales / CS",
    invoice_draft_preparation: "Accounting",
    expense_anomaly_detection: "Accounting",
    lead_qualification: "Sales / CS",
    faq_response: "Sales / CS",
    contract_analysis: "Contract",
    contract_extraction: "Contract",
    contract_validation: "Contract",
    hotel_upsell_package: "Custom",
  };

  function dedupeSkillsPreferCompany(list) {
    // One card per slug: company-scoped overrides platform (company_id null).
    const bySlug = new Map();
    for (const s of list || []) {
      const slug = s.slug || s.id;
      const prev = bySlug.get(slug);
      if (!prev) {
        bySlug.set(slug, s);
        continue;
      }
      const prevIsCompany = !!prev.company_id;
      const curIsCompany = !!s.company_id;
      if (curIsCompany && !prevIsCompany) {
        bySlug.set(slug, s);
      }
    }
    return Array.from(bySlug.values()).sort((a, b) =>
      String(a.slug || "").localeCompare(String(b.slug || ""))
    );
  }

  function skillDomain(slug) {
    return SKILL_DOMAIN_MAP[slug] || "Other";
  }
  function domainBadgeClass(domain) {
    const m = {
      Reservation: "badge-blue",
      Accounting: "badge-amber",
      "Sales / CS": "badge-green",
      Contract: "badge-purple",
      Custom: "badge-slate",
      Other: "badge-slate",
    };
    return m[domain] || "badge-slate";
  }
  let _skillsCache = [];
  let _skillsDomainFilter = "all";
  let _skillsScope = "deduped";


  function renderSkillsList(list) {
    const deduped = dedupeSkillsPreferCompany(list);
    const filtered =
      _skillsDomainFilter === "all"
        ? deduped
        : (deduped || []).filter((s) => skillDomain(s.slug) === _skillsDomainFilter);
    $("skillsList").innerHTML =
      (filtered || [])
        .map((s) => {
          const dom = skillDomain(s.slug);
          const tools = (s.allowed_tools || []).slice(0, 6)
            .map((t) => `<span class="tag">${escapeHtml(t)}</span>`)
            .join("");
          const know = (s.required_knowledge || []).slice(0, 4)
            .map((k) => `<span class="tag">${escapeHtml(k)}</span>`)
            .join("");
          return `<div class="agent-card" data-skill-id="${escapeHtml(s.id)}" data-skill-slug="${escapeHtml(s.slug)}">
          <div class="row" style="justify-content:space-between;gap:.5rem;flex-wrap:wrap">
            <h4 style="margin:0">${escapeHtml(s.name)}</h4>
            <span class="tag ${domainBadgeClass(dom)}">${escapeHtml(dom)}</span>
          </div>
          <div class="muted" style="font-size:.8rem">${escapeHtml(s.slug)} · ${s.company_id ? "company" : "platform"} · v${escapeHtml(s.version || "")}</div>
          <p style="font-size:.85rem;color:var(--muted)">${escapeHtml((s.description || "").slice(0, 140))}</p>
          ${tools ? `<div style="margin-top:.35rem"><span class="muted" style="font-size:.75rem">Tools:</span> ${tools}</div>` : ""}
          ${know ? `<div style="margin-top:.25rem"><span class="muted" style="font-size:.75rem">Knowledge:</span> ${know}</div>` : ""}
        </div>`;
        })
        .join("") || `<div class="empty">No skills${_skillsDomainFilter !== "all" ? " in this domain" : ""}.</div>`;
  }


  function fillSkillAssignSelects(list) {
    const sel = $("skillAssignSkill");
    if (!sel) return;
    const cur = sel.value;
    const opts = dedupeSkillsPreferCompany(list || []);
    sel.innerHTML =
      `<option value="">— select skill —</option>` +
      (opts || [])
        .map(
          (s) =>
            `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)} (${escapeHtml(skillDomain(s.slug))})</option>`
        )
        .join("");
    if (cur) sel.value = cur;
  }

  async function fillSkillAssignAgents() {
    const sel = $("skillAssignAgent");
    if (!sel || !state.companyId) return;
    try {
      const agents = await api(`/companies/${state.companyId}/agents`);
      const cur = sel.value;
      sel.innerHTML =
        `<option value="">— select agent —</option>` +
        (agents || [])
          .map(
            (a) =>
              `<option value="${escapeHtml(a.id)}">${escapeHtml(a.name || a.id)}</option>`
          )
          .join("");
      if (cur) sel.value = cur;
    } catch (err) {
      /* ignore */
    }
  }



  async function loadAgentAssignedSkills(agentId) {
    const box = $("skillAssignedList");
    if (!box) return;
    if (!agentId || !state.companyId) {
      box.innerHTML = `<div class="muted" style="font-size:.85rem">Select an agent to see assigned skills.</div>`;
      return;
    }
    try {
      const rows = await api(`/companies/${state.companyId}/agents/${agentId}/skills`);
      if (!rows || !rows.length) {
        box.innerHTML = `<div class="empty">No skills assigned to this agent.</div>`;
        return;
      }
      const byId = {};
      (_skillsCache || []).forEach((s) => {
        byId[s.id] = s;
      });
      box.innerHTML = rows
        .map((row) => {
          const sk = byId[row.skill_id] || {};
          const name = sk.name || row.skill_id;
          const slug = sk.slug || "";
          const dom = slug ? skillDomain(slug) : "Other";
          const canManage = hasPermission("agent.manage");
          const btn = canManage
            ? `<button type="button" class="secondary btn-unassign-skill" data-assignment-id="${escapeHtml(row.id)}" data-agent-id="${escapeHtml(agentId)}" style="margin-top:.35rem">Unassign</button>`
            : "";
          return `<div class="agent-card" data-assignment-id="${escapeHtml(row.id)}">
            <div class="row" style="justify-content:space-between;gap:.5rem;flex-wrap:wrap">
              <strong>${escapeHtml(name)}</strong>
              <span class="tag ${domainBadgeClass(dom)}">${escapeHtml(dom)}</span>
            </div>
            <div class="muted" style="font-size:.8rem">${escapeHtml(slug || row.skill_id)}</div>
            ${btn}
          </div>`;
        })
        .join("");
      box.querySelectorAll(".btn-unassign-skill").forEach((btn) => {
        btn.onclick = async () => {
          const assignmentId = btn.getAttribute("data-assignment-id");
          const ag = btn.getAttribute("data-agent-id");
          const log = $("skillAssignLog");
          try {
            await api(
              `/companies/${state.companyId}/agents/${ag}/skills/${assignmentId}`,
              { method: "DELETE" }
            );
            if (log) log.textContent = "Skill unassigned.";
            await loadAgentAssignedSkills(ag);
          } catch (err) {
            if (log) log.textContent = err.message;
          }
        };
      });
    } catch (err) {
      box.innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadSkills() {
    if (!state.companyId) return;
    if ($("skillCreateCard")) {
      $("skillCreateCard").classList.toggle("hidden", !hasPermission("agent.manage"));
    }
    if ($("skillAssignCard")) {
      $("skillAssignCard").classList.toggle("hidden", !hasPermission("agent.manage"));
    }
    try {
      const list = await api(`/companies/${state.companyId}/skills?scope=${encodeURIComponent(_skillsScope || "deduped")}`);
      _skillsCache = list || [];
      renderSkillsList(_skillsCache);
      fillSkillAssignSelects(_skillsCache);
      await fillSkillAssignAgents();
    } catch (err) {
      $("skillsList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  if ($("btnRefreshSkills")) $("btnRefreshSkills").onclick = loadSkills;
  
  document.querySelectorAll(".skill-scope-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".skill-scope-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      _skillsScope = btn.getAttribute("data-scope") || "deduped";
      loadSkills();
    });
  });

  document.querySelectorAll(".skill-domain-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".skill-domain-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      _skillsDomainFilter = btn.getAttribute("data-domain") || "all";
      renderSkillsList(_skillsCache);
    });
  });

  if ($("skillAssignAgent")) {
    $("skillAssignAgent").addEventListener("change", () => {
      const ag = $("skillAssignAgent").value;
      loadAgentAssignedSkills(ag);
    });
  }

  if ($("btnAssignSkill"))
    $("btnAssignSkill").onclick = async () => {
      const log = $("skillAssignLog");
      const agentId = $("skillAssignAgent") && $("skillAssignAgent").value;
      const skillId = $("skillAssignSkill") && $("skillAssignSkill").value;
      if (!agentId || !skillId) {
        if (log) log.textContent = "Select agent and skill.";
        return;
      }
      try {
        await api(`/companies/${state.companyId}/agents/${agentId}/skills`, {
          method: "POST",
          body: JSON.stringify({ skill_id: skillId }),
        });
        if (log) log.textContent = "Skill assigned.";
        await loadAgentAssignedSkills(agentId);
      } catch (err) {
        if (log) log.textContent = err.message;
      }
    };

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


  
  // ----- Job 57: platform provision (developer workspace) -----
  if ($("btnProvisionCompany")) {
    $("btnProvisionCompany").onclick = async () => {
      const log = $("provLog");
      try {
        if (!state.userId && !state.accessToken) {
          throw new Error("Connect as platform admin first (Login or Connect IDs).");
        }
        const res = await api(`/admin/companies`, {
          method: "POST",
          body: JSON.stringify({
            name: ($("provCompanyName") && $("provCompanyName").value.trim()) || "",
            owner_name: ($("provOwnerName") && $("provOwnerName").value.trim()) || "Owner",
            owner_email: ($("provOwnerEmail") && $("provOwnerEmail").value.trim()) || "",
            owner_password: ($("provOwnerPassword") && $("provOwnerPassword").value) || "demo12345",
          }),
        });
        if (log) {
          log.textContent =
            "Provisioned company " + res.company.id + "\nOwner: " + res.owner.email +
            "\nGive Company ID + credentials to the owner for /workspace login.";
        }
        if (typeof loadAdminCompanies === "function") loadAdminCompanies();
      } catch (err) {
        if (log) log.textContent = err.message;
      }
    };
  }

  async function loadAdminCompanies() {
    const list = $("adminCompanyList");
    if (!list) return;
    try {
      const rows = await api(`/admin/companies`);
      list.innerHTML =
        (rows || [])
          .map(
            (c) => `<div class="item">
          <strong>${escapeHtml(c.name)}</strong>
          <div class="meta">${escapeHtml(c.id)} · users ${c.user_count} · ${c.is_active ? "active" : "disabled"}</div>
          <div class="actions">
            <button class="secondary btn-admin-users" data-id="${c.id}">Users</button>
            <button class="secondary btn-admin-agents" data-id="${c.id}">AI employees</button>
            <button class="secondary btn-admin-toggle" data-id="${c.id}" data-active="${c.is_active ? "1" : "0"}">${c.is_active ? "Disable" : "Enable"}</button>
          </div>
        </div>`
          )
          .join("") || `<div class="empty">No companies.</div>`;
      document.querySelectorAll(".btn-admin-users").forEach((b) => {
        b.onclick = async () => {
          const detail = $("adminCompanyDetail");
          try {
            const data = await api(`/admin/companies/${b.dataset.id}/users`);
            detail.innerHTML =
              `<h4>${escapeHtml(data.company_name)} — human users</h4>` +
              (data.users || [])
                .map(
                  (u) =>
                    `<div class="item"><strong>${escapeHtml(u.name)}</strong>
                    <div class="meta">${escapeHtml(u.email)} · ${escapeHtml(u.role || "")} · ${escapeHtml(u.status || "")}</div></div>`
                )
                .join("") || `<div class="empty">No users</div>`;
          } catch (err) {
            detail.innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
          }
        };
      });
      document.querySelectorAll(".btn-admin-agents").forEach((b) => {
        b.onclick = async () => {
          const detail = $("adminCompanyDetail");
          try {
            const data = await api(`/admin/companies/${b.dataset.id}/agents`);
            detail.innerHTML =
              `<h4>AI employees</h4>` +
              (data.agents || [])
                .map(
                  (a) =>
                    `<div class="item"><strong>${escapeHtml(a.name)}</strong>
                    <div class="meta">${escapeHtml(a.status)} · ${escapeHtml(a.id)}</div></div>`
                )
                .join("") || `<div class="empty">No agents</div>`;
          } catch (err) {
            detail.innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
          }
        };
      });
      document.querySelectorAll(".btn-admin-toggle").forEach((b) => {
        b.onclick = async () => {
          const active = b.dataset.active === "1";
          const path = active ? "disable" : "enable";
          await api(`/admin/companies/${b.dataset.id}/${path}`, { method: "POST", body: "{}" });
          await loadAdminCompanies();
        };
      });
    } catch (err) {
      list.innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnAdminRefreshCompanies")) $("btnAdminRefreshCompanies").onclick = loadAdminCompanies;


  // ----- Boot -----
  if ($("apiBase")) $("apiBase").value = state.apiBase;
  if ($("companyId")) $("companyId").value = state.companyId;
  if ($("userId")) $("userId").value = state.userId;

  (async function bootSession() {
    const version = sessionVersion;
    setConnected(false);
    applyNavGating();
    if (state.accessToken) {
      if (!await loadMeProfile()) return;
      const profileLoaded = await loadCompanyProfile();
      if (!profileLoaded) {
        if (state.accessToken) {
          setConnected(true);
          showOnboardingRecovery("We could not load the company profile. Your workspace is still available; open Company profile to retry.");
        }
        return;
      }
      applyNavGating();
      setConnected(true);
      if (await routePostLoginOnboarding()) return;
      if (version !== sessionVersion) return;
      await bootstrapSessionEnvironment();
      if (version !== sessionVersion) return;
      await refreshInboxBadge();
      if (version !== sessionVersion) return;
      showView(defaultLandingView());
    } else {
      clearSession();
    }
  })();
})();
