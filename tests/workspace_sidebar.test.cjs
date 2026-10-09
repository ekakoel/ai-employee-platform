const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { configs, buildContext, excludeMainRecords, guideText, create } = require('../app/static/workspace/sidebar.js');

const tasks = [
  { id: 'failed', title: 'Retry report', status: 'failed', agent_instance_id: 'a', mode: 'execute', created_at: '2026-10-08T00:00:00Z' },
  { id: 'done', title: 'Summary', status: 'completed', result: 'Summary text', agent_instance_id: 'a', mode: 'consult', created_at: '2026-10-09T00:00:00Z' },
];

test('every workspace navigation page has an explicit context', () => {
  const html = fs.readFileSync(path.join(__dirname, '../app/static/workspace/index.html'), 'utf8');
  const views = [...html.matchAll(/data-view="([^"]+)"/g)].map(match => match[1]);
  for (const view of [...views, 'result-preview']) {
    assert.ok(configs[view], `Missing context: ${view}`);
    const guide = configs[view].guide;
    assert.ok(guide?.page && guide.summary, `Missing guide: ${view}`);
    assert.ok(guide.summary.length <= 160, `Guide purpose too long: ${view}`);
    assert.ok(guide.steps.length >= 2 && guide.steps.length <= 3, `Guide step count: ${view}`);
    assert.ok(guide.steps.every(step => step.length <= 140), `Guide steps too long: ${view}`);
    assert.match(guideText(view), /Purpose\n.*\n\nTypical use\n1\./);
  }
});

test('Home and Tasks use complementary sources without repeating tasks or metrics', () => {
  const data = { tasks, approvals: [{ status: 'pending' }], notifications: [{ title: 'New update', read_at: null }], policies: [{ name: 'Refund limits', is_active: true }] };
  const home = buildContext('home', data);
  const taskContext = buildContext('tasks', data);
  assert.notEqual(home.title, taskContext.title);
  assert.deepEqual(home.metrics, []);
  assert.deepEqual(taskContext.metrics, []);
  assert.equal(home.sections[0].entries[0].title, 'New update');
  assert.equal(taskContext.sections[1].entries[0].title, 'Refund limits');
  assert.ok(!configs.home.resources.includes('tasks'));
  assert.ok(!configs.tasks.resources.includes('tasks'));
});

test('Chat context scopes work and capabilities to the selected agent', () => {
  const context = buildContext('chat', {
    tasks: [...tasks, { ...tasks[1], id: 'other', agent_instance_id: 'b' }],
    agents: [{ id: 'a', name: 'Analyst', status: 'active', skills: ['Reporting'], scope: ['Sales'] }],
  }, 'a');
  assert.equal(context.sections[0].entries[0].title, 'Reporting');
  assert.equal(context.sections[0].compact, true);
  assert.equal(context.sections[1].compact, true);
  assert.deepEqual(context.metrics, []);
  assert.equal(context.sections.at(-1).entries.some(entry => entry.task.id === 'other'), false);
});

test('cost pages show plan capacity while usage pages show complementary spending', () => {
  const cost = buildContext('cost', { usage: { plan: { name: 'Team', max_agents: 3, max_tasks_day: 10 }, usage: { agents: 3, tasks_today: 0 } } });
  assert.equal(cost.sections[0].entries[0].detail, 'Team');
  assert.equal(cost.sections[0].entries[1].detail, '0');
  const usage = buildContext('usage', { 'governance/cost': { today: { estimated_cost_usd: 0 }, budget: { soft_limit_enabled: false } } });
  assert.equal(usage.sections[0].entries[0].detail, '0');
  assert.equal(buildContext('usage', {}).sections.length, 0);
});

test('Chat employee brief uses recorded configuration and remains concise without duplicating main', () => {
  const data = { agents: [
    { id: 'a', configuration: { role: 'Revenue analyst' }, instructions: 'Compare revenue against approved targets. ' + 'Use verified records. '.repeat(20) },
    { id: 'b', configuration: { role: 'Private unrelated role' }, instructions: 'Unrelated instruction' },
  ] };
  const model = buildContext('chat', data, 'a');
  const brief = model.sections.find(section => section.title === 'Employee brief');
  assert.equal(brief.entries[0].detail, 'Revenue analyst');
  assert.ok(brief.entries[1].detail.length <= 180);
  assert.ok(!JSON.stringify(model).includes('Private unrelated role'));
  const filtered = excludeMainRecords(model, [], data.agents[0].instructions);
  assert.equal(filtered.sections[0].entries.length, 1);
  assert.ok(!buildContext('chat', data, 'missing').sections.some(section => section.title === 'Employee brief'));
  assert.ok(!buildContext('consult', data, 'a').sections.some(section => section.title === 'Employee brief'));
});

