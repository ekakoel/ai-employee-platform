const test = require('node:test');
const assert = require('node:assert/strict');
const { create, messageMarkup, groupConversations, cleanReply } = require('../app/static/workspace/chat.js');
const esc = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function fixture(override) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, { value: '', checked: false, innerHTML: '', textContent: '', disabled: false,
        scrollHeight: 500, scrollTop: 0, clientHeight: 300, focus() {},
        classList: { add: name => classes.add(name), toggle: (name, yes) => yes ? classes.add(name) : classes.delete(name), remove: name => classes.delete(name), contains: name => classes.has(name) },
      });
    }
    return elements.get(id);
  };
  global.document = { getElementById: get };
  const calls = [], session = { companyId: 'one', userId: 'alice' };
  let tasksCreated = 0;
  const api = async (url, options = {}) => {
    calls.push([url, options]);
    if (override) { const result = override(url, options); if (result !== undefined) return result; }
    if (url.endsWith('/agents')) return [{ id: 'a', name: 'Analyst' }, { id: 'b', name: 'Researcher' }];
    if (url.includes('/conversations?')) return url.includes('=b') ? [] : [{ id: 'c', title: 'Budget', status: 'active', agent_instance_id: 'a' }];
    if (options.method === 'POST' && url.endsWith('/conversations')) return { id: 'new', title: 'New chat', status: 'active', agent_instance_id: 'a' };
    if (options.method === 'POST') return { human: { id: 'human', role: 'human', content: JSON.parse(options.body).content }, agent: { id: 'agent', role: 'agent', content: 'Reply' }, task_id: 'task' };
    return [{ id: 'previous', role: 'human', content: 'Earlier question' }];
  };
  const chat = create({ api, getSession: () => session, escapeHtml: esc, onAgentChanged() {}, onTaskCreated: () => tasksCreated++, openTask() {} });
  return { chat, get, calls, session, tasksCreated: () => tasksCreated };
}

test('messages escape content and roles; UTC timestamps display local time', () => {
  const markup = messageMarkup({ role: '<script>', content: '<img onerror="evil()">', created_at: '2026-10-09T01:02:03' }, esc);
  assert.match(markup, /class="bubble agent"/);
  assert.match(markup, /&lt;img/);
  assert.doesNotMatch(markup, /<img|<script>/);
  assert.match(markup, /datetime="2026-10-09T01:02:03.000Z"/);
});

test('recorded sender names replace generic roles and results appear only when available', () => {
  const saved = { id: 'report', title: '<Revenue report>', result: 'Saved report', status: 'completed' };
  const markup = messageMarkup({ role: 'agent', sender_name: '<Analyst>', content: 'Done', work_result: saved }, esc);
  assert.match(markup, /&lt;Analyst&gt;/);
  assert.match(markup, /data-chat-result="report"/);
  assert.match(markup, /&lt;Revenue report&gt;/);
  assert.doesNotMatch(markup, />AI employee</);
  assert.match(messageMarkup({ role: 'human', sender_name: 'Alice' }, esc), />Alice</);
  assert.match(messageMarkup({ role: 'human' }, esc), /Unknown sender/);
  assert.doesNotMatch(messageMarkup({ role: 'agent', work_result: { ...saved, result: '' } }, esc), /data-chat-result/);
  assert.doesNotMatch(messageMarkup({ role: 'agent', work_result: { ...saved, status: 'pending' } }, esc), /data-chat-result/);
});

test('legacy replies use the assigned agent and remove all footer wrappers without inventing outputs', () => {
  const sentence = '(Chat mode: no tools executed. Use \u201cCreate task\u201d to run with policy & tools.)';
  for (const wrapper of ['', '_', '*', '**']) {
    const content = `Quotation draft\n\n${wrapper}${sentence}${wrapper}`;
    assert.equal(cleanReply(content), 'Quotation draft');
    const markup = messageMarkup({ role: 'agent', content }, esc, { agentName: 'Reservation (Demo)' });
    assert.match(markup, /Reservation \(Demo\)/);
    assert.doesNotMatch(markup, /Unknown sender|Chat mode|data-chat-result/);
  }
  assert.equal(cleanReply('Reply\n\n*(Chat mode: no tools executed. Use "Create task" to run with policy & tools.)*'), 'Reply');
  assert.match(messageMarkup({ role: 'human', content: sentence }, esc, { agentName: 'Reservation (Demo)' }), /Chat mode/);
});

test('history groups by local date then recorded user identity and supports search', () => {
  const rows = [
    { id: 'old', title: 'Older work', user_id: 'a', user_name: 'Alice', updated_at: '2026-10-08T12:00:00Z' },
    { id: 'new-a', title: 'Revenue', user_id: 'a', user_name: 'Alice', updated_at: '2026-10-09T12:00:00Z' },
    { id: 'new-b', title: 'Research', user_id: 'b', user_name: 'Bob', updated_at: '2026-10-09T12:00:00Z' },
  ];
  const grouped = groupConversations(rows);
  assert.equal(grouped.length, 2);
  assert.deepEqual(grouped[0].users.map(user => user.name), ['Alice', 'Bob']);
  assert.equal(grouped[0].users[0].items[0].id, 'new-a');
  assert.equal(groupConversations(rows, 'BOB')[0].users.length, 1);
  assert.equal(groupConversations(rows, 'revenue')[0].users[0].items[0].id, 'new-a');
  assert.equal(groupConversations([{ id: 'missing' }])[0].date, 'Unknown date');
});

