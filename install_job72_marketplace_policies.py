"""Install Job 72 in-place. Run from repo root: python install_job72_marketplace_policies.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app/static/workspace/index.html").exists():
    sys.exit("Run from repo root (folder containing app/)")

html_path = ROOT / "app/static/workspace/index.html"
js_path = ROOT / "app/static/workspace/app.js"
docs = ROOT / "docs/features"
docs.mkdir(parents=True, exist_ok=True)

html = html_path.read_text(encoding="utf-8")

# --- Marketplace ---
if 'Install copies skills' in html or 'Public agent templates' in html:
    old_m = None
    for candidate in [
        '''      <section id="view-marketplace" class="view">
        <div class="card">
          <div class="row between">
            <div>
              <h2>Marketplace</h2>
              <p class="muted">Public agent templates. Install copies skills into your company catalog.</p>
            </div>
            <button id="btnRefreshMarket" class="secondary">Refresh</button>
          </div>
          <div id="marketList" class="cards"></div>
        </div>
        <div class="card">
          <h3>Installed templates</h3>
          <div id="installList" class="list"></div>
        </div>
      </section>
''',
    ]:
        if candidate in html:
            old_m = candidate
            break
    new_m = '''      <section id="view-marketplace" class="view">
        <p class="home-notice" role="status">
          <strong>Marketplace</strong> lists public AI Employee templates.
          <strong>Install</strong> copies template skills into your company (does not hire an instance by itself).
          After install, open <strong>AI Employees</strong> to hire from the catalog.
        </p>
        <div class="card">
          <div class="row between">
            <div>
              <h2>Public templates</h2>
              <p class="muted">Install requires <code>agent.hire</code> or <code>agent.manage</code> (Owner / AI Admin).</p>
            </div>
            <button id="btnRefreshMarket" class="secondary">Refresh</button>
          </div>
          <div id="marketList" class="cards"></div>
        </div>
        <div class="card">
          <h3>Installed templates</h3>
          <div id="installList" class="list"></div>
        </div>
      </section>
'''
    if old_m:
        html = html.replace(old_m, new_m)
        print("marketplace HTML updated")
    elif 'id="view-marketplace"' in html and "does not hire an instance" not in html:
        print("WARN: marketplace section shape differs — insert notice manually if needed")
    else:
        print("marketplace HTML already polished or unknown shape")

# --- Skills ---
old_s = '''      <section id="view-skills" class="view">
        <div class="card">
          <div class="row between">
            <div>
              <h2>Skills</h2>
              <p class="muted">Platform + company-scoped skills available to agents.</p>
            </div>
            <button id="btnRefreshSkills" class="secondary">Refresh</button>
          </div>
          <div id="skillsList" class="cards"></div>
        </div>
        <div class="card">
          <h3>Create company skill</h3>
          <div class="grid-2">
            <label>Slug
              <input id="skillSlug" placeholder="sales_followup" />
            </label>
            <label>Name
              <input id="skillName" placeholder="Sales follow-up" />
            </label>
            <label class="full">Description
              <textarea id="skillDescription" rows="2"></textarea>
            </label>
          </div>
          <button id="btnCreateSkill" class="primary">Create skill</button>
          <pre id="skillLog" class="log"></pre>
        </div>
      </section>
'''
new_s = '''      <section id="view-skills" class="view">
        <p class="home-notice" role="status">
          <strong>Skills</strong> are capabilities agents can use (platform catalog + company-specific).
          Company skills can be created by Owner / AI Admin.
          <em>Platform skill catalog upgrades</em> are done only by platform developers — not company users.
        </p>
        <div class="card">
          <div class="row between">
            <div>
              <h2>Skill catalog</h2>
              <p class="muted">Platform and company skills visible to your tenant.</p>
            </div>
            <button id="btnRefreshSkills" class="secondary">Refresh</button>
          </div>
          <div id="skillsList" class="cards"></div>
        </div>
        <div class="card" id="skillCreateCard">
          <h3>Create company skill</h3>
          <p class="muted">Requires <code>agent.manage</code>. For advanced platform catalog changes, use the developer console.</p>
          <div class="grid-2">
            <label>Slug
              <input id="skillSlug" placeholder="sales_followup" />
            </label>
            <label>Name
              <input id="skillName" placeholder="Sales follow-up" />
            </label>
            <label class="full">Description
              <textarea id="skillDescription" rows="2"></textarea>
            </label>
          </div>
          <button id="btnCreateSkill" class="primary">Create skill</button>
          <pre id="skillLog" class="log"></pre>
        </div>
      </section>
'''
if old_s in html:
    html = html.replace(old_s, new_s)
    print("skills HTML updated")
elif 'id="skillCreateCard"' in html:
    print("skills HTML already has skillCreateCard")
else:
    print("WARN: skills section not matched")

# --- Policies ---
old_p = '''      <section id="view-policy-management" class="view">
        <div class="card">
          <h2>Create policy</h2>
          <div class="grid-2">
            <label>Name
              <input id="policyName" placeholder="Require approval for quotes" />
            </label>
            <label>Effect
              <select id="policyEffect">
                <option value="allow">allow</option>
                <option value="require_approval">require_approval</option>
                <option value="deny">deny</option>
              </select>
            </label>
            <label>Tool / action
              <input id="policyTool" placeholder="send_quotation" />
            </label>
            <label>Description
              <input id="policyDescription" placeholder="Optional note" />
            </label>
          </div>
          <button id="btnCreatePolicy" class="primary">Create policy</button>
          <pre id="policyLog" class="log"></pre>
        </div>
'''
new_p = '''      <section id="view-policy-management" class="view">
        <p class="home-notice" role="status">
          <strong>Policies</strong> control whether tools may run: <code>allow</code>, <code>require_approval</code>, or <code>deny</code>.
          AI Administrators and Owners configure these. Unmatched tools are denied by default.
          After changing policies, test with Task <strong>execute</strong> or the developer Policy Simulator.
        </p>
        <div class="card" id="policyCreateCard">
          <h2>Create policy</h2>
          <p class="muted">Requires <code>policy.manage</code>. Example tools: <code>search_availability</code>, <code>send_quotation</code>, <code>create_reservation</code>.</p>
          <div class="grid-2">
            <label>Name
              <input id="policyName" placeholder="Require approval for bookings" />
            </label>
            <label>Effect
              <select id="policyEffect">
                <option value="allow">allow</option>
                <option value="require_approval">require_approval</option>
                <option value="deny">deny</option>
              </select>
            </label>
            <label>Tool / action
              <input id="policyTool" placeholder="create_reservation" list="policyToolHints" />
              <datalist id="policyToolHints">
                <option value="search_availability"></option>
                <option value="send_quotation"></option>
                <option value="create_reservation"></option>
              </datalist>
            </label>
            <label>Description
              <input id="policyDescription" placeholder="Optional note" />
            </label>
          </div>
          <button id="btnCreatePolicy" class="primary">Create policy</button>
          <pre id="policyLog" class="log"></pre>
        </div>
'''
if old_p in html:
    html = html.replace(old_p, new_p)
    print("policies HTML updated")
elif 'id="policyCreateCard"' in html:
    print("policies HTML already polished")
else:
    print("WARN: policies section not matched")

html_path.write_text(html, encoding="utf-8")

# --- JS ---
js = js_path.read_text(encoding="utf-8")

if "const canInstall = hasPermission" not in js:
    target = '''            ${installed.has(t.id)
                ? `<span class="pill ok">Installed</span>`
                : `<button class="primary btn-install" data-id="${t.id}">Install</button>`
              }'''
    repl = '''            ${installed.has(t.id)
                ? `<span class="pill ok">Installed</span>`
                : canInstall
                  ? `<button class="primary btn-install" data-id="${t.id}">Install</button>`
                  : `<span class="meta">Install requires Owner/AI Admin</span>`
              }'''
    if target in js:
        js = js.replace(
            "const installed = new Set((installs || []).map((i) => i.catalog_agent_id));",
            "const installed = new Set((installs || []).map((i) => i.catalog_agent_id));\n"
            "      const canInstall = hasPermission(\"agent.hire\") || hasPermission(\"agent.manage\");",
            1,
        )
        js = js.replace(target, repl)
        print("marketplace install gating OK")
    else:
        print("WARN: install button template not found")

if 'skillCreateCard' not in js or 'skillCreateCard").classList' not in js:
    if "async function loadSkills()" in js and 'skillCreateCard' not in js.split("async function loadSkills()")[1][:400]:
        js = js.replace(
            "  async function loadSkills() {\n    if (!state.companyId) return;\n    try {",
            "  async function loadSkills() {\n    if (!state.companyId) return;\n"
            "    if ($(\"skillCreateCard\")) {\n"
            "      $(\"skillCreateCard\").classList.toggle(\"hidden\", !hasPermission(\"agent.manage\"));\n"
            "    }\n    try {",
            1,
        )
        print("skills gating OK")

if 'policyCreateCard' not in js or 'policyCreateCard").classList' not in js:
    if "async function loadPolicies()" in js:
        js = js.replace(
            "  async function loadPolicies() {\n    if (!state.companyId) return;\n    try {",
            "  async function loadPolicies() {\n    if (!state.companyId) return;\n"
            "    if ($(\"policyCreateCard\")) {\n"
            "      $(\"policyCreateCard\").classList.toggle(\n"
            "        \"hidden\",\n"
            "        !(hasPermission(\"policy.manage\") || hasPermission(\"agent.manage\"))\n"
            "      );\n"
            "    }\n    try {",
            1,
        )
        print("policies gating OK")

if 'Policy created."' in js and "Unmatched tools" not in js:
    js = js.replace(
        'log.textContent = "Policy created.";',
        'log.textContent =\n'
        '          "Policy created. Unmatched tools remain denied by default. Run a Task execute or Policy Simulator to verify.";',
        1,
    )
    print("policy success message OK")

js_path.write_text(js, encoding="utf-8")

# --- Docs (always overwrite feature pages) ---
(docs / "14_marketplace_skills.md").write_text(
    """# Feature: Marketplace & Skills

