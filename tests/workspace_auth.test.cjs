const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '../app/static/workspace');
const source = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

function fixture({ saved = {}, respond, mode = 'user' } = {}) {
  const storage = new Map(Object.entries(saved));
  const elements = new Map();
  for (const match of html.matchAll(/<([a-z][\w-]*)\b[^>]*\bid="([^"]+)"[^>]*>/gi)) {
    const classes = new Set();
    const listeners = new Map();
    elements.set(match[2], {
      tagName: match[1].toUpperCase(), value: '', textContent: '', innerHTML: '',
      checked: false, disabled: false, dataset: {}, listeners,
      classList: {
        add: name => classes.add(name), remove: name => classes.delete(name),
        contains: name => classes.has(name),
        toggle: (name, yes) => yes ? classes.add(name) : classes.delete(name),
      },
      addEventListener: (name, handler) => listeners.set(name, handler),
      setAttribute() {}, focus() {}, click() { return this.onclick?.(); },
    });
  }
  const get = id => elements.get(id) || null;
  const calls = [];
  const resets = [];
  let session;
  // Stub dashboard rendering only; execute the real controller and its auth handlers.
  const dashboard = {
    create(options) {
      session = options.getSession;
      return Object.fromEntries(['reset', 'refresh', 'reconcile', 'show', 'load', 'results']
        .map(name => [name, () => { if (name === 'reset') resets.push(options); }]));
    },
    buildQueue: () => [],
  };
  vm.runInNewContext(source, {
    document: {
      body: { dataset: { workspace: mode } }, getElementById: get,
      querySelectorAll: () => [], querySelector: selector => selector === 'main' ? {} : null,
    },
    localStorage: {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: key => storage.delete(key),
    },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const response = await respond?.(url, options) || { status: 200, body: [] };
      return { status: response.status, ok: response.status < 400, text: async () => JSON.stringify(response.body) };
    },
    WorkspaceResults: dashboard, WorkspaceHome: dashboard, WorkspaceInbox: dashboard,
    WorkspaceSidebar: dashboard, WorkspaceChat: dashboard,
    MutationObserver: class { observe() {} }, console: { warn() {} }, location: {},
  }, { filename: 'app.js', timeout: 1000 });
  return { get, calls, storage, resets, session: () => session() };
}

const profile = { company_id: 'tenant-a', user_id: 'user-a', name: 'Test User',
  role: 'owner', permissions: ['task.read'], is_platform_admin: false,
  access_token: 'mock-access', refresh_token: 'mock-refresh' };
const savedSession = {
  ws_companyId: profile.company_id, ws_userId: profile.user_id,
  ws_accessToken: profile.access_token, ws_refreshToken: profile.refresh_token,
  ws_userName: profile.name, ws_role: 'owner', ws_permissions: '["team.manage"]', ws_isPlatformAdmin: '1',
};

test('workspace initializes the login gate and registers login/logout/Enter handlers', async () => {
  const f = fixture();
  await settle();
  assert.equal(f.get('registerCompanyId'), null);
  assert.equal(f.get('loginCompanyId').value, '');
  assert.equal(f.get('loginGate').classList.contains('hidden'), false);
  assert.equal(f.get('app').classList.contains('hidden'), true);
  for (const id of ['btnLogin', 'btnLogout', 'btnClearSession', 'btnQuickStart']) {
    assert.equal(typeof f.get(id).onclick, 'function');
  }
  for (const id of ['loginEmail', 'loginPassword']) {
    let clicked = false;
    f.get('btnLogin').onclick = () => { clicked = true; };
    f.get(id).listeners.get('keydown')({ key: 'Enter' });
    assert.equal(clicked, true);
  }
  assert.equal(f.calls.length, 0);
});

