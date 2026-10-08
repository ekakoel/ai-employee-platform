/* Job 12 — Human workspace client */
(function () {
  const state = {
    apiBase: localStorage.getItem("ws_apiBase") || "/api/v1",
    companyId: localStorage.getItem("ws_companyId") || "",
    userId: localStorage.getItem("ws_userId") || "",
    accessToken: localStorage.getItem("ws_accessToken") || "",
    connected: false,
    tasks: [],
    agents: [],
  };

  const $ = (id) => document.getElementById(id);

  function clearSession() {
    state.companyId = "";
    state.userId = "";
    state.accessToken = "";
    state.connected = false;
    localStorage.removeItem("ws_companyId");
    localStorage.removeItem("ws_userId");
    localStorage.removeItem("ws_accessToken");
    localStorage.removeItem("ws_refreshToken");
    if ($("companyId")) $("companyId").value = "";
    if ($("userId")) $("userId").value = "";
    setConnected(false);
  }

  function headers(json = true, skipAuth = false) {
    const h = {};
    if (json) h["Content-Type"] = "application/json";
    if (!skipAuth) {
      if (state.userId) h["X-User-ID"] = state.userId;
      if (state.accessToken) h["Authorization"] = "Bearer " + state.accessToken;
    }
    return h;
  }

  async function api(path, opts = {}) {
    const skipAuth = !!opts.skipAuth;
    const fetchOpts = { ...opts };
    delete fetchOpts.skipAuth;
    const url = state.apiBase.replace(/\/$/, "") + path;
    const res = await fetch(url, {
      ...fetchOpts,
      headers: {
        ...headers(!(opts.body instanceof FormData), skipAuth),
        ...(opts.headers || {}),
      },
    });
    let data = null;
    const text = await res.text();
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : text || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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

  function setInboxBadge(n) {
    const el = $("inboxBadge");
    if (n > 0) {
      el.textContent = String(n);
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  }

  const titles = {
    setup: "Setup",
    workforce: "Workforce Overview",
    inbox: "AI Inbox",
    tasks: "Task Center",
    approvals: "Approval Center",
    agents: "Agent Dashboard",
    consult: "Consultation",
    directory: "Agent Directory",
    knowledge: "Knowledge",
    delegation: "Delegation",
    automation: "Automation",
    governance: "Governance",
  };

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    const view = $("view-" + name);
    if (view) view.classList.add("active");
    const btn = document.querySelector(`.nav-btn[data-view="${name}"]`);
    if (btn) btn.classList.add("active");
    $("viewTitle").textContent = titles[name] || name;
    if (!state.connected) return;
    if (name === "workforce") loadWorkforce();
    if (name === "inbox") loadInbox();
    if (name === "agents") loadAgents();
    if (name === "tasks") {
      loadAgentOptions();
      loadTasks();
    }
    if (name === "approvals") loadApprovals();
    if (name === "consult") loadAgentOptions();
    if (name === "directory") listDirectory();
    if (name === "delegation") {
      loadAgentOptions();
      loadDelegations();
    }
    if (name === "automation") {
      loadAgentOptions();
      loadAutomations();
    }
    if (name === "governance") loadGovernance();
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
      await refreshInboxBadge();
      showView("workforce");
    } catch (err) {
      $("setupLog").textContent =
        "Connect failed: " + err.message +
        "\nSession cleared. Use Quick start or create a new company, then Register/Login.";
      clearSession();
    }
  };

  const btnClear = $("btnClearSession");
  if (btnClear) {
    btnClear.onclick = () => {
      clearSession();
      $("setupLog").textContent = "Session cleared. Use Quick start or fill company/user IDs.";
    };
  }

  $("btnQuickStart").onclick = async () => {

    state.apiBase = $("apiBase").value.trim() || "/api/v1";
    localStorage.setItem("ws_apiBase", state.apiBase);
    const log = $("setupLog");
    // Drop stale credentials so bootstrap is not blocked by old JWT/user
    clearSession();
    state.apiBase = $("apiBase").value.trim() || "/api/v1";
    try {
      log.textContent = "Creating company...";
      const co = await api("/companies", {
        method: "POST",
        body: JSON.stringify({
          name: "Workspace Demo Co " + new Date().toISOString().slice(0, 19),
        }),
        skipAuth: true,
      });
      const user = await api(`/companies/${co.id}/users`, {
        method: "POST",
        body: JSON.stringify({
          name: "Workspace Owner",
          email: `owner-${Date.now()}@demo.local`,
          role: "owner",
          password: "demo-pass-123",
        }),
        skipAuth: true,
      });
      state.companyId = co.id;
      state.userId = user.id;
      state.accessToken = "";
      $("companyId").value = co.id;
      $("userId").value = user.id;
      if ($("loginEmail")) $("loginEmail").value = user.email || "";
      if ($("loginPassword")) $("loginPassword").value = "demo-pass-123";
      localStorage.setItem("ws_companyId", co.id);
      localStorage.setItem("ws_userId", user.id);

      // Login to obtain JWT for subsequent calls
      try {
        const tok = await api("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            company_id: co.id,
            email: user.email,
            password: "demo-pass-123",
          }),
          skipAuth: true,
        });
        state.accessToken = tok.access_token || "";
        localStorage.setItem("ws_accessToken", state.accessToken);
        if (tok.refresh_token) {
          localStorage.setItem("ws_refreshToken", tok.refresh_token);
        }
      } catch (loginErr) {
        log.textContent += "\nLogin after create skipped: " + loginErr.message;
      }

      const catalog = await api("/agent-catalog", { skipAuth: true });
      const res = catalog.find((c) => c.slug === "reservation") || catalog[0];
      if (res) {
        await api(`/companies/${co.id}/agents/${res.id}/hire`, {
          method: "POST",
          body: JSON.stringify({ name: "Desk AI" }),
        });
      }
      const contract = catalog.find((c) => c.slug === "contract-manager");
      if (contract) {
        await api(`/companies/${co.id}/agents/${contract.id}/hire`, {
          method: "POST",
          body: JSON.stringify({ name: "Contract AI" }),
        });
      }
      setConnected(true);
      log.textContent =
        `Company ${co.id}\nUser ${user.id}\nEmail ${user.email}\nPassword demo-pass-123\nAgents hired.\nReady.`;
      await refreshInboxBadge();
      showView("workforce");
    } catch (err) {
      log.textContent += "\nError: " + err.message;
      setConnected(false);
    }
  };

  // ---- Shared data ----
  async function loadAgentOptions() {
    const agents = await api(`/companies/${state.companyId}/agents`);
    state.agents = agents;
    const opts = agents
      .map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`)
      .join("");
    ["taskAgent", "consultAgent", "delSource", "delTarget", "autoAgent"].forEach((id) => {
      const el = $(id);
      if (el) el.innerHTML = opts;
    });
  }

  async function refreshInboxBadge() {
    try {
      const [tasks, approvals, dels, notif] = await Promise.all([
        api(`/companies/${state.companyId}/tasks`),
        api(`/companies/${state.companyId}/approvals`).catch(() => []),
        api(`/companies/${state.companyId}/delegation-requests`).catch(() => []),
        api(`/companies/${state.companyId}/notifications/unread-count`).catch(() => ({
          count: 0,
        })),
      ]);
      const n =
        tasks.filter((t) => t.status === "pending").length +
        (approvals || []).filter((a) => a.status === "pending").length +
        (dels || []).filter((d) => d.status === "pending" || d.status === "accepted")
          .length +
        (notif && notif.count ? notif.count : 0);
      setInboxBadge(n);
    } catch {
      setInboxBadge(0);
    }
  }

  async function loadNotifications() {
    try {
      const [notes, count] = await Promise.all([
        api(`/companies/${state.companyId}/notifications?limit=50`),
        api(`/companies/${state.companyId}/notifications/unread-count`),
      ]);
      $("notifStats").innerHTML = [
        `<span class="stat"><strong>${count.count}</strong> unread</span>`,
        `<span class="stat"><strong>${notes.length}</strong> shown</span>`,
      ].join("");
      if (!notes.length) {
        $("notifList").innerHTML = '<p class="muted">No notifications yet.</p>';
        return;
      }
      $("notifList").innerHTML = notes
        .map(
          (n) => `
        <div class="list-item ${n.read_at ? "muted" : ""}">
          <div>
            <strong>${n.title}</strong>
            <div class="muted">${n.type} · ${n.created_at || ""}</div>
            <div>${(n.body || "").slice(0, 200)}</div>
          </div>
          <div class="row">
            ${
              n.read_at
                ? "<span class=\"muted\">Read</span>"
                : `<button class="secondary" data-notif-read="${n.id}">Mark read</button>`
            }
          </div>
        </div>`
        )
        .join("");
      $("notifList").querySelectorAll("[data-notif-read]").forEach((btn) => {
        btn.onclick = async () => {
          await api(
            `/companies/${state.companyId}/notifications/${btn.dataset.notifRead}/read`,
            { method: "POST", body: "{}" }
          );
          await loadNotifications();
          await refreshInboxBadge();
        };
      });
    } catch (err) {
      $("notifList").innerHTML = `<p class="danger">${err.message}</p>`;
    }
  }

  // ---- Workforce Overview ----
  async function loadWorkforce() {
    try {
      const [agents, tasks, approvals] = await Promise.all([
        api(`/companies/${state.companyId}/agents`),
        api(`/companies/${state.companyId}/tasks`),
        api(`/companies/${state.companyId}/approvals`).catch(() => []),
      ]);
      state.agents = agents;
      state.tasks = tasks;
      const pendingAppr = (approvals || []).filter((a) => a.status === "pending");
      const active = agents.filter((a) => a.status === "active").length;
      $("wfStats").innerHTML = [
        ["AI Employees", agents.length],
        ["Active", active],
        ["Open tasks", tasks.filter((t) => t.status !== "completed").length],
        ["Pending approvals", pendingAppr.length],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`
        )
        .join("");

      const byStatus = {};
      agents.forEach((a) => {
        byStatus[a.status] = (byStatus[a.status] || 0) + 1;
      });
      $("wfStatusBreakdown").innerHTML =
        Object.entries(byStatus)
          .map(
            ([s, n]) =>
              `<div class="item"><strong>${escapeHtml(s)}</strong><div class="meta">${n} agent(s)</div></div>`
          )
          .join("") || '<div class="muted">No agents</div>';

      $("wfActivity").innerHTML =
        tasks
          .slice(0, 8)
          .map(
            (t) =>
              `<div class="item"><strong>${escapeHtml(t.title)}</strong>
               <div class="meta">${t.mode || "execute"} · ${t.status}</div></div>`
          )
          .join("") || '<div class="muted">No recent tasks</div>';

      $("wfAgentGrid").innerHTML =
        agents
          .map(
            (a) => `<div class="agent-card">
            <h4>${escapeHtml(a.name)}</h4>
            <div class="meta">${a.status} · autonomy ${a.autonomy ?? "-"}</div>
            <div style="margin-top:0.4rem">
              ${(a.skills || [])
                .slice(0, 5)
                .map((s) => `<span class="tag">${escapeHtml(s)}</span>`)
                .join("")}
            </div>
          </div>`
          )
          .join("") || '<div class="muted">Hire agents from Agent Dashboard</div>';

      await refreshInboxBadge();
    } catch (err) {
      $("wfStats").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }

  // ---- AI Inbox ----
  async function loadInbox() {
    try {
      const [tasks, approvals, dels] = await Promise.all([
        api(`/companies/${state.companyId}/tasks`),
        api(`/companies/${state.companyId}/approvals`).catch(() => []),
        api(`/companies/${state.companyId}/delegation-requests`).catch(() => []),
      ]);
      const pendingTasks = tasks.filter((t) => t.status === "pending");
      const pendingAppr = (approvals || []).filter((a) => a.status === "pending");
      const openDels = (dels || []).filter(
        (d) => d.status === "pending" || d.status === "accepted"
      );

      $("inboxStats").innerHTML = [
        ["Pending tasks", pendingTasks.length],
        ["Approvals", pendingAppr.length],
        ["Delegations", openDels.length],
        ["Total", pendingTasks.length + pendingAppr.length + openDels.length],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`
        )
        .join("");

      const items = [];
      pendingTasks.forEach((t) =>
        items.push({
          type: "task",
          title: t.title,
          meta: `${t.mode || "execute"} · ${t.id}`,
          action:
            t.mode === "consult"
              ? `<button class="secondary" data-inbox-consult="${t.id}">Run consult</button>`
              : "",
        })
      );
      pendingAppr.forEach((a) =>
        items.push({
          type: "approval",
          title: a.action,
          meta: a.reason || a.id,
          action: `<button class="success" data-inbox-approve="${a.id}">Approve</button>
                   <button class="danger" data-inbox-reject="${a.id}">Reject</button>`,
        })
      );
      openDels.forEach((d) =>
        items.push({
          type: "delegation",
          title: d.title,
          meta: `${d.status} · ${d.capability}`,
          action:
            d.status === "pending" || d.status === "accepted"
              ? `<button class="secondary" data-inbox-exec-del="${d.id}">Execute</button>`
              : "",
        })
      );

      $("inboxList").innerHTML =
        items
          .map(
            (i) => `<div class="item">
            <div class="row between">
              <div>
                <span class="inbox-item-type ${i.type}">${i.type}</span>
                <strong>${escapeHtml(i.title)}</strong>
                <div class="meta">${escapeHtml(i.meta)}</div>
              </div>
              <div class="row">${i.action}</div>
            </div>
          </div>`
          )
          .join("") || '<div class="muted">Inbox is clear</div>';

      setInboxBadge(items.length);

      $("inboxList").querySelectorAll("[data-inbox-consult]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/tasks/${btn.dataset.inboxConsult}/consult`,
              { method: "POST" }
            );
            loadInbox();
          } catch (err) {
            alert(err.message);
          }
        };
      });
      $("inboxList").querySelectorAll("[data-inbox-approve]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/approvals/${btn.dataset.inboxApprove}/approve`,
              { method: "POST", body: JSON.stringify({ comment: "Approved from inbox" }) }
            );
            loadInbox();
          } catch (err) {
            alert(err.message);
          }
        };
      });
      $("inboxList").querySelectorAll("[data-inbox-reject]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/approvals/${btn.dataset.inboxReject}/reject`,
              { method: "POST", body: JSON.stringify({ comment: "Rejected from inbox" }) }
            );
            loadInbox();
          } catch (err) {
            alert(err.message);
          }
        };
      });
      $("inboxList").querySelectorAll("[data-inbox-exec-del]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/delegation-requests/${btn.dataset.inboxExecDel}/execute`,
              { method: "POST", body: JSON.stringify({ mode: "consult" }) }
            );
            loadInbox();
          } catch (err) {
            alert(err.message);
          }
        };
      });
    } catch (err) {
      $("inboxList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshInbox").onclick = loadInbox;

  // ---- Agents ----
  async function loadAgents() {
    try {
      const agents = await api(`/companies/${state.companyId}/agents`);
      state.agents = agents;
      $("agentList").innerHTML =
        agents
          .map(
            (a) => `<div class="agent-card">
            <h4>${escapeHtml(a.name)}</h4>
            <div class="meta">${a.status} · autonomy ${a.autonomy ?? "-"}</div>
            <div style="margin-top:0.4rem">
              ${(a.skills || [])
                .slice(0, 6)
                .map((s) => `<span class="tag">${escapeHtml(s)}</span>`)
                .join("")}
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
      const inst = await api(
        `/companies/${state.companyId}/agents/${$("catalogSelect").value}/hire`,
        {
          method: "POST",
          body: JSON.stringify({ name: $("hireName").value.trim() || "New AI" }),
        }
      );
      $("hireLog").textContent = "Hired: " + JSON.stringify(inst, null, 2);
      loadAgents();
    } catch (err) {
      $("hireLog").textContent = err.message;
    }
  };

  // ---- Tasks ----
  async function loadTasks() {
    try {
      const tasks = await api(`/companies/${state.companyId}/tasks`);
      state.tasks = tasks;
      const filter = $("taskFilter").value;
      const filtered = tasks.filter((t) => {
        if (filter === "all") return true;
        if (filter === "pending" || filter === "completed") return t.status === filter;
        if (filter === "consult" || filter === "execute")
          return (t.mode || "execute") === filter;
        return true;
      });
      $("taskList").innerHTML =
        filtered
          .map((t) => {
            const actions =
              t.mode === "consult" && t.status === "pending"
                ? `<button class="secondary" data-consult="${t.id}">Run consult</button>`
                : "";
            return `<div class="item">
            <div class="row between">
              <div><strong>${escapeHtml(t.title)}</strong>
                <div class="meta">${t.mode || "execute"} · ${t.status} · ${t.id}</div>
              </div>
              <div class="row">${actions}</div>
            </div>
            ${
              t.result
                ? `<pre class="log" style="max-height:120px">${escapeHtml(
                    String(t.result).slice(0, 800)
                  )}</pre>`
                : ""
            }
          </div>`;
          })
          .join("") || '<div class="muted">No tasks</div>';

      $("taskList").querySelectorAll("[data-consult]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/tasks/${btn.dataset.consult}/consult`,
              { method: "POST" }
            );
            loadTasks();
            refreshInboxBadge();
          } catch (err) {
            alert(err.message);
          }
        };
      });
      await refreshInboxBadge();
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
          title: $("taskTitle").value.trim(),
          instruction: $("taskInstruction").value.trim(),
          mode: $("taskMode").value,
        }),
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
      $("approvalList").innerHTML =
        approvals
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
            refreshInboxBadge();
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
            refreshInboxBadge();
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
      const done = await api(
        `/companies/${state.companyId}/tasks/${task.id}/consult`,
        { method: "POST" }
      );
      let result = done.result;
      try {
        result = JSON.stringify(JSON.parse(done.result), null, 2);
      } catch {}
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
      $("dirList").innerHTML =
        entries
          .map(
            (e) => `<div class="agent-card">
            <h4>${escapeHtml(e.name)}</h4>
            <div class="meta">${escapeHtml(e.role)} · ${e.status}</div>
            <div style="margin-top:0.4rem">
              ${(e.capabilities || [])
                .slice(0, 10)
                .map((c) => `<span class="tag">${escapeHtml(c)}</span>`)
                .join("")}
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
      $("knowResults").innerHTML =
        hits
          .map(
            (h) =>
              `<div class="item"><div class="meta">${h.source} · score ${h.score}</div>${escapeHtml(
                (h.content || h.title || "").slice(0, 300)
              )}</div>`
          )
          .join("") || '<div class="muted">No hits</div>';
    } catch (err) {
      $("knowResults").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  };

  // ---- Delegation ----
  async function loadDelegations() {
    try {
      const list = await api(`/companies/${state.companyId}/delegation-requests`);
      $("delList").innerHTML =
        list
          .map(
            (d) => `<div class="item">
            <div class="row between">
              <div>
                <strong>${escapeHtml(d.title)}</strong>
                <div class="meta">${d.status} · ${escapeHtml(d.capability)} · ${d.id}</div>
              </div>
              ${
                d.status === "pending" || d.status === "accepted"
                  ? `<button class="secondary" data-exec-del="${d.id}">Execute</button>`
                  : ""
              }
            </div>
            ${
              d.result
                ? `<pre class="log" style="max-height:100px">${escapeHtml(
                    String(d.result).slice(0, 500)
                  )}</pre>`
                : ""
            }
          </div>`
          )
          .join("") || '<div class="muted">No delegations</div>';
      $("delList").querySelectorAll("[data-exec-del]").forEach((btn) => {
        btn.onclick = async () => {
          try {
            await api(
              `/companies/${state.companyId}/delegation-requests/${btn.dataset.execDel}/execute`,
              { method: "POST", body: JSON.stringify({ mode: "consult" }) }
            );
            loadDelegations();
          } catch (err) {
            alert(err.message);
          }
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
      refreshInboxBadge();
    } catch (err) {
      alert(err.message);
    }
  };

  // ---- Automation ----
  async function loadAutomations() {
    try {
      const [rules, runs] = await Promise.all([
        api(`/companies/${state.companyId}/automations`),
        api(`/companies/${state.companyId}/automations/runs`),
      ]);
      $("autoRules").innerHTML =
        rules
          .map(
            (r) =>
              `<div class="item"><strong>${escapeHtml(r.name)}</strong>
               <div class="meta">${r.trigger_type} · ${r.event_type || "interval " + r.interval_seconds} · ${r.is_active ? "active" : "off"}</div></div>`
          )
          .join("") || '<div class="muted">No rules</div>';
      $("autoRuns").innerHTML =
        runs
          .slice(0, 15)
          .map(
            (r) =>
              `<div class="item"><strong>${r.status}</strong>
               <div class="meta">attempt ${r.attempt} · ${escapeHtml(r.idempotency_key)} · task ${r.task_id || "-"}</div></div>`
          )
          .join("") || '<div class="muted">No runs</div>';
    } catch (err) {
      $("autoRules").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  $("btnRefreshAuto").onclick = loadAutomations;
  $("btnCreateAuto").onclick = async () => {
    try {
      const trigger = $("autoTrigger").value;
      const body = {
        agent_instance_id: $("autoAgent").value,
        name: $("autoName").value.trim() || "Automation",
        trigger_type: trigger,
        task_title_template: $("autoTitle").value.trim() || "Auto task",
        task_instruction_template: $("autoInstruction").value.trim() || "Auto instruction",
        task_mode: "consult",
      };
      if (trigger === "event") {
        body.event_type = $("autoEvent").value.trim() || "sample.event";
      } else {
        body.interval_seconds = 3600;
      }
      await api(`/companies/${state.companyId}/automations`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      $("autoLog").textContent = "Rule created.";
      loadAutomations();
    } catch (err) {
      $("autoLog").textContent = err.message;
    }
  };
  $("btnTickAuto").onclick = async () => {
    try {
      const runs = await api(`/companies/${state.companyId}/automations/tick`, {
        method: "POST",
      });
      $("autoLog").textContent = "Tick: " + JSON.stringify(runs, null, 2);
      loadAutomations();
    } catch (err) {
      $("autoLog").textContent = err.message;
    }
  };
  $("btnFireEvent").onclick = async () => {
    try {
      const eventType = $("autoEvent").value.trim() || "sample.event";
      const runs = await api(`/companies/${state.companyId}/automations/events`, {
        method: "POST",
        body: JSON.stringify({
          event_type: eventType,
          payload: { booking_id: "B-DEMO" },
          idempotency_key: eventType + ":B-DEMO:" + Date.now(),
        }),
      });
      $("autoLog").textContent = "Event: " + JSON.stringify(runs, null, 2);
      loadAutomations();
    } catch (err) {
      $("autoLog").textContent = err.message;
    }
  };


  async function loadGovernance() {
    try {
      const [ov, agents, exp, audit] = await Promise.all([
        api(`/companies/${state.companyId}/governance/overview`),
        api(`/companies/${state.companyId}/governance/agents`),
        api(`/companies/${state.companyId}/governance/experiences`),
        api(`/companies/${state.companyId}/governance/audit?limit=50`),
      ]);
      $("govStats").innerHTML = [
        ["Agents", ov.workforce.agents_total],
        ["Open tasks", ov.tasks.open],
        ["Pending approvals", ov.approvals.pending],
        ["Validated experiences", ov.experiences.validated],
      ]
        .map(
          ([l, n]) =>
            `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`
        )
        .join("");
      $("govAgents").innerHTML =
        agents
          .map(
            (a) =>
              `<div class="item"><strong>${escapeHtml(a.name)}</strong>
               <div class="meta">tasks ${a.tasks_total} · completed ${a.tasks_completed} · rate ${a.completion_rate}</div></div>`
          )
          .join("") || '<div class="muted">No agents</div>';
      $("govExp").textContent = JSON.stringify(exp, null, 2);
      $("govAudit").textContent = JSON.stringify(
        { by_action: audit.by_action, recent: audit.recent },
        null,
        2
      );
    } catch (err) {
      $("govStats").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  const btnGov = $("btnRefreshGov");
  if (btnGov) btnGov.onclick = loadGovernance;


  async function applyAuthSession(body) {
    state.companyId = body.company_id;
    state.userId = body.user_id;
    state.accessToken = body.access_token || "";
    $("companyId").value = state.companyId;
    $("userId").value = state.userId;
    localStorage.setItem("ws_companyId", state.companyId);
    localStorage.setItem("ws_userId", state.userId);
    localStorage.setItem("ws_accessToken", state.accessToken);
    if (body.refresh_token) {
      localStorage.setItem("ws_refreshToken", body.refresh_token);
    }
    setConnected(true);
    await refreshInboxBadge();
    showView("workforce");
  }

  const btnLogin = $("btnLogin");
  if (btnLogin) {
    btnLogin.onclick = async () => {
      try {
        const body = await api("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            company_id: $("companyId").value.trim(),
            email: $("loginEmail").value.trim(),
            password: $("loginPassword").value,
          }),
          skipAuth: true,
        });
        $("setupLog").textContent = "Login OK for " + body.email;
        await applyAuthSession(body);
      } catch (err) {
        $("setupLog").textContent = "Login failed: " + err.message;
      }
    };
  }
  const btnRegister = $("btnRegister");
  if (btnRegister) {
    btnRegister.onclick = async () => {
      try {
        const body = await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({
            company_id: $("companyId").value.trim(),
            email: $("loginEmail").value.trim(),
            name: $("loginEmail").value.trim().split("@")[0] || "User",
            password: $("loginPassword").value,
            role: "member",
          }),
          skipAuth: true,
        });
        $("setupLog").textContent = "Registered " + body.email;
        await applyAuthSession(body);
      } catch (err) {
        $("setupLog").textContent = "Register failed: " + err.message;
      }
    };
  }

  if (state.companyId && state.userId) {
    $("btnConnect").click();
  }
})();


  // Job 20 — notification controls
  document.addEventListener("DOMContentLoaded", () => {
    const r = $("btnNotifRefresh");
    if (r) r.onclick = () => loadNotifications();
    const a = $("btnNotifReadAll");
    if (a)
      a.onclick = async () => {
        if (!state.companyId) return;
        await api(`/companies/${state.companyId}/notifications/read-all`, {
          method: "POST",
          body: "{}",
        });
        await loadNotifications();
        await refreshInboxBadge();
      };
  });