test('loads saved conversations, caches revisits, and sends without reloading transcript', async () => {
  const f = fixture();
  await f.chat.load();
  assert.equal(f.get('chatMeta').textContent, 'Budget');
  assert.match(f.get('chatThread').innerHTML, /Earlier question/);
  const count = f.calls.length;
  await f.chat.load();
  assert.equal(f.calls.length, count);
  f.get('chatInput').value = 'Follow up'; f.get('chatCreateTask').checked = true;
  await f.get('btnChatSend').onclick();
  assert.equal(f.calls.length, count + 1);
  assert.match(f.get('chatThread').innerHTML, /Reply/);
  assert.match(f.get('chatThread').innerHTML, /Analyst/);
  assert.equal(f.get('chatInput').value, '');
  assert.equal(f.tasksCreated(), 1);
  assert.equal(f.get('chatAgent').disabled, false);
  delete global.document;
});

test('new conversation is created lazily and drafts survive conversation switching', async () => {
  const f = fixture(); await f.chat.load();
  f.get('chatInput').value = 'Old draft';
  await f.get('btnChatStart').onclick();
  assert.equal(f.calls.filter(([, opts]) => opts.method === 'POST').length, 0);
  f.get('chatInput').value = 'New draft';
  f.get('chatConversation').value = 'c'; await f.get('chatConversation').onchange();
  assert.equal(f.get('chatInput').value, 'Old draft');
  await f.get('btnChatStart').onclick();
  assert.equal(f.get('chatInput').value, 'New draft');
  await f.get('btnChatSend').onclick();
  assert.equal(f.calls.filter(([, opts]) => opts.method === 'POST').length, 2);
  delete global.document;
});

test('failed delivery retains draft and clears the optimistic bubble', async () => {
  const f = fixture((url, opts) => opts.method === 'POST' ? Promise.reject(new Error('Offline')) : undefined);
  await f.chat.load(); f.get('chatInput').value = 'Keep me';
  await f.get('btnChatSend').onclick();
  assert.equal(f.get('chatInput').value, 'Keep me');
  assert.match(f.get('chatLog').textContent, /Offline.*draft has been kept/);
  assert.doesNotMatch(f.get('chatThread').innerHTML, /Sending|Keep me/);
  assert.equal(f.get('btnChatSend').disabled, false);
  delete global.document;
});

test('duplicate sends are blocked and late replies cannot repopulate after logout', async () => {
  let resolve;
  const f = fixture((url, opts) => opts.method === 'POST' ? new Promise(done => { resolve = done; }) : undefined);
  await f.chat.load(); f.get('chatInput').value = 'Question';
  const pending = f.get('btnChatSend').onclick();
  await f.get('btnChatSend').onclick();
  assert.equal(f.calls.filter(([, opts]) => opts.method === 'POST').length, 1);
  assert.equal(f.get('chatAgent').disabled, true);
  f.chat.reset(); f.session.userId = '';
  resolve({ human: { role: 'human', content: 'Private' }, agent: { role: 'agent', content: 'Secret' } });
  await pending;
  assert.doesNotMatch(f.get('chatThread').innerHTML, /Private|Secret|Question/);
  assert.equal(f.get('chatInput').value, '');
  delete global.document;
});

test('agent switching refreshes only that agent history; task mode follows checkbox', async () => {
  const f = fixture(); await f.chat.load();
  f.get('chatAgent').value = 'b'; f.get('chatAgent').onchange();
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(f.calls.some(([url]) => url.endsWith('agent_instance_id=b')));
  assert.equal(f.get('chatMeta').textContent, 'New conversation');
  f.get('chatCreateTask').checked = false; f.get('chatCreateTask').onchange();
  assert.equal(f.get('chatTaskMode').disabled, true);
  f.get('chatCreateTask').checked = true; f.get('chatCreateTask').onchange();
  assert.equal(f.get('chatTaskMode').disabled, false);
  delete global.document;
});

test('late initial loads cannot restore another session data', async () => {
  let resolve;
  const f = fixture(url => url.endsWith('/agents') ? new Promise(done => { resolve = done; }) : undefined);
  const pending = f.chat.load();
  f.chat.reset(); f.session.userId = 'different-user';
  resolve([{ id: 'private', name: 'Private agent' }]);
  await pending;
  assert.doesNotMatch(f.get('chatAgent').innerHTML, /Private/);
  assert.equal(f.calls.length, 1);
  delete global.document;
});

test('closed conversations and no-agent workspaces cannot submit messages', async () => {
  const closed = fixture(url => url.includes('/conversations?') ? [{ id: 'closed', title: 'Archived', status: 'closed', agent_instance_id: 'a' }] : undefined);
  await closed.chat.load(); closed.get('chatInput').value = 'Do not send';
  await closed.get('btnChatSend').onclick();
  assert.equal(closed.get('chatInput').disabled, true);
  assert.equal(closed.calls.filter(([, opts]) => opts.method === 'POST').length, 0);
  const empty = fixture(url => url.endsWith('/agents') ? [] : undefined);
  await empty.chat.load();
  assert.match(empty.get('chatThread').innerHTML, /No AI employees available/);
  assert.equal(empty.get('btnChatSend').disabled, true);
  delete global.document;
});
