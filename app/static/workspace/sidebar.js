(function (root) {
  const configs = {
    home: { title: "Workspace updates", resources: ["notifications", "workflows"], links: [["Read notifications", "notifications"], ["View workflows", "workflows"]] },
    inbox: { title: "Inbox guide", resources: ["policies", "knowledge"], links: [["Company policies", "policy-management"]], guide: {
      summary: "A shared queue for work that needs your attention.",
      steps: ["Review approvals before restricted actions proceed.", "Start ready consultations, inspect failed tasks, or review handoffs.", "Use In progress to monitor work already underway."],
    } },
    tasks: { title: "Task references", resources: ["knowledge", "policies"], links: [["Company knowledge", "knowledge"]] },
    approvals: { title: "Review references", resources: ["policies", "knowledge"], links: [["Company policies", "policy-management"]] },
    chat: { title: "Conversation context", resources: ["agents", "tasks"], links: [["Company knowledge", "knowledge"], ["AI employees", "agents"]] },
    consult: { title: "Consultation context", resources: ["agents", "tasks"], links: [["Company knowledge", "knowledge"]] },
    agents: { title: "Organization context", resources: ["departments", "teams"], links: [["View teams", "teams"]] },
    directory: { title: "Organization context", resources: ["departments", "teams"], links: [["View teams", "teams"]] },
    marketplace: { title: "Hiring capacity", resources: ["usage"], links: [["Plan & usage", "usage"]] },
    knowledge: { title: "Related capabilities", resources: ["skills"], links: [["Consult an AI", "consult"]] },
    delegation: { title: "Handoff policies", resources: ["policies"], links: [["Company policies", "policy-management"]] },
    automation: { title: "Related workflows", resources: ["workflows"], links: [["View workflows", "workflows"]] },
    notifications: { title: "Automation context", resources: ["automations"], links: [["View automations", "automation"]] },
    governance: { title: "Policy references", resources: ["policies"], links: [["Company policies", "policy-management"]] },
    "policy-management": { title: "Tool risk references", resources: ["/tools"], links: [] },
    departments: { title: "Related teams", resources: ["teams"], links: [["View teams", "teams"]] },
    teams: { title: "Department context", resources: ["departments"], links: [["View departments", "departments"]] },
    skills: { title: "Knowledge references", resources: ["knowledge"], links: [["Company knowledge", "knowledge"]] },
    learning: { title: "Knowledge references", resources: ["knowledge"], links: [["Company knowledge", "knowledge"]] },
    usage: { title: "Cost context", resources: ["governance/cost"], links: [["LLM cost", "cost"]] },
    audit: { title: "Policy references", resources: ["policies"], links: [["Company policies", "policy-management"]] },
    tools: { title: "Connected services", resources: ["integrations"], links: [["Integrations", "integrations"]] },
    integrations: { title: "Related workflows", resources: ["workflows"], links: [["View workflows", "workflows"]] },
    workflows: { title: "Related automations", resources: ["automations"], links: [["View automations", "automation"]] },
    cost: { title: "Plan context", resources: ["usage"], links: [["Plan & usage", "usage"]] },
    policies: { title: "Policy context", resources: ["agents", "policies"], links: [["View tools", "tools"]] },
    scopecheck: { title: "Agent scope", resources: ["agents"], links: [["View tools", "tools"]] },
    "result-preview": { title: "Selected result", resources: ["tasks"], links: [["View tasks", "tasks"]] },
  };
  const guides = {
    home: ["Home", "An overview of workspace priorities and recent work.", "Review items that need attention.", "Open a task or conversation to continue work."],
    tasks: ["Tasks", "Assigned AI work, progress, and saved outcomes.", "Create a task with an AI employee and a clear instruction.", "Review status and results; execution remains subject to policy."],
    approvals: ["Approvals", "Human decisions for actions that require authorization.", "Check the reason and requested action.", "Approve or reject with an appropriate review comment."],
    chat: ["Chat", "Advisory conversations with AI employees.", "Choose an AI employee and reopen a conversation or start a new one.", "Create a task when work needs execution; chat does not run tools."],
    consult: ["Consult", "Structured advice without executing tool actions.", "Choose an AI employee and describe the question.", "Review the recommendation before planning execution."],
    agents: ["AI Employees", "Hired AI employees and their configuration.", "Review employee scope, skills, and status.", "Adjust configuration and access within your permissions."],
    directory: ["Directory", "AI employee roles and organizational assignments.", "Find the employee responsible for a capability.", "Review organization and supervision before assigning work."],
    marketplace: ["Marketplace", "Available AI employee templates for hiring.", "Compare role and capability requirements.", "Check plan capacity before hiring."],
    knowledge: ["Knowledge", "Company reference material available to AI employees.", "Add relevant documents and reference notes.", "Keep source material accurate and current."],
    delegation: ["Delegation", "Work handed from one AI employee to another.", "Choose source, target, and the requested capability.", "Review handoff status and its linked task."],
    automation: ["Automation", "Configured rules for recurring AI work.", "Define a rule and its intended task.", "Review run history and failures before enabling recurring work."],
    notifications: ["Notifications", "Workspace events that may need your attention.", "Review updates and open the related work.", "Mark reviewed notifications as read."],
    governance: ["Governance", "Oversight of AI activity and operational outcomes.", "Review activity and risk indicators.", "Investigate notable events through policies and audit records."],
    "policy-management": ["Policies", "Company rules that govern AI tool actions.", "Review active rules and approval requirements.", "Change policies only within your authorization."],
    departments: ["Departments", "Department ownership within the company.", "Review department records and organizational assignments.", "Keep ownership aligned with the company structure."],
    teams: ["Teams", "Groups of AI employees organized for shared work.", "Review team membership and department alignment.", "Manage membership within your permissions."],
    skills: ["Skills", "Capabilities available to AI employees.", "Review capability definitions and requirements.", "Match skills to the work being assigned."],
    learning: ["Learning", "Recorded lessons and proposed improvements.", "Review learning records against their source work.", "Evaluate suggestions before changing configuration or policy."],
    usage: ["Plan & Usage", "Subscription allowances and current consumption.", "Compare usage with plan limits.", "Check remaining capacity before adding work or employees."],
    audit: ["Audit Log", "Recorded actions, actors, timestamps, and outcomes.", "Find the event related to the work under review.", "Use recorded evidence to trace decisions and failures."],
    tools: ["Tools", "Developer references for registered tool capabilities.", "Inspect available tools and their risk levels.", "Check required permissions before integrating a tool."],
    integrations: ["Integrations", "External service connections used by the workspace.", "Review connection status and configuration.", "Protect credentials and validate connections before use."],
    workflows: ["Workflows", "Reusable sequences for coordinated AI work.", "Review workflow steps and assigned employees.", "Inspect run outcomes before repeating a workflow."],
    cost: ["LLM Cost", "Estimated model spending and configured budgets.", "Review cost trends and remaining budget.", "Use estimates for planning, not as a billing statement."],
    policies: ["Policy Simulator", "Developer checks for policy decisions on proposed actions.", "Choose an employee, tool, and proposed arguments.", "Inspect the decision before running a real task."],
    scopecheck: ["Scope Check", "Developer checks for whether instructions match an employee's scope.", "Select an employee and enter the proposed instruction.", "Review scope findings before assigning work."],
    "result-preview": ["Result Preview", "A saved outcome from an AI task.", "Review the result alongside its original instruction.", "Download the output or revise the work when needed."],
  };
  for (const [view, [page, summary, ...steps]] of Object.entries(guides)) configs[view].guide = { page, summary, steps };
  configs.inbox.guide.page = "Inbox";

  function guideText(view) {
    const guide = configs[view]?.guide;
    if (!guide) return "";
    return `${guide.page}\n\nPurpose\n${guide.summary}\n\nTypical use\n${guide.steps.map((step, index) => `${index + 1}. ${step}`).join("\n")}\n`;
  }
  const newest = (records) => [...records].sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0));
  const normalizeTitle = (value) => String(value || "").trim().replace(/\s+/g, " ").toLowerCase();

  function excludeMainRecords(model, mainTitles, mainText = "") {
    const visible = new Set(mainTitles.map(normalizeTitle));
    const content = normalizeTitle(mainText);
    return { ...model, sections: model.sections.map((section) => ({
      ...section, entries: section.entries.filter((entry) => !visible.has(normalizeTitle(entry.title)) &&
        !(normalizeTitle(entry.detail).length > 20 && content.includes(normalizeTitle(entry.detail)))),
    })) };
  }

  function buildContext(view, data, agentId = "", selectedTaskId = "") {
    const config = configs[view] || { title: "Page context", resources: [], links: [] };
    const sections = [], metrics = [];
    const list = (key) => Array.isArray(data[key]) ? data[key] : [];
    const records = (items) => newest(items).slice(0, 5).map((item) => ({
      title: item.title || item.name || item.action || item.type || item.category || "Record",
      detail: [item.description || item.reason || item.lesson || "",
        item.risk != null ? `Risk: ${item.risk}` : "",
        Array.isArray(item.steps) ? `${item.steps.length} steps` : "",
        Array.isArray(item.member_agent_ids) ? `${item.member_agent_ids.length} members` : "",
      ].filter(Boolean).join(" / ").slice(0, 180),
    }));
    if (["chat", "consult", "scopecheck", "policies"].includes(view)) {
      const agent = list("agents").find((item) => item.id === agentId);
      if (agent) {
        if (view === "chat") {
          const brief = [
            ["Role", agent.configuration?.role, 80],
            ["Working instructions", agent.instructions, 180],
          ].filter(([, value]) => typeof value === "string" && value.trim()).map(([title, value, limit]) => ({
            title, detail: value.trim().replace(/\s+/g, " ").slice(0, limit),
          }));
          if (brief.length) sections.push({ title: "Employee brief", entries: brief, empty: "" });
        }
        sections.push({ title: "Skills", compact: view === "chat", entries: (agent.skills || []).slice(0, view === "chat" ? 50 : 5).map((skill) => ({ title: typeof skill === "string" ? skill : skill.name || skill.slug || "Skill", detail: "" })), empty: "No skills assigned." });
        sections.push({ title: "Scope", compact: view === "chat", entries: (agent.scope || []).slice(0, view === "chat" ? 50 : 5).map((scope) => ({ title: typeof scope === "string" ? scope : JSON.stringify(scope), detail: "" })), empty: "No scope entries configured." });
      }
      if (["chat", "consult"].includes(view)) {
        const tasks = list("tasks").filter((task) => task.agent_instance_id === agentId && task.result && (view !== "consult" || task.mode === "consult"));
        sections.push({ title: "Earlier outputs", entries: newest(tasks).slice(0, 3).map((task) => ({
          title: task.title, detail: "", task, kind: "result",
        })), empty: "No earlier outputs available." });
      }
      if (view === "policies") sections.push({ title: "Company rules", entries: records(list("policies")), empty: "No company rules available." });
    } else if (view === "result-preview") {
      const task = list("tasks").find((item) => item.id === selectedTaskId);
      if (task) sections.push({ title: "Original instruction", entries: [{ title: "Task brief", detail: task.instruction }], empty: "" });
    } else if (["marketplace", "cost", "usage"].includes(view)) {
      const key = config.resources[0], record = data[key];
      if (record) {
        const fields = key === "usage" ? [
          ["Plan", record.plan?.name || record.plan?.code],
          ["Agent slots remaining", record.plan?.max_agents != null && record.usage?.agents != null ? Math.max(0, record.plan.max_agents - record.usage.agents) : null],
          ["Task allowance remaining today", record.plan?.max_tasks_day != null && record.usage?.tasks_today != null ? Math.max(0, record.plan.max_tasks_day - record.usage.tasks_today) : null],
        ] : [
          ["Today's estimated cost (USD)", record.today?.estimated_cost_usd],
          ["Daily budget remaining (USD)", record.budget?.soft_limit_enabled ? record.budget.remaining_usd : "No limit configured"],
        ];
        sections.push({ title: config.title, entries: fields.map(([title, detail]) => ({ title, detail: detail == null ? "Unavailable" : String(detail) })), empty: "Data unavailable." });
      }
    } else {
      const names = { policies: "Company rules", knowledge: "Reference notes", notifications: "Unread updates", workflows: "Available workflows", automations: "Automation rules", skills: "Related skills", departments: "Departments", teams: "Teams", integrations: "Connected services", "/tools": "Tool risks" };
      config.resources.forEach((key) => {
        let items = list(key);
        if (key === "notifications") items = items.filter((item) => !item.read_at);
        if (key === "policies") items = items.filter((item) => item.is_active !== false);
        sections.push({ title: names[key] || "References", entries: records(items), empty: data[key] == null ? "Data unavailable." : "No additional records available." });
      });
    }
    return { title: config.title, metrics, sections, links: config.links, guide: config.guide };
  }

  function create({ api, getSession, escapeHtml: esc, getAgentId, getMainTitles = () => [], getMainText = () => "", getSelectedTaskId = () => "", canNavigate = () => true, navigate, openTask, openResult, showResults }) {
    const $ = (id) => document.getElementById(id);
    let view = "home", generation = 0, library = false, lastModel = null;
    function reconcile() {
      if (library || !lastModel) return;
      const model = excludeMainRecords(lastModel.model, getMainTitles(), getMainText());
      const failures = lastModel.failures;
    let actions = [];
    $("sidebarContext").innerHTML = (failures ? '<p class="context-notice">Some page data is unavailable. Check your access or try refreshing.</p>' : "") +
      (model.metrics.length ? `<div class="context-metrics">${model.metrics.map(([label, count]) => `<div class="context-metric"><strong>${esc(String(count))}</strong><span>${esc(label)}</span></div>`).join("")}</div>` : "") +
      model.sections.map((section) => `<section class="context-section"><h4>${esc(section.title)}</h4>${section.compact && section.entries.length ? `<div class="context-chips" tabindex="0" aria-label="${esc(section.title)}">${section.entries.map((entry) => `<span class="context-chip">${esc(entry.title)}</span>`).join("")}</div>` : section.entries.map((entry) => {
        const index = actions.push(entry) - 1;
        return `<article class="context-record">${entry.task ? `<button class="link-btn context-result-link" data-context-action="${index}" title="${entry.kind === "result" ? "View result" : "Open task"}">${esc(entry.title)}</button>` : `<strong>${esc(entry.title)}</strong>`}${entry.detail ? `<p>${esc(entry.detail)}</p>` : ""}</article>`;
      }).join("") || `<p class="muted">${esc(failures ? "No accessible records loaded." : section.empty)}</p>`}</section>`).join("") +
      `<div class="context-links">${model.links.filter(([, target]) => canNavigate(target)).map(([label, target]) => `<button class="secondary" data-context-view="${esc(target)}">${esc(label)}</button>`).join("")}</div>`;
    $("sidebarContext").querySelectorAll("[data-context-action]").forEach((button) => {
      button.onclick = () => { const entry = actions[Number(button.dataset.contextAction)]; if (entry.kind === "result") openResult(entry.task); else openTask(entry.task); };
    });
    $("sidebarContext").querySelectorAll("[data-context-view]").forEach((button) => { button.onclick = () => navigate(button.dataset.contextView); });
    }
    function setMode(results) {
      library = results;
      $("resultLibrary").classList.toggle("hidden", !results);
      $("sidebarContext").classList.toggle("hidden", results);
      $("btnSidebarContext").classList.toggle("active", !results);
      $("btnSidebarResults").classList.toggle("active", results);
      $("btnSidebarContext").setAttribute("aria-selected", String(!results));
      $("btnSidebarResults").setAttribute("aria-selected", String(results));
      $("outputTitle").textContent = results ? "AI Work Results" : (configs[view]?.title || "Page context");
      $("sidebarEyebrow").textContent = results ? "WORK LIBRARY" : view.replace(/-/g, " ").toUpperCase();
      const guide = $("sidebarPageGuide");
      if (guide) {
        guide.href = `data:text/plain;charset=utf-8,${encodeURIComponent(guideText(view))}`;
        guide.download = `${view}-guide.txt`;
        guide.title = `${configs[view]?.guide?.page || "Page"} guide`;
        guide.setAttribute("aria-label", `Download ${configs[view]?.guide?.page || "page"} guide`);
      }
    }
    async function refresh() {
      if (library) { showResults(); return; }
      const session = { ...getSession() };
      if (!session.companyId || !session.userId) return;
      const request = ++generation, requestedView = view;
      const config = configs[view] || { resources: [] };
      $("btnRefreshSidebar").disabled = true;
      $("sidebarContext").innerHTML = '<div class="empty">Loading page context...</div>';
      try {
        const responses = await Promise.allSettled(config.resources.map((key) => api(key.startsWith("/") ? key : `/companies/${session.companyId}/${key}`)));
        if (request !== generation || library || requestedView !== view || session.companyId !== getSession().companyId || session.userId !== getSession().userId) return;
        const data = Object.fromEntries(responses.map((response, index) => [config.resources[index], response.status === "fulfilled" ? response.value : null]));
        const failures = responses.filter((response) => response.status === "rejected").length;
        lastModel = { model: buildContext(view, data, getAgentId(view), getSelectedTaskId()), failures };
        reconcile();
      } finally { if (request === generation) $("btnRefreshSidebar").disabled = false; }
    }
    function show(nextView) {
      generation++; lastModel = null; view = nextView; setMode(nextView === "result-preview");
      $("btnRefreshSidebar").disabled = false;
      if (library) return;
      return refresh();
    }
    function results() { generation++; setMode(true); $("btnRefreshSidebar").disabled = false; showResults(true); }
    function reset() { generation++; lastModel = null; $("sidebarContext").textContent = ""; setMode(false); $("btnRefreshSidebar").disabled = false; }
    $("btnSidebarContext").onclick = () => { generation++; setMode(false); refresh(); };
    $("btnSidebarResults").onclick = results;
    $("btnRefreshSidebar").onclick = refresh;
    return { show, refresh, results, reset, reconcile };
  }

  const exports = { configs, buildContext, excludeMainRecords, guideText, create };
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  else root.WorkspaceSidebar = exports;
})(globalThis);