test('successful login uses existing credentials contract and updates company/session fields', async () => {
  const f = fixture({ respond: url => url.endsWith('/auth/login') ? { status: 200, body: profile } : undefined });
  f.get('loginEmail').value = ' user@example.test ';
  f.get('loginPassword').value = 'mock-password';
  await f.get('btnLogin').onclick();
  const login = f.calls.find(call => call.url.endsWith('/auth/login'));
  assert.equal(login.options.method, 'POST');
  // Compare booleans so failed assertions do not print credential payloads.
  const payload = JSON.parse(login.options.body);
  assert.equal(Object.keys(payload).sort().join(','), 'email,password');
  assert.ok(payload.email === 'user@example.test' && payload.password === 'mock-password');
  assert.equal(login.options.headers.Authorization, undefined);
  assert.equal(login.options.headers['X-User-ID'], undefined);
  assert.equal(f.get('loginCompanyId').value, profile.company_id);
  assert.equal(f.get('companyId').value, profile.company_id);
  assert.equal(f.get('userId').value, profile.user_id);
  assert.ok(f.storage.get('ws_accessToken') === profile.access_token);
  assert.ok(f.storage.get('ws_refreshToken') === profile.refresh_token);
  assert.equal(f.get('loginGate').classList.contains('hidden'), true);
  assert.equal(f.get('btnLogin').disabled, false);
  const hydrate = f.calls.find(call => call.url.endsWith('/inventory/hydrate'));
  assert.ok(hydrate.options.headers.Authorization === `Bearer ${profile.access_token}`);
  assert.equal(f.calls.some(call => /\/auth\/(token|register)$/.test(call.url)), false);
});

test('failed login stays at the gate without creating a session', async () => {
  const f = fixture({ respond: () => ({ status: 401, body: { detail: 'Invalid credentials' } }) });
  f.get('loginEmail').value = 'user@example.test';
  f.get('loginPassword').value = 'mock-password';
  await f.get('btnLogin').onclick();
  assert.equal(f.get('loginLog').textContent, 'Invalid credentials');
  assert.equal(f.get('loginLog').classList.contains('error'), true);
  assert.equal(f.get('loginGate').classList.contains('hidden'), false);
  assert.equal(f.storage.has('ws_accessToken'), false);
  assert.equal(f.get('btnLogin').disabled, false);
});

test('missing credentials never send a login request', async () => {
  const f = fixture();
  await f.get('btnLogin').onclick();
  assert.equal(f.calls.length, 0);
  assert.equal(f.get('loginLog').textContent, 'Email and password are required');
});

test('boot restores the company field and verifies profile using Bearer; logout clears session', async () => {
  const f = fixture({ saved: savedSession,
    respond: url => url.endsWith('/auth/me') ? { status: 200, body: profile } : undefined });
  await settle();
  assert.equal(f.get('loginCompanyId').value, profile.company_id);
  const me = f.calls.find(call => call.url.endsWith('/auth/me'));
  assert.ok(me.options.headers.Authorization === `Bearer ${profile.access_token}`);
  assert.equal(f.get('loginGate').classList.contains('hidden'), true);
  f.get('btnLogout').onclick();
  assert.equal(f.session().companyId, '');
  assert.equal(f.session().userId, '');
  assert.ok(f.session().accessToken === '');
  for (const key of ['ws_companyId', 'ws_userId', 'ws_accessToken', 'ws_refreshToken',
    'ws_userName', 'ws_role', 'ws_permissions', 'ws_isPlatformAdmin']) {
    assert.equal(f.storage.has(key), false);
  }
  assert.equal(f.get('loginGate').classList.contains('hidden'), false);
  assert.equal(f.get('app').classList.contains('hidden'), true);
});

test('quick start reports denied provisioning without creating a session', async () => {
  const f = fixture({ respond: () => ({ status: 403, body: { detail: 'Provisioning restricted' } }) });
  await f.get('btnQuickStart').onclick();
  assert.equal(f.calls.length, 1);
  assert.equal(f.get('quickLog').textContent, 'Quick start failed: Provisioning restricted');
  assert.equal(f.storage.has('ws_companyId'), false);
});