## Marketplace
Public AI Employee **templates**. **Install** copies skills into the company catalog; it does **not** create a running agent instance.

| Action | Who |
|--------|-----|
| Browse templates | Users with marketplace access |
| Install template | `agent.hire` or `agent.manage` (Owner, AI Admin) |
| Hire instance | **AI Employees** page after install |

### Backend
- `GET /api/v1/marketplace/templates`
- `POST /companies/{id}/marketplace/install/{catalog_id}`
- `GET /companies/{id}/marketplace/installations`

## Skills
| Action | Who |
|--------|-----|
| List skills | Company users with agent access |
| Create **company** skill | `agent.manage` (Owner, AI Admin) |
| Upgrade **platform** skill catalog | Platform developer only (`/developer`) |

### Backend
- `GET /companies/{id}/skills`
- `POST /companies/{id}/skills`

## Flow
```
Marketplace Install → AI Employees Hire → Chat/Tasks
```
""",
    encoding="utf-8",
)

(docs / "15_policies_ai_admin.md").write_text(
    """# Feature: Policies (AI Administrator)

## Purpose
Rules for tools during **Task execute**:

| Effect | Meaning |
|--------|---------|
| `allow` | Tool runs without human gate |
| `require_approval` | Approval queue |
| `deny` | Blocked |

