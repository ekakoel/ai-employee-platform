(function (root) {
  const parseDate = raw => new Date(raw && !/(Z|[+-]\d{2}:\d{2})$/i.test(raw) ? `${raw}Z` : raw || 'invalid');
  function groupConversations(conversations, query = '') {
    const search = query.trim().toLowerCase(), dates = new Map();
    const ordered = [...conversations].sort((a, b) => (parseDate(b.updated_at || b.created_at).getTime() || 0) - (parseDate(a.updated_at || a.created_at).getTime() || 0));
    ordered.filter(item => !search || [item.title, item.user_name].join(' ').toLowerCase().includes(search)).forEach(item => {
      const date = parseDate(item.updated_at || item.created_at);
      const dateKey = Number.isNaN(date.getTime()) ? 'Unknown date' : new Intl.DateTimeFormat('en', { year: 'numeric', month: 'short', day: 'numeric' }).format(date);
      if (!dates.has(dateKey)) dates.set(dateKey, new Map());
      const users = dates.get(dateKey), userKey = item.user_id || 'unknown';
      if (!users.has(userKey)) users.set(userKey, { name: item.user_name || 'Unknown user', items: [] });
      users.get(userKey).items.push(item);
    });
    return [...dates].map(([date, users]) => ({ date, users: [...users.values()] }));
  }

  function cleanReply(content) {
    return String(content || '').replace(/\s*[_*]*\s*\(Chat mode:\s*no tools executed\.\s*Use\s*[\u201c\u201d"']?Create task[\u201c\u201d"']?\s*to run with policy & tools\.\)\s*[_*]*\s*$/, '').trimEnd();
  }
  function messageMarkup(message, esc, { agentName = '' } = {}) {
    const normalizedRole = { assistant: 'agent', user: 'human' }[message.role] || message.role;
    const role = ['human', 'agent', 'system'].includes(normalizedRole) ? normalizedRole : 'agent';
    const raw = message.created_at || '';
    const date = new Date(raw && !/(Z|[+-]\d{2}:\d{2})$/i.test(raw) ? `${raw}Z` : raw);
    const time = !Number.isNaN(date.getTime()) ? `<time datetime="${esc(date.toISOString())}">${esc(new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }).format(date))}</time>` : '';
    const sender = message.sender_name || (role === 'agent' ? agentName || 'Unknown sender' : role === 'system' ? 'System' : 'Unknown sender');
    const work = role === 'agent' && typeof message.work_result?.result === 'string' && message.work_result.result.trim() && message.work_result.status === 'completed' ? message.work_result : null;
    const content = role === 'agent' ? cleanReply(message.content) : message.content || '';
    return `<article class="bubble ${role}"><div class="who"><span>${esc(sender)}</span>${time}</div><div>${esc(content)}</div>${work ? `<div class="chat-message-results"><button class="link-btn" data-chat-result="${esc(work.id)}" title="View saved result">${esc(work.title || 'Saved result')}</button></div>` : ''}</article>`;
  }

  function create({ api, getSession, escapeHtml: esc, onAgentChanged, onTaskCreated, openTask, openResult }) {
    const $ = id => document.getElementById(id);
    let agents = [], conversations = [], messages = [], conversation = null;
    let generation = 0, busy = false, loadedAt = 0, sessionKey = '', pendingMessage = '', activeAgentId = '';
    const drafts = new Map();
    const key = () => `${getSession().companyId}/${getSession().userId}`;
    const path = () => `/companies/${getSession().companyId}`;
    const current = (request, session) => request === generation && session === key();
    function notice(text = '') { $('chatLog').textContent = text; $('chatLog').classList.toggle('hidden', !text); }
    function controls() {
      ['chatAgent', 'chatConversation', 'btnChatStart', 'btnRefreshChat', 'chatCreateTask'].forEach(id => { $(id).disabled = busy; });
      $('chatTaskMode').disabled = busy || !$('chatCreateTask').checked;
      $('btnChatSend').disabled = busy || !$('chatAgent').value || (conversation && conversation.status !== 'active') || !$('chatInput').value.trim();
      $('chatInput').disabled = busy || !$('chatAgent').value || (conversation && conversation.status !== 'active');
      $('chatTyping').classList.toggle('hidden', !pendingMessage);
      $('btnChatSend').textContent = pendingMessage ? 'Sending...' : 'Send';
      $('chatHistoryList').querySelectorAll?.('[data-chat-conversation]').forEach(button => { button.disabled = busy; });
    }
    function render(scroll = true) {
      const thread = $('chatThread');
      const nearBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
      const agentName = agents.find(agent => agent.id === (conversation?.agent_instance_id || activeAgentId))?.name || '';
      thread.innerHTML = messages.map(message => messageMarkup(message, esc, { agentName })).join('') + (pendingMessage ? `<article class="bubble human pending"><div class="who">${esc(getSession().userName || 'Unknown sender')} / Sending...</div><div>${esc(pendingMessage)}</div></article>` : '') || `<div class="empty">${$('chatAgent').value ? 'No messages yet.' : 'No AI employees available.'}</div>`;
      thread.querySelectorAll?.('[data-chat-result]').forEach(button => {
        button.onclick = () => {
          const work = messages.find(message => message.work_result?.id === button.dataset.chatResult)?.work_result;
          if (work && openResult) openResult(work);
        };
      });
      $('chatMeta').textContent = conversation?.title || 'New conversation';
      if (scroll || nearBottom) thread.scrollTop = thread.scrollHeight;
      controls();
    }
    function saveDraft() { drafts.set(conversation?.id || `new:${activeAgentId}`, $('chatInput').value); }
    function restoreDraft() { $('chatInput').value = drafts.get(conversation?.id || `new:${$('chatAgent').value}`) || ''; }
    function hideTask() { $('chatLinkedTask').classList.add('hidden'); $('chatLinkedTask').onclick = null; }
    function options() {
      $('chatConversation').innerHTML = '<option value="">New conversation</option>' + conversations.map(item => `<option value="${esc(item.id)}">${esc(item.title || 'Untitled conversation')}${item.status !== 'active' ? ' (closed)' : ''}</option>`).join('');
      $('chatConversation').value = conversation?.id || '';
      history();
    }
    function history() {
      const groups = groupConversations(conversations, $('chatHistorySearch').value);
      $('chatHistoryList').innerHTML = groups.map(group => `<section class="chat-history-date"><h4>${esc(group.date)}</h4>${group.users.map(user => `<div class="chat-history-user"><div class="chat-history-owner">${esc(user.name)}</div>${user.items.map(item => `<button class="chat-history-item ${item.id === conversation?.id ? 'active' : ''}" data-chat-conversation="${esc(item.id)}" aria-current="${item.id === conversation?.id ? 'true' : 'false'}" ${busy ? 'disabled' : ''}><span>${esc(item.title || 'Untitled conversation')}</span>${item.status !== 'active' ? '<small>Closed</small>' : ''}</button>`).join('')}</div>`).join('')}</section>`).join('') || '<div class="empty">No matching conversations.</div>';
      $('chatHistoryList').querySelectorAll?.('[data-chat-conversation]').forEach(button => { button.onclick = () => select(button.dataset.chatConversation); });
    }
    async function select(id) {
      if (busy) return;
      saveDraft();
      const previous = conversation;
      const next = conversations.find(item => item.id === id) || null;
      const request = ++generation, session = key();
      busy = true; notice(); controls();
      try {
        const rows = next ? await api(`${path()}/conversations/${next.id}/messages`) : [];
        if (!current(request, session)) return;
        conversation = next; messages = rows; hideTask(); restoreDraft(); render();
      } catch (error) {
        if (current(request, session)) { conversation = previous; notice(error.message); }
      } finally {
        if (current(request, session)) { busy = false; options(); controls(); }
      }
    }
    async function load(force = false) {
      if (!getSession().companyId || !getSession().userId || busy) return;
      if (sessionKey !== key()) reset();
      sessionKey = key();
      if (!force && loadedAt && Date.now() - loadedAt < 30000) { render(false); return; }
      loadedAt = 0;
      saveDraft();
      const request = ++generation, session = key(), selectedAgent = $('chatAgent').value;
      busy = true; notice(); controls();
      try {
        const availableAgents = await api(`${path()}/agents`);
        if (!current(request, session)) return;
        agents = availableAgents;
        $('chatAgent').innerHTML = agents.map(agent => `<option value="${esc(agent.id)}">${esc(agent.name)}</option>`).join('');
        $('chatAgent').value = agents.some(agent => agent.id === selectedAgent) ? selectedAgent : agents[0]?.id || '';
        const agentId = $('chatAgent').value;
        activeAgentId = agentId;
        const rows = agentId ? await api(`${path()}/conversations?agent_instance_id=${encodeURIComponent(agentId)}`) : [];
        if (!current(request, session)) return;
        conversations = rows;
        const next = rows.find(item => item.id === conversation?.id) || rows[0] || null;
        const transcript = next ? await api(`${path()}/conversations/${next.id}/messages`) : [];
        if (!current(request, session)) return;
        conversation = next; messages = transcript; loadedAt = Date.now();
        options(); restoreDraft(); hideTask(); render(); onAgentChanged();
      } catch (error) {
        if (current(request, session)) {
          if (conversation && conversation.agent_instance_id !== $('chatAgent').value) {
            conversation = null; messages = []; conversations = []; options(); restoreDraft(); hideTask(); render();
          }
          notice(error.message);
        }
      }
      finally { if (current(request, session)) { busy = false; controls(); } }
    }
    async function send() {
      const content = $('chatInput').value.trim();
      if (busy || !content || !$('chatAgent').value || (conversation && conversation.status !== 'active')) return;
      const request = ++generation, session = key(), base = path();
      const createTask = $('chatCreateTask').checked, mode = $('chatTaskMode').value;
      busy = true; pendingMessage = content; notice(); render();
      try {
        if (!conversation) {
          const created = await api(`${base}/conversations`, { method: 'POST', skipSidebarRefresh: true, body: JSON.stringify({ agent_instance_id: $('chatAgent').value, title: content.slice(0, 80) }) });
          if (!current(request, session)) return;
          conversation = created; conversations.unshift(created); options();
        }
        const result = await api(`${base}/conversations/${conversation.id}/messages`, {
          method: 'POST', skipSidebarRefresh: true,
          body: JSON.stringify({ content, create_task: createTask, task_mode: mode }),
        });
        if (!current(request, session)) return;
        messages.push(result.human, result.agent);
        messages = messages.slice(-200);
        pendingMessage = ''; $('chatInput').value = ''; drafts.delete(conversation.id); drafts.delete(`new:${$('chatAgent').value}`);
        conversation.updated_at = result.agent.created_at;
        conversations = [conversation, ...conversations.filter(item => item.id !== conversation.id)]; options();
        if (result.task_id) {
          $('chatLinkedTask').classList.remove('hidden');
          $('chatLinkedTask').onclick = () => openTask(result.task_id);
          onTaskCreated();
        }
        loadedAt = Date.now(); render();
      } catch (error) {
        if (current(request, session)) {
          notice(`${error.message} Your draft has been kept. Refresh the conversation before retrying if delivery is uncertain.`);
          pendingMessage = ''; saveDraft(); render(false);
        }
      } finally { if (current(request, session)) { busy = false; pendingMessage = ''; controls(); $('chatInput').focus(); } }
    }
    function reset() {
      generation++; busy = false; loadedAt = 0; sessionKey = ''; pendingMessage = ''; activeAgentId = '';
      agents = []; conversations = []; messages = []; conversation = null; drafts.clear();
      $('chatHistorySearch').value = '';
      $('chatAgent').innerHTML = ''; $('chatInput').value = ''; $('chatCreateTask').checked = false;
      options(); hideTask(); notice(); render();
    }
    $('btnChatSend').onclick = send;
    $('btnChatStart').onclick = () => select('');
    $('btnRefreshChat').onclick = () => load(true);
    $('chatConversation').onchange = () => select($('chatConversation').value);
    $('chatHistorySearch').oninput = history;
    $('chatAgent').onchange = () => {
      saveDraft(); activeAgentId = $('chatAgent').value; conversation = null; conversations = []; messages = []; options(); restoreDraft(); hideTask(); render();
      onAgentChanged(); load(true);
    };
    $('chatCreateTask').onchange = controls;
    $('chatInput').oninput = () => { saveDraft(); controls(); };
    $('chatInput').onkeydown = event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(); }
    };
    return { load, reset };
  }
  const exports = { create, messageMarkup, groupConversations, cleanReply };
  if (typeof module !== 'undefined' && module.exports) module.exports = exports;
  else root.WorkspaceChat = exports;
})(globalThis);
