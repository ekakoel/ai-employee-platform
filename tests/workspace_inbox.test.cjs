const test = require('node:test');
const assert = require('node:assert/strict');
const { buildQueue, filterQueue, attributionMarkup, create } = require('../app/static/workspace/inbox.js');
const { buildContext } = require('../app/static/workspace/sidebar.js');

const tasks = [
  { id: 'blocked', title: 'Refund', status: 'waiting_approval', agent_instance_id: 'a' },
  { id: 'child', title: 'Handoff child', status: 'pending', agent_instance_id: 'a' },
  { id: 'ready', title: 'Sales report', instruction: 'Review revenue', status: 'pending', mode: 'consult', agent_instance_id: 'a' },
  { id: 'running', title: 'Processing', status: 'running', agent_instance_id: 'a' },
  { id: 'failed', title: 'Retry', status: 'failed', agent_instance_id: 'a' },
  { id: 'done', title: 'Finished', status: 'completed', agent_instance_id: 'a' },
];
const data = {
  tasks, approvals: [{ id: 'approval', task_id: 'blocked', agent_instance_id: 'a', status: 'pending', action: 'Refund', reason: 'Above limit' }],
  delegations: [{ id: 'handoff', child_task_id: 'child', status: 'accepted', title: 'Research handoff', source_agent_instance_id: 'a', target_agent_instance_id: 'b' }],
  agents: [{ id: 'a', name: 'Analyst' }, { id: 'b', name: 'Researcher' }],
};

test('queue deduplicates linked approvals and child tasks, and excludes completed work', () => {
  const queue = buildQueue(data);
  assert.deepEqual(queue.map(item => item.id), ['approval', 'failed', 'handoff', 'ready', 'running']);
  assert.equal(queue[0].action, 'Review approval');
  assert.equal(queue.find(item => item.id === 'handoff').agent, 'Analyst to Researcher');
});

test('action and progress views, type filters, and search combine', () => {
  const queue = buildQueue(data);
  assert.equal(filterQueue(queue, { tab: 'progress', type: '', query: '' }).length, 1);
  const ready = filterQueue(queue, { tab: 'action', type: 'task', query: 'REVENUE' });
  assert.equal(ready.length, 1);
  assert.equal(ready[0].action, 'Run consultation');
  assert.equal(filterQueue(queue, { tab: 'all', type: 'approval', query: 'Analyst' }).length, 1);
});

test('an accepted handoff with a running child belongs in progress', () => {
  const queue = buildQueue({ ...data, tasks: tasks.map(task => task.id === 'child' ? { ...task, status: 'running' } : task) });
  assert.equal(queue.find(item => item.id === 'handoff').group, 'progress');
  assert.equal(queue.some(item => item.id === 'child'), false);
});

test('Inbox guidance is concise and does not mirror queue data', () => {
  const context = buildContext('inbox', { policies: [], knowledge: [] });
  assert.match(context.guide.summary, /shared queue/);
  assert.equal(context.guide.steps.length, 3);
  assert.deepEqual(context.metrics, []);
  assert.ok(context.sections.every(section => section.entries.length === 0));
});

test('watermark displays persisted actor, action and timezone without inventing history', () => {
  const escape = value => String(value).replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const markup = attributionMarkup({ actor_name: '<Alice>', actor_type: 'human', action: 'task.create', performed_at: '2026-10-09T02:03:04Z' }, false, escape);
  assert.match(markup, /&lt;Alice&gt;.*Human/);
  assert.match(markup, /task create/);
  assert.match(markup, /datetime="2026-10-09T02:03:04.000Z"/);
  assert.doesNotMatch(markup, /<Alice>/);
  assert.match(attributionMarkup(null, false, escape), /No recorded history/);
  assert.match(attributionMarkup(null, true, escape), /History unavailable/);
  assert.match(attributionMarkup({ actor_type: 'agent', actor_name: 'Analyst', performed_at: 'invalid' }, false, escape), /AI agent.*Time not recorded/s);
  assert.match(attributionMarkup({ performed_at: '2026-10-09T02:03:04' }, false, escape), /datetime="2026-10-09T02:03:04.000Z"/);
});

test('inbox stays available when approvals are forbidden and escapes titles', async () => {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {
      value: '', innerHTML: '', textContent: '', disabled: false, querySelectorAll: () => [],
      classList: { add() {}, toggle() {}, remove() {} },
    });
    return elements.get(id);
  };
  global.document = { getElementById: get, querySelectorAll: () => [] };
  let historyUnavailable = false;
  const inbox = create({
    getSession: () => ({ companyId: 'one', userId: 'member' }),
    api: async endpoint => {
      if (endpoint.endsWith('/inbox-attribution/task')) {
        if (historyUnavailable) throw new Error('History service unavailable');
        return [{ resource_id: 'ready', actor_type: 'human', actor_name: '<Alice>', action: 'task.create', performed_at: '2026-10-09T02:03:04Z' }];
      }
      if (endpoint.endsWith('/approvals')) throw new Error('Forbidden');
      if (endpoint.endsWith('/tasks')) return [{ ...tasks[2], title: '<script>alert(1)</script>' }];
      return [];
    },
    escapeHtml: value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
    navigate() {}, openTask() {}, onChanged() {},
  });
  await inbox.load();
  assert.match(get('inboxStats').innerHTML, /Unavailable/);
  assert.match(get('inboxList').innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(get('inboxList').innerHTML, /<script>/);
  assert.match(get('inboxList').innerHTML, /&lt;Alice&gt;/);
  assert.match(get('inboxList').innerHTML, /Latest recorded action/);
  assert.match(get('inboxNotice').textContent, /approvals/);
  assert.equal(get('btnRefreshInbox').disabled, false);
  historyUnavailable = true;
  await inbox.load();
  assert.match(get('inboxList').innerHTML, /History unavailable/);
  assert.match(get('inboxList').innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(get('inboxList').innerHTML, /Alice/);
  inbox.reset();
  assert.equal(get('inboxList').textContent, '');
  delete global.document;
});