**Default:** no matching policy → **denied**.

## Who
| Role | View | Create |
|------|------|--------|
| Owner | Yes | Yes |
| AI Administrator | Yes | Yes |
| Others | Usually no | No |

## Frontend
- Nav **Policies**
- Effects: allow / require_approval / deny
- Example tools: `search_availability`, `send_quotation`, `create_reservation`

## Starter policies (travel)
1. `search_availability` → allow  
2. `create_reservation` → require_approval  

## Backend
- `GET /companies/{id}/policies`
- `POST /companies/{id}/policies`
- Policy Simulator on developer console
""",
    encoding="utf-8",
)
print("docs 14/15 written")

# Append to README without full replace
readme = docs / "README.md"
if readme.exists():
    rt = readme.read_text(encoding="utf-8")
    if "14_marketplace_skills" not in rt:
        rt = rt.rstrip() + "\n\n| 14 | Marketplace & Skills | [14](14_marketplace_skills.md) |\n| 15 | Policies (AI Admin) | [15](15_policies_ai_admin.md) |\n"
        readme.write_text(rt, encoding="utf-8")
        print("README appended")
    else:
        print("README already lists 14/15")
else:
    readme.write_text(
        "# Features\n\n| 14 | Marketplace & Skills | [14_marketplace_skills.md](14_marketplace_skills.md) |\n| 15 | Policies | [15_policies_ai_admin.md](15_policies_ai_admin.md) |\n",
        encoding="utf-8",
    )

# Test file
(ROOT / "tests").mkdir(exist_ok=True)
(ROOT / "tests/test_marketplace_policies_ui_job72.py").write_text(
    '''"""Job 72 — marketplace/skills/policies UI + docs."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_marketplace_skills_policies_markup():
    html = client.get("/workspace").text
    assert 'id="view-marketplace"' in html
    assert 'id="view-skills"' in html
    assert 'id="skillCreateCard"' in html
    assert 'id="view-policy-management"' in html
    assert 'id="policyCreateCard"' in html


def test_docs_exist():
    assert Path("docs/features/14_marketplace_skills.md").is_file()
    assert Path("docs/features/15_policies_ai_admin.md").is_file()


def test_js_gating_hooks():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "canInstall" in js
    assert "skillCreateCard" in js
    assert "policyCreateCard" in js
''',
    encoding="utf-8",
)
print("test written")
print("\nDone. Run: pytest tests/test_marketplace_policies_ui_job72.py -q")
print("Then Ctrl+F5 on /workspace")
