(function (root) {
  const labels = { pending: "Ready to start", planning: "Planning", running: "In progress", waiting_approval: "Awaiting approval", failed: "Needs investigation", accepted: "Ready for handoff" };

  function buildQueue({ tasks = [], approvals = [], delegations = [], agents = [] }) {
    const names = new Map((agents || []).map((agent) => [agent.id, agent.name]));
    const taskMap = new Map((tasks || []).map((task) => [task.id, task]));
    const pendingApprovals = (approvals || []).filter((approval) => approval.status === "pending");
    const approvedTaskIds = new Set(pendingApprovals.map((approval) => approval.task_id));
    const handoffs = (delegations || []).filter((item) => ["pending", "accepted", "running", "waiting_approval"].includes(item.status) && !approvedTaskIds.has(item.child_task_id));
    const childIds = new Set(handoffs.map((item) => item.child_task_id).filter(Boolean));
    const queue = pendingApprovals.map((approval) => ({
      id: approval.id, type: "approval", title: taskMap.get(approval.task_id)?.title || approval.action,
      detail: approval.reason || approval.action, status: "Review required", agent: names.get(approval.agent_instance_id) || "AI Employee",
      group: "action", priority: 0, created_at: approval.created_at, action: "Review approval", view: "approvals", record: approval,
    }));
    (tasks || []).filter((task) => ["pending", "planning", "running", "waiting_approval", "failed"].includes(task.status) && !approvedTaskIds.has(task.id) && !childIds.has(task.id))
      .forEach((task) => queue.push({
        id: task.id, type: "task", title: task.title, detail: task.instruction,
        status: labels[task.status], agent: names.get(task.agent_instance_id) || "AI Employee",
        group: ["pending", "failed"].includes(task.status) ? "action" : "progress",
        priority: task.status === "failed" ? 1 : 3, created_at: task.created_at,
        action: task.status === "pending" && task.mode === "consult" ? "Run consultation" : "Open task",
        view: "tasks", record: task,
      }));
    handoffs.forEach((item) => {
      const childStatus = taskMap.get(item.child_task_id)?.status;
      const underway = ["planning", "running", "waiting_approval"].includes(childStatus);
      queue.push({
      id: item.id, type: "delegation", title: item.title, detail: item.instruction || item.capability,
      status: underway ? labels[childStatus] : labels[item.status], agent: `${names.get(item.source_agent_instance_id) || "Source AI"} to ${names.get(item.target_agent_instance_id) || "Target AI"}`,
      group: !underway && ["pending", "accepted"].includes(item.status) ? "action" : "progress", priority: 2, created_at: item.created_at,
      action: "Review handoff", view: "delegation", record: item,
      });
    });
    return queue.sort((a, b) => a.priority - b.priority || (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0));
  }

  function filterQueue(queue, { tab, type, query }) {
    const search = query.trim().toLowerCase();
    return queue.filter((item) => (tab === "all" || item.group === tab) && (!type || item.type === type) &&
      (!search || [item.title, item.detail, item.agent, item.status].join(" ").toLowerCase().includes(search)));
  }

  function attributionMarkup(history, unavailable, esc) {
    if (!history) return `<footer class="inbox-watermark">${unavailable ? "History unavailable" : "No recorded history"}</footer>`;
    const raw = history.performed_at || "";
    const date = new Date(raw && !/(Z|[+-]\d{2}:\d{2})$/i.test(raw) ? `${raw}Z` : raw);
    const valid = !Number.isNaN(date.getTime());
    const time = valid ? `<time datetime="${esc(date.toISOString())}">${esc(new Intl.DateTimeFormat("en", {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short",
    }).format(date))}</time>` : "Time not recorded";
    const action = String(history.action || "Recorded action").replace(/[._]/g, " ");
    const actorType = { human: "Human", agent: "AI agent" }[history.actor_type];
    return `<footer class="inbox-watermark" aria-label="Latest recorded action">
      <span class="inbox-watermark-label">Latest recorded action</span><span>${esc(action)}</span>
      <span>${esc(history.actor_name || "Actor not recorded")}${actorType ? ` <span class="inbox-actor-type">(${actorType})</span>` : ""}</span>${time}
    </footer>`;
  }

  function create({ api, getSession, escapeHtml: esc, navigate, openTask, onChanged }) {
    const $ = (id) => document.getElementById(id);
    let queue = [], tab = "action", generation = 0, partial = false;
    const busy = new Set();
    const types = { task: "Task", approval: "Approval", delegation: "Handoff" };
    function render() {
      const items = filterQueue(queue, { tab, type: $("inboxType").value, query: $("inboxSearch").value });
      $("inboxCount").textContent = `${items.length} ${items.length === 1 ? "item" : "items"}${partial ? " / partial data" : ""}`;
      $("inboxList").innerHTML = items.map((item, index) => `<article class="inbox-card">
        <div class="row between"><span class="type-tag ${item.type}">${types[item.type]}</span><span class="inbox-status">${esc(item.status)}</span></div>
        <strong>${esc(item.title)}</strong><p class="inbox-description">${esc(item.detail || "")}</p>
        <div class="meta">${esc(item.agent)}</div>
        <div class="actions"><button class="${item.priority === 0 ? "primary" : "secondary"}" data-inbox-item="${index}" ${busy.has(item.id) ? "disabled" : ""}>${busy.has(item.id) ? "Working..." : item.action}</button></div>
        ${attributionMarkup(item.history, item.historyUnavailable, esc)}
      </article>`).join("") || `<div class="empty">${partial ? "No matching items in the available data." : queue.length ? "No items match this view." : "Your inbox is clear."}</div>`;
      $("inboxList").querySelectorAll("[data-inbox-item]").forEach((button) => {
        button.onclick = async () => {
          const item = items[Number(button.dataset.inboxItem)];
          if (busy.has(item.id)) return;
          if (item.action !== "Run consultation") { if (item.type === "task") openTask(item.record); else navigate(item.view); return; }
          const session = { ...getSession() }, request = generation;
          busy.add(item.id); render();
          try {
            await api(`/companies/${session.companyId}/tasks/${item.id}/consult`, { method: "POST", body: "{}" });
            if (request !== generation || session.userId !== getSession().userId || session.companyId !== getSession().companyId) return;
            await load();
            if (session.userId === getSession().userId && session.companyId === getSession().companyId) onChanged();
          } catch (error) {
            if (request === generation) { $("inboxNotice").textContent = error.message; $("inboxNotice").classList.remove("hidden"); }
          } finally {
            busy.delete(item.id);
            if (session.userId === getSession().userId && session.companyId === getSession().companyId) render();
          }
        };
      });
    }

    async function load() {
      const session = { ...getSession() };
      if (!session.companyId || !session.userId) return;
      const request = ++generation;
      $("btnRefreshInbox").disabled = true;
      $("inboxList").innerHTML = '<div class="empty">Loading inbox...</div>';
      try {
        const keys = ["tasks", "approvals", "delegation-requests", "agents", "inbox-attribution/task", "inbox-attribution/approval", "inbox-attribution/delegation"];
        const responses = await Promise.allSettled(keys.map((key) => api(`/companies/${session.companyId}/${key}`)));
        if (request !== generation || session.userId !== getSession().userId || session.companyId !== getSession().companyId) return;
        const values = responses.map((response) => response.status === "fulfilled" ? response.value : null);
        partial = values.slice(0, 3).some((value) => value == null);
        queue = buildQueue({ tasks: values[0], approvals: values[1], delegations: values[2], agents: values[3] });
        const historyIndexes = { task: 4, approval: 5, delegation: 6 };
        const histories = values.slice(4).map((rows) => new Map((rows || []).map((row) => [row.resource_id, row])));
        queue.forEach((item) => {
          const index = historyIndexes[item.type];
          item.history = histories[index - 4].get(item.id);
          item.historyUnavailable = values[index] == null;
        });
        const failed = keys.filter((_, index) => responses[index].status === "rejected");
        $("inboxNotice").classList.toggle("hidden", !failed.length);
        $("inboxNotice").textContent = failed.length ? `Some inbox data is unavailable (${failed.join(", ")}). Check your access or refresh.` : "";
        $("inboxStats").innerHTML = [["Needs review", "approval"], ["Task actions", "task"], ["Handoffs to review", "delegation"]].map(([label, type]) => {
          const key = { approval: 1, task: 0, delegation: 2 }[type];
          const count = values[key] == null ? "Unavailable" : queue.filter((item) => item.type === type && item.group === "action").length;
          return `<div class="stat"><div class="n ${count === "Unavailable" ? "inbox-unavailable" : ""}">${count}</div><div class="l">${label}</div></div>`;
        }).join("") + `<div class="stat"><div class="n ${partial ? "inbox-unavailable" : ""}">${partial ? "Unavailable" : queue.filter((item) => item.group === "progress").length}</div><div class="l">In progress</div></div>`;
        render();
      } finally { if (request === generation) $("btnRefreshInbox").disabled = false; }
    }
    function reset() {
      generation++; queue = []; busy.clear(); tab = "action"; partial = false;
      $("inboxSearch").value = ""; $("inboxType").value = "";
      ["inboxStats", "inboxList", "inboxCount", "inboxNotice"].forEach((id) => { $(id).textContent = ""; });
      $("inboxNotice").classList.add("hidden"); $("btnRefreshInbox").disabled = false;
      updateTabs();
    }
    function updateTabs() {
      document.querySelectorAll("[data-inbox-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.inboxTab === tab);
        button.setAttribute("aria-selected", String(button.dataset.inboxTab === tab));
      });
    }
    $("btnRefreshInbox").onclick = load;
    $("inboxSearch").oninput = render; $("inboxType").onchange = render;
    document.querySelectorAll("[data-inbox-tab]").forEach((button) => {
      button.onclick = () => { tab = button.dataset.inboxTab; updateTabs(); render(); };
    });
    return { load, reset };
  }
  const exports = { buildQueue, filterQueue, attributionMarkup, create };
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  else root.WorkspaceInbox = exports;
})(globalThis);
