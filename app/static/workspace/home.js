(function (root) {
  const labels = {
    pending: "Not started", planning: "Planning", running: "In progress",
    waiting_approval: "Awaiting approval", completed: "Completed", failed: "Failed", cancelled: "Cancelled",
  };
  const openStatuses = new Set(["pending", "planning", "running", "waiting_approval"]);

  function summarize({ tasks, approvals, agents }) {
    const counts = Object.fromEntries(Object.keys(labels).map((status) => [status, 0]));
    (tasks || []).forEach((task) => { counts[task.status] = (counts[task.status] || 0) + 1; });
    const pendingApprovals = (approvals || []).filter((approval) => approval.status === "pending");
    const taskMap = new Map((tasks || []).map((task) => [task.id, task]));
    const approvalTasks = new Set(pendingApprovals.map((approval) => approval.task_id));
    const attention = pendingApprovals.map((approval) => ({
      id: approval.id, title: taskMap.get(approval.task_id)?.title || approval.action,
      detail: approval.reason || approval.action, label: "Pending approvals", view: "approvals", priority: 0,
    }));
    (tasks || []).filter((task) => ["failed", "pending", "waiting_approval"].includes(task.status) && !approvalTasks.has(task.id))
      .forEach((task) => attention.push({
        id: task.id, title: task.title, detail: task.status === "failed" ? "Review the failed task" : labels[task.status],
        label: labels[task.status], view: "tasks", task, priority: task.status === "failed" ? 1 : task.status === "waiting_approval" ? 2 : 3,
      }));
    attention.sort((a, b) => a.priority - b.priority);
    return {
      counts, attention,
      open: tasks == null ? null : tasks.filter((task) => openStatuses.has(task.status)).length,
      results: tasks == null ? null : tasks.filter((task) => task.result && task.result.trim()).length,
      active: agents == null ? null : agents.filter((agent) => agent.status === "active").length,
      pendingApprovals: approvals == null ? null : pendingApprovals.length,
      recent: [...(tasks || [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 5),
    };
  }


  const ROLE_LABELS = {
    owner: "Owner",
    ai_admin: "AI Administrator",
    manager: "Manager",
    reservation: "Reservation",
    member: "Member",
  };

  function roleQuickActions(role) {
    const common = [
      { id: "chat", title: "Chat with AI", desc: "Advisory conversation" },
      { id: "tasks", title: "Create task", desc: "Run tools with policy" },
      { id: "inbox", title: "Inbox", desc: "Approvals & handoffs" },
    ];
    if (role === "reservation") {
      return [
        { id: "chat", title: "Ask availability", desc: "Advisory chat first" },
        { id: "tasks", title: "Run reservation task", desc: "Search / quote / book" },
        { id: "results", title: "Quotations & results", desc: "Find drafts & rates" },
        { id: "inbox", title: "Approvals", desc: "Pending bookings" },
      ];
    }
    if (role === "ai_admin") {
      return [
        { id: "agents", title: "AI Employees", desc: "Hire & access" },
        { id: "policy-management", title: "Policies", desc: "Allow / approve tools" },
        { id: "users", title: "Users & roles", desc: "Team access" },
        { id: "tasks", title: "Tasks", desc: "Operational work" },
      ];
    }
    if (role === "owner" || role === "manager") {
      return [
        { id: "home", title: "Overview", desc: "Command center" },
        { id: "agents", title: "AI team", desc: "Workforce" },
        { id: "governance", title: "Governance", desc: "Controls & metrics" },
        { id: "users", title: "Users", desc: "Roles & access" },
        { id: "results", title: "Results", desc: "Work outputs" },
      ];
    }
    return common;
  }

  function create({ api, getSession, escapeHtml: esc, navigate, openTask, openResult }) {
    const $ = (id) => document.getElementById(id);
    let generation = 0;
    const empty = (text) => `<div class="empty">${esc(text)}</div>`;
    const number = (value) => value == null ? "Unavailable" : value;
    const date = (value) => {
      if (!value) return "";
      const utc = !value.endsWith("Z") && !/[+-]\d{2}:\d{2}$/.test(value) ? value + "Z" : value;
      return new Date(utc).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
    };

    async function load() {
      const session = { ...getSession() };
      if (!session.companyId || !session.userId) return;
      const request = ++generation;
      $("btnRefreshHome").disabled = true;
      $("homeGreeting").textContent = session.userName ? `Hello, ${session.userName}` : "Workspace overview";
      $("homeUpdated").textContent = "Loading overview...";
      ["homeStats", "homeInbox", "homeProgress", "homeRecent", "homeAgents"].forEach((id) => { $(id).innerHTML = empty("Loading..."); });
      $("homeNotice").classList.add("hidden");
      try {
        const resources = ["agents", "tasks", "approvals"];
        const responses = await Promise.allSettled(resources.map((resource) => api(`/companies/${session.companyId}/${resource}`)));
        if (request !== generation || session.companyId !== getSession().companyId || session.userId !== getSession().userId) return;
        const data = Object.fromEntries(responses.map((response, index) => [resources[index], response.status === "fulfilled" ? response.value : null]));
        const summary = summarize(data);
        const names = new Map((data.agents || []).map((agent) => [agent.id, agent.name]));
        const failures = resources.filter((_, index) => responses[index].status === "rejected");
        const resourceNames = { agents: "AI team", tasks: "tasks", approvals: "approvals" };
        $("homeNotice").classList.toggle("hidden", !failures.length);
        $("homeNotice").textContent = failures.length ? `${failures.map((key) => resourceNames[key]).join(", ")} data is unavailable. Check your access or refresh the overview.` : "";
        $("homeStats").innerHTML = [
          ["Active AI employees", summary.active, "agents"], ["Open tasks", summary.open, "tasks"],
          ["Available results", summary.results, "results"], ["Pending approvals", summary.pendingApprovals, "approvals"],
        ].map(([label, value, view]) => `<button class="stat home-metric" data-home-view="${view}" ${value == null ? "disabled" : ""}>
          <span class="n ${value == null ? "unavailable" : ""}">${number(value)}</span><span class="l">${label}</span></button>`).join("");
        $("homeInbox").innerHTML = summary.attention.slice(0, 6).map((entry, index) =>
          `<div class="home-work-row"><div><span class="home-status ${entry.priority < 2 ? "needs-action" : ""}">${esc(entry.label)}</span>
          <strong>${esc(entry.title)}</strong><span class="meta">${esc(entry.detail)}</span></div>
          <button class="secondary" data-home-attention="${index}">${entry.view === "approvals" ? "Review" : "Open"}</button></div>`).join("") ||
          empty(data.tasks == null || data.approvals == null ? "Some attention data is unavailable." : "No tasks need attention.");
        $("homeProgress").innerHTML = data.tasks == null ? empty("Task data is unavailable.") : !data.tasks.length ? empty("No tasks yet.") :
          Object.entries(summary.counts).filter(([, count]) => count > 0).map(([status, count]) =>
            `<div class="home-progress-row"><span>${esc(labels[status] || status)}</span><strong>${count}</strong>
            <progress value="${count}" max="${data.tasks.length}" aria-label="${esc(labels[status] || status)}"></progress></div>`).join("");
        $("homeRecent").innerHTML = summary.recent.map((task, index) =>
          `<div class="home-work-row"><div><strong>${esc(task.title)}</strong><span class="meta">${esc(names.get(task.agent_instance_id) || "AI Employee")} / ${esc(labels[task.status] || task.status)}</span>
          <span class="meta">Created ${esc(date(task.created_at))}</span></div>
          <button class="secondary" data-home-task="${index}">${task.result && task.result.trim() ? "View result" : "Open"}</button></div>`).join("") ||
          empty(data.tasks == null ? "Task data is unavailable." : "No tasks yet.");
        $("homeAgents").innerHTML = data.agents == null ? empty("AI team data is unavailable.") : data.agents.length ?
          [...data.agents].sort((a, b) => Number(b.status === "active") - Number(a.status === "active")).slice(0, 6).map((agent) => {
            const work = data.tasks == null ? "Workload unavailable" : `${data.tasks.filter((task) => task.agent_instance_id === agent.id && openStatuses.has(task.status)).length} open tasks`;
            return `<div class="home-work-row"><div><strong>${esc(agent.name)}</strong><span class="meta">${agent.status === "active" ? "Active" : "Inactive"} / ${work}</span></div></div>`;
          }).join("") : empty("No AI employees yet.") + '<button class="secondary" data-home-view="marketplace">Choose an AI employee</button>';
        $("homeUpdated").textContent = `Updated ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`;

        // Job 41 — role-aware greeting + quick actions + inventory status
        const role = session.role || "member";
        const roleName = ROLE_LABELS[role] || role;
        $("homeGreeting").textContent = `Welcome · ${roleName}`;
        if ($("homeRoleLabel")) $("homeRoleLabel").textContent = roleName;
        const actions = roleQuickActions(role);
        if ($("homeQuickActions")) {
          $("homeQuickActions").innerHTML = actions.map((a) =>
            `<button type="button" data-home-view="${esc(a.id)}"><span class="hq-title">${esc(a.title)}</span><span class="hq-desc">${esc(a.desc)}</span></button>`
          ).join("");
        }
        const showInv = ["owner", "ai_admin", "manager", "reservation"].includes(role);
        if ($("homeInventorySection")) $("homeInventorySection").classList.toggle("hidden", !showInv);
        if (showInv && $("homeInventoryStatus")) {
          try {
            const inv = await api(`/companies/${session.companyId}/inventory`);
            const n = (inv.items || []).length;
            $("homeInventoryStatus").innerHTML = n
              ? `<div class="item"><strong>${n} availability product(s)</strong><div class="meta">Durable inventory ready for search_availability</div></div>`
              : `<div class="item"><strong>No inventory yet</strong><div class="meta">Owner/AI Admin: Agents → Seed reservation demo data</div>
                 <button type="button" class="secondary" data-home-seed="1">Seed demo data</button></div>`;
          } catch (e) {
            $("homeInventoryStatus").innerHTML = `<div class="muted">${esc(e.message || "Inventory unavailable")}</div>`;
          }
        }
        if ($("btnHomeRefreshInventory")) {
          $("btnHomeRefreshInventory").onclick = () => load();
        }
        $("homeInventoryStatus")?.querySelectorAll("[data-home-seed]").forEach((button) => {
          button.onclick = async () => {
            try {
              await api(`/companies/${session.companyId}/demo/seed-reservation`, { method: "POST", body: "{}" });
              await load();
            } catch (err) { alert(err.message); }
          };
        });

        $("view-home").querySelectorAll("[data-home-view]").forEach((button) => { button.onclick = () => navigate(button.dataset.homeView); });
        $("homeInbox").querySelectorAll("[data-home-attention]").forEach((button) => {
          button.onclick = () => { const entry = summary.attention[Number(button.dataset.homeAttention)]; if (entry.task) openTask(entry.task); else navigate(entry.view); };
        });
        $("homeRecent").querySelectorAll("[data-home-task]").forEach((button) => {
          button.onclick = () => { const task = summary.recent[Number(button.dataset.homeTask)]; if (task.result && task.result.trim()) openResult(task); else openTask(task); };
        });
      } finally {
        if (request === generation) $("btnRefreshHome").disabled = false;
      }
    }
    function reset() {
      generation++;
      ["homeStats", "homeInbox", "homeProgress", "homeRecent", "homeAgents", "homeQuickActions", "homeInventoryStatus"].forEach((id) => { if ($(id)) $(id).textContent = ""; });
      $("homeGreeting").textContent = "Workspace overview";
      $("homeUpdated").textContent = "";
      $("homeNotice").textContent = "";
      $("homeNotice").classList.add("hidden");
      $("btnRefreshHome").disabled = false;
    }
    $("btnRefreshHome").onclick = load;
    return { load, reset };
  }
  const exports = { summarize, create };
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  else root.WorkspaceHome = exports;
})(globalThis);
