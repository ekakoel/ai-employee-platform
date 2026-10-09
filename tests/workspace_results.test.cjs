const test = require('node:test');
const assert = require('node:assert/strict');
const { describe, filterResults, create } = require('../app/static/workspace/results.js');

const items = [
  { ...describe({ id: 'old', title: 'Sales', result: '{"recommendation":"Review revenue"}', agent_instance_id: 'a', created_at: '2026-09-01T00:00:00Z' }), agentName: 'Analyst' },
  { ...describe({ id: 'new', title: 'Memo', result: 'Customer follow-up', agent_instance_id: 'b', created_at: '2026-10-09T00:00:00Z' }), agentName: 'Writer' },
];
const filters = { query: '', agent: '', kind: '', days: '', context: '', tab: 'all', pins: new Set(['old']) };

test('result types preserve text, JSON primitives, and structured outputs', () => {
  assert.equal(items[0].kind, 'analysis');
  assert.equal(items[1].kind, 'text');
  assert.equal(describe({ result: 'null' }).kind, 'text');
  assert.equal(describe({ result: '{"rows":[]}' }).kind, 'structured');
});

test('quotation summary uses the persisted tool document rather than model prose', () => {
  const document = 'Quotation for Ada\nTotal: 600.00 USD';
  const saved = describe({ result: JSON.stringify({ status: 'verified', tool_results: [
    { tool: 'draft_quotation', result: { draft: document, source_references: ['knowledge:prices'] } },
  ] }) });
  assert.equal(saved.summary, document);
  assert.equal(saved.documentText, document);
  assert.deepEqual(saved.value.tool_results[0].result.source_references, ['knowledge:prices']);
  assert.equal(describe({ result: '{"status":"completed"}' }).documentText, '');
});

test('search matches result content and agent names with newest-first sorting', () => {
  assert.deepEqual(filterResults(items, filters).map(x => x.id), ['new', 'old']);
  assert.equal(filterResults(items, { ...filters, query: 'REVENUE' })[0].id, 'old');
  assert.equal(filterResults(items, { ...filters, query: 'Writer' })[0].id, 'new');
});

test('agent, type, date, pins, and context filters combine', () => {
  assert.equal(filterResults(items, { ...filters, agent: 'a', kind: 'text' }).length, 0);
  assert.deepEqual(filterResults(items, { ...filters, tab: 'pinned' }).map(x => x.id), ['old']);
  assert.deepEqual(filterResults(items, { ...filters, days: '7' }, Date.parse('2026-10-10T00:00:00Z')).map(x => x.id), ['new']);
  assert.deepEqual(filterResults(items, { ...filters, context: 'old' }).map(x => x.id), ['old']);
});

test('results already visible in main are excluded even from pinned searches', () => {
  assert.deepEqual(filterResults(items, { ...filters, mainTitles: [' SALES '] }).map(item => item.id), ['new']);
  assert.equal(filterResults(items, { ...filters, tab: 'pinned', mainTitles: ['Sales'] }).length, 0);
  assert.deepEqual(filterResults(items, { ...filters, mainText: 'Agent: Customer follow-up' }).map(item => item.id), ['old']);
});

test('library loads persisted results, opens preview, pins, and clears on logout', async () => {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: '', textContent: '', innerHTML: '', disabled: false,
      classList: { toggle() {} }, setAttribute() {}, addEventListener(name, handler) { this[name] = handler; },
      querySelectorAll() { return []; },
    });
    return elements.get(id);
  }
  global.document = { getElementById: element, querySelectorAll: () => [] };
  let opened = false, source = '', revised = '', calls = [];
  const library = create({
    getSession: () => ({ companyId: 'one', userId: 'alice' }),
    api: async (path, options) => {
      calls.push([path, options]);
      if (options) return null;
      if (path.endsWith('/tasks')) return [{ ...items[0], title: '<script>alert(1)</script>' }];
      if (path.endsWith('/agents')) return [{ id: 'a', name: 'Analyst' }];
      return [];
    },
    escapeHtml: value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
    openPreview: () => { opened = true; }, openTask: item => { source = item.id; }, revise: item => { revised = item.id; },
  });
  await library.refresh();
  assert.match(element('outputContent').innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(element('outputContent').innerHTML, /<script>/);
  assert.equal(element('resultCount').textContent, '1 / 1 results');
  library.select(items[0]);
  assert.equal(opened, true);
  element('btnResultTask').onclick();
  element('btnResultRevise').onclick();
  assert.equal(source, 'old'); assert.equal(revised, 'old');
  await library.refresh();
  await element('btnResultPin').onclick();
  assert.ok(calls.some(([path, options]) => path.endsWith('/old/result-pin') && options?.method === 'PUT'));
  assert.match(element('outputContent').innerHTML, /Pinned/);
  library.reset();
  assert.equal(element('resultPreview').textContent, '');
  assert.doesNotMatch(element('outputContent').innerHTML, /Review revenue/);
  delete global.document;
});