function fakeDocument() {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, {
        innerHTML: '', textContent: '', disabled: false, querySelectorAll: () => [], setAttribute() {},
        classList: { toggle: (name, value) => value ? classes.add(name) : classes.delete(name), contains: name => classes.has(name) },
      });
    }
    return elements.get(id);
  };
  global.document = { getElementById: get };
  return get;
}
const esc = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const options = { getSession: () => ({ companyId: 'one', userId: 'owner' }), escapeHtml: esc, getAgentId: () => '', navigate() {}, openTask() {}, openResult() {}, showResults() {} };

test('late Home requests cannot overwrite Tasks context; Results is optional', async () => {
  const get = fakeDocument();
  let finish, resultRequests = 0;
  const oldTasks = new Promise(resolve => { finish = resolve; });
  const sidebar = create({ ...options, showResults: () => { resultRequests++; }, api: async endpoint => {
    if (endpoint.endsWith('/notifications')) return oldTasks;
    if (endpoint.endsWith('/policies')) return [{ name: 'Fresh policy' }];
    return [];
  } });
  const old = sidebar.show('home');
  assert.equal(get('sidebarPageGuide').download, 'home-guide.txt');
  assert.match(decodeURIComponent(get('sidebarPageGuide').href), /An overview of workspace priorities/);
  await sidebar.show('tasks');
  assert.equal(get('sidebarPageGuide').download, 'tasks-guide.txt');
  finish([{ title: 'Stale home data' }]);
  await old;
  assert.equal(get('outputTitle').textContent, 'Task references');
  assert.match(get('sidebarContext').innerHTML, /Fresh policy/);
  assert.doesNotMatch(get('sidebarContext').innerHTML, /Stale home data/);
  get('btnSidebarResults').onclick();
  assert.equal(get('sidebarPageGuide').download, 'tasks-guide.txt');
  assert.equal(resultRequests, 1);
  assert.equal(get('sidebarContext').classList.contains('hidden'), true);
  await sidebar.show('knowledge');
  assert.equal(get('resultLibrary').classList.contains('hidden'), true);
  assert.equal(get('outputTitle').textContent, 'Related capabilities');
  delete global.document;
});

test('permission errors, hostile titles, and logout are handled safely', async () => {
  const get = fakeDocument();
  const sidebar = create({ ...options, api: async endpoint => {
    if (endpoint.endsWith('/notifications')) throw new Error('Forbidden');
    if (endpoint.endsWith('/workflows')) return [{ name: '<img src=x onerror=alert(1)>' }];
    return { count: 0 };
  } });
  await sidebar.show('home');
  assert.equal(get('sidebarPageGuide').download, 'home-guide.txt');
  assert.match(get('sidebarContext').innerHTML, /Some page data is unavailable/);
  assert.match(get('sidebarContext').innerHTML, /&lt;img/);
  assert.doesNotMatch(get('sidebarContext').innerHTML, /<img/);
  sidebar.reset();
  assert.equal(get('sidebarContext').textContent, '');
  assert.equal(get('btnRefreshSidebar').disabled, false);
  delete global.document;
});

test('duplicate titles are normalized and rechecked after the main page renders', async () => {
  const model = buildContext('tasks', { policies: [{ name: 'Refund rules' }, { name: 'Extra guidance' }] });
  const filtered = excludeMainRecords(model, [' REFUND   RULES ']);
  assert.deepEqual(filtered.sections[1].entries.map(entry => entry.title), ['Extra guidance']);
  const get = fakeDocument();
  let mainTitles = [];
  const sidebar = create({ ...options, getMainTitles: () => mainTitles, api: async endpoint => endpoint.endsWith('/policies') ? [{ name: 'Refund rules' }] : [] });
  await sidebar.show('tasks');
  assert.match(get('sidebarContext').innerHTML, /Refund rules/);
  mainTitles = ['Refund rules'];
  sidebar.reconcile();
  assert.doesNotMatch(get('sidebarContext').innerHTML, /Refund rules/);
  delete global.document;
});