function assertUnauthenticated(f) {
  for (const key of ['companyId', 'userId', 'userName', 'role']) assert.equal(f.session()[key], '');
  assert.ok(f.session().accessToken === '');
  assert.equal(f.session().permissions.length, 0);
  assert.equal(f.session().isPlatformAdmin, false);
  for (const key of ['ws_companyId', 'ws_userId', 'ws_accessToken', 'ws_refreshToken',
    'ws_userName', 'ws_role', 'ws_permissions', 'ws_isPlatformAdmin']) assert.equal(f.storage.has(key), false);
  for (const id of ['companyId', 'userId', 'loginCompanyId']) assert.equal(f.get(id).value, '');
  assert.equal(f.get('loginGate').classList.contains('hidden'), false);
  assert.equal(f.get('app').classList.contains('hidden'), true);
  assert.equal(f.get('statusPill').textContent, 'Offline');
  assert.equal(f.get('sessionBox').innerHTML.includes(profile.name), false);
  assert.ok(f.resets.length >= 5);
}

test('expired /auth/me clears credentials, identity, tenant controls and cached dashboards', async () => {
  const f = fixture({ saved: savedSession,
    respond: () => ({ status: 401, body: { detail: 'Token expired' } }) });
  await settle();
  assert.equal(f.calls.length, 1);
  assertUnauthenticated(f);
});

for (const failure of ['network', 503]) {
  test(`/auth/me ${failure} preserves credentials but never confirms connection`, async () => {
    const f = fixture({ saved: savedSession, respond: () => {
      if (failure === 'network') throw new TypeError('Failed to fetch');
      return { status: failure, body: { detail: 'Temporarily unavailable' } };
    } });
    await settle();
    assert.ok(f.storage.get('ws_accessToken') === profile.access_token);
    assert.ok(f.storage.get('ws_refreshToken') === profile.refresh_token);
    assert.equal(f.get('loginGate').classList.contains('hidden'), false);
    assert.equal(f.get('statusPill').textContent, 'Offline');
    assert.equal(f.calls.length, 1);
  });
}

test('profile identity overrides cached tenant/user IDs, not the other way around', async () => {
  const f = fixture({ saved: { ...savedSession, ws_companyId: 'old-tenant', ws_userId: 'old-user' },
    respond: url => url.endsWith('/auth/me') ? { status: 200, body: profile } : undefined });
  await settle();
  assert.equal(f.session().companyId, profile.company_id);
  assert.equal(f.session().userId, profile.user_id);
  assert.equal(f.get('loginCompanyId').value, profile.company_id);
  assert.equal(f.calls.some(call => call.url.includes('/companies/old-tenant')), false);
});

test('failed new login removes all previous identity and permissions', async () => {
  const f = fixture({ saved: savedSession, respond: url => url.endsWith('/auth/me')
    ? { status: 200, body: profile } : url.endsWith('/auth/login')
      ? { status: 401, body: { detail: 'Invalid credentials' } } : undefined });
  await settle();
  f.get('loginEmail').value = 'other@example.test';
  f.get('loginPassword').value = 'mock-password';
  await f.get('btnLogin').onclick();
  assertUnauthenticated(f);
});

test('successful new login replaces previous identity and clears old refresh credential if omitted', async () => {
  const next = { ...profile, company_id: 'tenant-b', user_id: 'user-b', name: 'New User', refresh_token: null };
  const f = fixture({ saved: savedSession, respond: url => url.endsWith('/auth/me')
    ? { status: 200, body: profile } : url.endsWith('/auth/login')
      ? { status: 200, body: next } : undefined });
  await settle();
  f.get('loginEmail').value = 'other@example.test';
  f.get('loginPassword').value = 'mock-password';
  await f.get('btnLogin').onclick();
  assert.equal(f.session().companyId, next.company_id);
  assert.equal(f.session().userId, next.user_id);
  assert.equal(f.get('sessionBox').innerHTML.includes(profile.name), false);
  assert.equal(f.storage.has('ws_refreshToken'), false);
});

