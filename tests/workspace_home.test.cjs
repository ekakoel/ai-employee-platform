const test = require('node:test');
const assert = require('node:assert/strict');
const { summarize, create } = require('../app/static/workspace/home.js');

const tasks = [
  { id: 'pending', title: 'Pending', status: 'pending', agent_instance_id: 'agent', created_at: '2026-10-01T00:00:00Z' },
  { id: 'running', title: 'Running', status: 'running', agent_instance_id: 'agent', created_at: '2026-10-02T00:00:00Z' },
  { id: 'blocked', title: 'Blocked', status: 'waiting_approval', agent_instance_id: 'agent', created_at: '2026-10-03T00:00:00Z' },
  { id: 'done', title: 'Done', status: 'completed', result: 'Report', agent_instance_id: 'agent', created_at: '2026-10-04T00:00:00Z' },
  { id: 'failed', title: 'Failed', status: 'failed', agent_instance_id: 'agent', created_at: '2026-10-05T00:00:00Z' },
];
const approvals = [{ id: 'approval', task_id: 'blocked', status: 'pending', action: 'Send', reason: 'Review email' }];
const agents = [{ id: 'agent', name: 'Analyst', status: 'active' }, { id: 'inactive', name: 'Other', status: 'inactive' }];

test('summary distinguishes work in progress, results, approvals, and failures', () => {
  const summary = summarize({ tasks, approvals, agents });
  assert.equal(summary.open, 3);
  assert.equal(summary.results, 1);
  assert.equal(summary.active, 1);
  assert.equal(summary.pendingApprovals, 1);
  assert.equal(summary.counts.failed, 1);
  assert.equal(summary.recent[0].id, 'failed');
});

test('approvals precede failures and unstarted work without duplicating blocked tasks', () => {
  const summary = summarize({ tasks, approvals, agents });
  assert.deepEqual(summary.attention.map(item => item.id), ['approval', 'failed', 'pending']);
  assert.equal(summary.attention[0].title, 'Blocked');
});

test('unavailable data is not treated as an empty workspace', () => {
  assert.equal(summarize({ tasks: null, agents: null, approvals: null }).open, null);
  assert.equal(summarize({ tasks: [], agents: [], approvals: [] }).open, 0);
  assert.equal(summarize({ tasks, agents, approvals: null }).pendingApprovals, null);
});

function fakeDocument() {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, {
        textContent: '', innerHTML: '', disabled: false, querySelectorAll: () => [],
        classList: { add: name => classes.add(name), toggle: (name, value) => value ? classes.add(name) : classes.delete(name), contains: name => classes.has(name) },
      });
    }
    return elements.get(id);
  };
  global.document = { getElementById: get };
  return get;
}
const esc = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

test('home remains informative when approvals are forbidden and escapes task titles', async () => {
  const get = fakeDocument();
  const dashboard = create({
    getSession: () => ({ companyId: 'one', userId: 'member', userName: 'Member' }),
    api: async path => {
      if (path.endsWith('/approvals')) throw new Error('Forbidden');
      if (path.endsWith('/agents')) return agents;
      return [{ ...tasks[0], title: '<img src=x onerror=alert(1)>' }];
    }, escapeHtml: esc, navigate() {}, openTask() {}, openResult() {},
  });
  await dashboard.load();
  assert.match(get('homeStats').innerHTML, /Unavailable/);
  assert.match(get('homeRecent').innerHTML, /&lt;img/);
  assert.doesNotMatch(get('homeRecent').innerHTML, /<img/);
  assert.match(get('homeNotice').textContent, /approvals/);
  assert.equal(get('homeNotice').classList.contains('hidden'), false);
  assert.equal(get('btnRefreshHome').disabled, false);
  assert.equal(get('homeGreeting').textContent, 'Hello, Member');
  delete global.document;
});

test('late requests cannot repopulate the dashboard after logout', async () => {
  const get = fakeDocument();
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const dashboard = create({
    getSession: () => ({ companyId: 'one', userId: 'member' }),
    api: () => pending, escapeHtml: esc, navigate() {}, openTask() {}, openResult() {},
  });
  const loading = dashboard.load();
  dashboard.reset();
  finish([]);
  await loading;
  assert.equal(get('homeStats').textContent, '');
  assert.equal(get('homeUpdated').textContent, '');
  assert.equal(get('btnRefreshHome').disabled, false);
  delete global.document;
});
