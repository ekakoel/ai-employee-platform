(function (root) {
  function parseResult(value) {
    try { return JSON.parse(value); } catch (_) { return value; }
  }

  function extractArtifacts(value) {
    const artifacts = [];
    if (!value || typeof value !== "object") return artifacts;
    const tools = Array.isArray(value.tool_results)
      ? value.tool_results
      : Array.isArray(value.tools)
        ? value.tools
        : [];
    for (const item of tools) {
      const name = item.tool || item.name || "";
      const res = item.result != null ? item.result : item.output != null ? item.output : item;
      if (name === "search_availability") {
        const opts = (res && res.options) || [];
        artifacts.push({
          type: "availability",
          title: "Availability",
          summary: `${res?.count ?? opts.length} option(s)` + (opts[0]?.location ? ` · ${opts[0].location}` : ""),
          options: opts,
          data: res,
        });
      } else if (name === "draft_quotation") {
        const draft = res?.draft || res?.text || "";
        artifacts.push({
          type: "quotation",
          title: "Quotation",
          summary: draft ? String(draft).slice(0, 160) : "Quotation draft",
          text: draft,
          data: res,
        });
      } else if (name === "create_reservation" || name === "get_reservation") {
        artifacts.push({
          type: "reservation",
          title: "Reservation",
          summary: res?.confirmation || res?.id || "Reservation record",
          data: res,
        });
      } else if (name) {
        artifacts.push({
          type: "tool",
          title: name,
          summary: typeof res === "string" ? res.slice(0, 120) : JSON.stringify(res || {}).slice(0, 120),
          data: res,
        });
      }
    }
    if (value.recommendation && !artifacts.some((a) => a.type === "analysis")) {
      artifacts.push({
        type: "analysis",
        title: "Recommendation",
        summary: String(value.recommendation).slice(0, 180),
        text: String(value.recommendation),
      });
    }
    return artifacts;
  }

  function describe(task) {
    const value = parseResult(task.result);
    const structured = value !== null && typeof value === "object";
    const artifacts = structured ? extractArtifacts(value) : [];
    const quotation = artifacts.find((a) => a.type === "quotation");
    const availability = artifacts.find((a) => a.type === "availability");
    let kind = "text";
    if (quotation) kind = "quotation";
    else if (availability) kind = "availability";
    else if (artifacts.some((a) => a.type === "reservation")) kind = "reservation";
    else if (structured && value.recommendation) kind = "analysis";
    else if (structured) kind = "structured";
    const documentText = quotation?.text
      || artifacts.filter((a) => a.text).map((a) => a.text).join("\n\n")
      || "";
    const summary =
      quotation?.summary ||
      availability?.summary ||
      documentText ||
      (structured
        ? String(value.recommendation || value.summary || JSON.stringify(value)).slice(0, 240)
        : String(value ?? ""));
    return {
      ...task,
      kind,
      summary,
      documentText,
      artifacts,
      value,
    };
  }

  function filterResults(items, filters, now = Date.now()) {
    const query = filters.query.toLowerCase().trim();
    const visible = new Set((filters.mainTitles || []).map((title) => title.trim().replace(/\s+/g, " ").toLowerCase()));
    const mainText = String(filters.mainText || "").trim().replace(/\s+/g, " ").toLowerCase();
    return items.filter((item) =>
      !visible.has(String(item.title || "").trim().replace(/\s+/g, " ").toLowerCase()) &&
      !(mainText && item.summary && mainText.includes(item.summary.trim().replace(/\s+/g, " ").toLowerCase())) &&
      (!filters.agent || item.agent_instance_id === filters.agent) &&
      (!filters.kind || item.kind === filters.kind) &&
      (!filters.days || Date.parse(item.created_at) >= now - Number(filters.days) * 86400000) &&
      (!filters.context || item.id === filters.context) &&
      (filters.tab !== "pinned" || filters.pins.has(item.id)) &&
      (!query || [item.title, item.result, item.agentName].join(" ").toLowerCase().includes(query))
    ).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  }

  function create({ getSession, api, escapeHtml: esc, getMainTitles = () => [], getMainText = () => "", openPreview, openTask, revise }) {
    const $ = (id) => document.getElementById(id);
    let items = [], pins = new Set(), tab = "recent", context = "", generation = 0;
    let selectedTaskId = "";
    const parsedTaskDate = (task) => task.created_at && !task.created_at.endsWith("Z") && !/[+-]\d{2}:\d{2}$/.test(task.created_at)
      ? task.created_at + "Z" : task.created_at;
    const typeNames = { analysis: "Analysis", text: "Text", structured: "Structured data", quotation: "Quotation", availability: "Availability", reservation: "Reservation" };
    const statusNames = { completed: "Completed", pending: "Pending", waiting_approval: "Awaiting approval", failed: "Failed" };
    const date = (value) => new Date(value).toLocaleString("en-US");
    const message = (text) => { $("outputContent").innerHTML = `<div class="empty">${esc(text)}</div>`; };

    function render() {
      const mainTitles = getMainTitles();
      const selectedVisible = items.some((item) => item.id === context && mainTitles.some((title) => title.trim().toLowerCase() === item.title.trim().toLowerCase()));
      const filtered = filterResults(items, {
        query: $("resultSearch").value, agent: $("resultAgent").value,
        kind: $("resultType").value, days: $("resultPeriod").value, tab, pins, context: selectedVisible ? "" : context, mainTitles, mainText: getMainText(),
      });
      const shown = tab === "recent" ? filtered.slice(0, 20) : filtered;
      $("resultCount").textContent = `${shown.length} / ${filtered.length} results`;
      $("outputContent").innerHTML = `${context ? '<button class="link-btn" id="btnAllResults">All results</button>' : ""}` +
        shown.map((item) => {
          const tags = (item.artifacts || []).map((a) => `<span class="tag">${esc(a.type)}</span>`).join("");
          return `<article class="result-item">
          <button class="result-open" data-result-id="${esc(item.id)}">
            <span class="result-kind">${esc(typeNames[item.kind] || item.kind)}${pins.has(item.id) ? " / Pinned" : ""}</span>
            <strong>${esc(item.title)}</strong>
            <span class="result-summary">${esc((item.summary || "").slice(0, 180))}</span>
            <span class="meta">${esc(item.agentName)} / ${esc(date(item.created_at))}</span>
            <span class="meta">Task: ${esc(statusNames[item.status] || item.status)}</span>
            ${tags ? `<span class="result-tags">${tags}</span>` : ""}
          </button>
        </article>`;
        }).join("") + (!shown.length ? '<div class="empty">No matching results.</div>' : "");
      $("btnAllResults")?.addEventListener("click", () => { context = ""; render(); });
      $("outputContent").querySelectorAll("[data-result-id]").forEach((button) => {
        button.onclick = () => preview(items.find((item) => item.id === button.dataset.resultId));
      });
    }

    async function refresh() {
      const session = { ...getSession() };
      if (!session.companyId || !session.userId) return;
      const request = ++generation;
      $("btnRefreshResults").disabled = true;
      try {
        const [tasks, agents, savedPins] = await Promise.all([
          api(`/companies/${session.companyId}/tasks`),
          api(`/companies/${session.companyId}/agents`),
          api(`/companies/${session.companyId}/result-pins`),
        ]);
        if (request !== generation || session.companyId !== getSession().companyId || session.userId !== getSession().userId) return;
        const names = new Map(agents.map((agent) => [agent.id, agent.name]));
        items = tasks.filter((task) => task.result && task.result.trim()).map((task) => ({
          ...describe(task), created_at: parsedTaskDate(task), agentName: names.get(task.agent_instance_id) || "AI Employee",
        }));
        pins = new Set(savedPins);
        const selected = $("resultAgent").value;
        $("resultAgent").innerHTML = '<option value="">All agents</option>' + agents.map((agent) =>
          `<option value="${esc(agent.id)}">${esc(agent.name)}</option>`).join("");
        $("resultAgent").value = names.has(selected) ? selected : "";
        render();
      } catch (error) {
        if (request === generation) { items = []; $("resultCount").textContent = ""; message(error.message); }
      } finally {
        if (request === generation) $("btnRefreshResults").disabled = false;
      }
    }

    function renderArtifactCards(artifacts) {
      if (!artifacts || !artifacts.length) return "";
      return `<div class="artifact-list">` + artifacts.map((a) => {
        if (a.type === "availability" && Array.isArray(a.options) && a.options.length) {
          const rows = a.options.map((o) =>
            `<tr><td>${esc(o.location || "")}</td><td>${esc(o.room_type || "")}</td>` +
            `<td>${esc(String(o.capacity ?? ""))}</td><td>${esc(String(o.rate ?? ""))} ${esc(o.currency || "")}</td>` +
            `<td><code>${esc(o.id || "")}</code></td></tr>`
          ).join("");
          return `<section class="artifact-card"><h3>${esc(a.title)}</h3><p class="muted">${esc(a.summary || "")}</p>` +
            `<table class="artifact-table"><thead><tr><th>Location</th><th>Room</th><th>Cap</th><th>Rate</th><th>availability_id</th></tr></thead>` +
            `<tbody>${rows}</tbody></table></section>`;
        }
        if (a.type === "quotation" && a.text) {
          return `<section class="artifact-card"><h3>${esc(a.title)}</h3><pre class="result-document">${esc(a.text)}</pre></section>`;
        }
        if (a.type === "reservation") {
          return `<section class="artifact-card"><h3>${esc(a.title)}</h3><pre class="result-document">${esc(JSON.stringify(a.data || {}, null, 2))}</pre></section>`;
        }
        if (a.type === "analysis" && a.text) {
          return `<section class="artifact-card"><h3>${esc(a.title)}</h3><p>${esc(a.text)}</p></section>`;
        }
        return `<section class="artifact-card"><h3>${esc(a.title || a.type)}</h3><p class="muted">${esc(a.summary || "")}</p></section>`;
      }).join("") + `</div>`;
    }

    function preview(item) {
      if (!item) return;
      selectedTaskId = item.id;
      const details = typeof item.value === "object" && item.value !== null ? JSON.stringify(item.value, null, 2) : String(item.value);
      const content = item.documentText || details;
      const textDownload = Boolean(item.documentText) || item.kind === "text" || item.kind === "quotation";
      const cards = renderArtifactCards(item.artifacts || []);
      $("resultPreview").innerHTML = `<h2>${esc(item.title)}</h2>
        <p class="muted">${esc(item.agentName)} / ${esc(date(item.created_at))} / Task: ${esc(item.status)} / Type: ${esc(typeNames[item.kind] || item.kind)}</p>
        <div class="row result-actions">
          <button id="btnResultTask" class="secondary">Open source task</button>
          <button id="btnResultDownload" class="secondary">Download ${textDownload ? "text" : "JSON"}</button>
          <button id="btnResultPin" class="secondary" aria-pressed="${pins.has(item.id)}">${pins.has(item.id) ? "Unpin" : "Pin"}</button>
          <button id="btnResultRevise" class="primary">Request revision</button>
        </div>
        <p id="resultActionStatus" role="status"></p>
        ${cards || `<pre class="result-document">${esc(content)}</pre>`}
        <details ${cards ? "" : "open"}><summary>Raw execution payload</summary><pre class="result-document">${esc(details)}</pre></details>`;
      $("btnResultTask").onclick = () => openTask(item);
      $("btnResultRevise").onclick = () => revise(item);
      $("btnResultDownload").onclick = () => {
        const blob = new Blob([content], { type: textDownload ? "text/plain;charset=utf-8" : "application/json" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${item.title.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80) || "result"}.${textDownload ? "txt" : "json"}`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      };
      $("btnResultPin").onclick = async () => {
        const request = generation;
        const button = $("btnResultPin");
        button.disabled = true;
        try {
          await api(`/companies/${getSession().companyId}/tasks/${item.id}/result-pin`, { method: pins.has(item.id) ? "DELETE" : "PUT" });
          if (request !== generation) return;
          if (pins.has(item.id)) pins.delete(item.id); else pins.add(item.id);
          render(); preview(item);
        } catch (error) { if (request === generation) { $("resultActionStatus").textContent = error.message; button.disabled = false; } }
      };
      openPreview();
    }

    function reset() {
      selectedTaskId = "";
      generation++; items = []; pins = new Set(); context = ""; tab = "recent";
      $("resultSearch").value = ""; $("resultAgent").value = ""; $("resultType").value = ""; $("resultPeriod").value = "";
      $("resultPreview").textContent = "";
      $("btnRefreshResults").disabled = false;
      $("resultCount").textContent = "";
      message("No results loaded.");
      document.querySelectorAll("[data-result-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.resultTab === tab);
        button.setAttribute("aria-selected", String(button.dataset.resultTab === tab));
      });
    }

    $("btnRefreshResults").onclick = refresh;
    $("resultSearch").oninput = render;
    ["resultAgent", "resultType", "resultPeriod"].forEach((id) => { $(id).onchange = render; });
    document.querySelectorAll("[data-result-tab]").forEach((button) => {
      button.onclick = () => {
        tab = button.dataset.resultTab; context = "";
        document.querySelectorAll("[data-result-tab]").forEach((other) => {
          other.classList.toggle("active", other === button);
          other.setAttribute("aria-selected", String(other === button));
        });
        render();
      };
    });
    reset();
    return { refresh, reset, reconcile: render, getSelectedTaskId: () => selectedTaskId, showAll() {
      context = ""; tab = "all";
      $("resultSearch").value = ""; $("resultAgent").value = ""; $("resultType").value = ""; $("resultPeriod").value = "";
      document.querySelectorAll("[data-result-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.resultTab === tab);
        button.setAttribute("aria-selected", String(button.dataset.resultTab === tab));
      });
      render(); refresh(); $("resultSearch").focus();
    }, select(task) {
      const previous = items.find((candidate) => candidate.id === task.id);
      const item = { ...describe(task), created_at: parsedTaskDate(task), agentName: previous?.agentName || "AI Employee" };
      items = [...items.filter((candidate) => candidate.id !== task.id), item];
      $("resultSearch").value = ""; $("resultAgent").value = ""; $("resultType").value = ""; $("resultPeriod").value = "";
      tab = "recent";
      document.querySelectorAll("[data-result-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.resultTab === tab);
        button.setAttribute("aria-selected", String(button.dataset.resultTab === tab));
      });
      context = task.id; render(); preview(item); refresh();
    } };
  }

  const exports = { describe, filterResults, create };
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  else root.WorkspaceResults = exports;
})(globalThis);