test('logout prevents late profile response from restoring identity', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const f = fixture({ saved: savedSession, respond: () => pending });
  f.get('btnLogout').onclick();
  finish({ status: 200, body: profile });
  await settle();
  assertUnauthenticated(f);
  assert.equal(f.calls.length, 1);
});

test('logout prevents late successful login from restoring identity', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const f = fixture({ respond: () => pending });
  f.get('loginEmail').value = 'user@example.test';
  f.get('loginPassword').value = 'mock-password';
  const login = f.get('btnLogin').onclick();
  f.get('btnLogout').onclick();
  finish({ status: 200, body: profile });
  await login;
  assertUnauthenticated(f);
});

test('cached IDs without Bearer token cannot restore a session', async () => {
  const f = fixture({ saved: { ws_companyId: 'old-tenant', ws_userId: 'old-user' } });
  await settle();
  assertUnauthenticated(f);
  assert.equal(f.calls.length, 0);
});

test('empty-permission login stops if subsequent profile verification rejects the token', async () => {
  const f = fixture({ respond: url => url.endsWith('/auth/login')
    ? { status: 200, body: { ...profile, permissions: [] } }
    : { status: 401, body: { detail: 'Invalid session' } } });
  f.get('loginEmail').value = 'user@example.test';
  f.get('loginPassword').value = 'mock-password';
  await f.get('btnLogin').onclick();
  assertUnauthenticated(f);
  assert.equal(f.calls.length, 2);
});

for (const failure of ['network', 500]) {
  test(`new login profile ${failure} stays offline without discarding the new credentials`, async () => {
    const f = fixture({ respond: url => {
      if (url.endsWith('/auth/login')) return { status: 200, body: { ...profile, permissions: [] } };
      if (failure === 'network') throw new TypeError('Failed to fetch');
      return { status: failure, body: { detail: 'Server error' } };
    } });
    f.get('loginEmail').value = 'user@example.test';
    f.get('loginPassword').value = 'mock-password';
    await f.get('btnLogin').onclick();
    assert.ok(f.storage.get('ws_accessToken') === profile.access_token);
    assert.equal(f.get('statusPill').textContent, 'Offline');
    assert.equal(f.get('loginGate').classList.contains('hidden'), false);
    assert.equal(f.calls.length, 2);
  });
}

test('late 401 for the previous session cannot clear a newly authenticated user', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const next = { ...profile, company_id: 'tenant-b', user_id: 'user-b' };
  const f = fixture({ saved: savedSession, respond: url => url.endsWith('/auth/me')
    ? pending : url.endsWith('/auth/login') ? { status: 200, body: next } : undefined });
  f.get('loginEmail').value = 'other@example.test';
  f.get('loginPassword').value = 'mock-password';
  await f.get('btnLogin').onclick();
  finish({ status: 401, body: { detail: 'Old session expired' } });
  await settle();
  assert.equal(f.session().userId, next.user_id);
  assert.equal(f.session().companyId, next.company_id);
  assert.equal(f.get('statusPill').textContent, 'Online');
});

test('developer console also stays unauthenticated after rejected profile verification', async () => {
  const f = fixture({ mode: 'developer', saved: { ...savedSession, ws_isPlatformAdmin: '1' },
    respond: () => ({ status: 401, body: { detail: 'Invalid session' } }) });
  await settle();
  assertUnauthenticated(f);
  assert.equal(f.calls.length, 1);
});

test('logout during login bootstrap stops further workspace initialization', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const f = fixture({ respond: url => url.endsWith('/auth/login')
    ? { status: 200, body: profile } : pending });
  f.get('loginEmail').value = 'user@example.test';
  f.get('loginPassword').value = 'mock-password';
  const login = f.get('btnLogin').onclick();
  await settle();
  f.get('btnLogout').onclick();
  finish({ status: 200, body: {} });
  await login;
  assertUnauthenticated(f);
  assert.equal(f.calls.length, 2);
});
