"""Install Job 63 in-place (safe when git apply fails). Run from repo root."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app" / "static" / "workspace" / "app.js").exists():
    sys.exit("Run from repo root (folder that contains app/)")

js_path = ROOT / "app/static/workspace/app.js"
html_path = ROOT / "app/static/workspace/index.html"
svc_path = ROOT / "app/services/company_onboarding.py"
docs_dir = ROOT / "docs/features"
tests_path = ROOT / "tests/test_users_positions_job63.py"

# --- 1) Fix critical syntax ---
js = js_path.read_text(encoding="utf-8")
changed = False
for bad, good in [
    (
        'if ($("btnRefreshUsers") $("btnRefreshUsers").onclick = loadUsers;',
        'if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;',
    ),
    (
        "if ($('btnRefreshUsers') $('btnRefreshUsers').onclick = loadUsers;",
        "if ($('btnRefreshUsers')) $('btnRefreshUsers').onclick = loadUsers;",
    ),
]:
    if bad in js:
        js = js.replace(bad, good)
        changed = True
        print("Fixed btnRefreshUsers syntax")
if 'if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;' not in js:
    # last resort: regex-ish manual line scan
    lines = js.splitlines(keepends=True)
    out = []
    for line in lines:
        if "btnRefreshUsers" in line and "onclick = loadUsers" in line and "))" not in line.split("onclick")[0]:
            out.append('  if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;\n')
            changed = True
            print("Fixed btnRefreshUsers via line rewrite")
        else:
            out.append(line)
    js = "".join(out)

# Invite success message enhancement (idempotent)
needle = 'log.textContent = body.message;'
if needle in js and "Position:" not in js[js.find("btnCreateUser") : js.find("btnCreateUser") + 1200]:
    js = js.replace(
        '''        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = body.message;
        }
        if ($("inviteDebugTokenWrap")) $("inviteDebugTokenWrap").classList.toggle("hidden", !body.invitation_token);
''',
        '''        if (log) {
          log.classList.remove("hidden-log");
          const role = body.role_name || ($("userRoleInput") && $("userRoleInput").value) || "member";
          log.textContent =
            (body.message || "Invitation created.") +
            " Position: " + role +
            (body.invitation_token
              ? "\\nDev token (Accept invitation tab): " + body.invitation_token
              : "\\nEmployee will receive an email when SMTP is configured.");
        }
        if ($("inviteDebugTokenWrap")) $("inviteDebugTokenWrap").classList.toggle("hidden", !body.invitation_token);
''',
        1,
    )
    changed = True
    print("Enhanced invite log message")

# Ensure invite sends role_name
if 'role_name: ($("userRoleInput")' not in js and "userRoleInput" in (html_path.read_text(encoding="utf-8") if html_path.exists() else ""):
    if 'email: ($("userEmailInput").value || "").trim(),' in js and "role_name:" not in js[js.find("btnCreateUser"):js.find("btnCreateUser")+800]:
        js = js.replace(
            'email: ($("userEmailInput").value || "").trim(),',
            'email: ($("userEmailInput").value || "").trim(),\n'
            '            role_name: ($("userRoleInput") && $("userRoleInput").value) || "member",',
            1,
        )
        changed = True
        print("Added role_name to invite payload")

if changed:
    js_path.write_text(js, encoding="utf-8")
    print("Wrote", js_path.relative_to(ROOT))
else:
    print("app.js already OK or only syntax check")

# Verify syntax with a simple bracket scan for the bad pattern
js2 = js_path.read_text(encoding="utf-8")
if 'if ($("btnRefreshUsers") $("btnRefreshUsers")' in js2:
    sys.exit("ERROR: syntax still broken")
print("Syntax check: btnRefreshUsers OK")

# --- 2) HTML hierarchy legend ---
html = html_path.read_text(encoding="utf-8")
if "role-legend" not in html and "Users &amp; job positions" in html:
    html = html.replace(
        '<p class="muted">Owner invites employees by email and assigns a job position (role). AI Administrator can manage agents, skills, and knowledge. Owner role cannot be assigned by invitation.</p>',
        '''<p class="muted"><strong>Owner only:</strong> invite employees and change their job position. The Owner account cannot be invited or demoted here.</p>
          <div class="role-legend muted" style="font-size:.85rem;line-height:1.5;margin-bottom:1rem;padding:.75rem 1rem;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
            <strong>Hierarchy</strong>
            <ul style="margin:.35rem 0 0 1.1rem;padding:0">
              <li><strong>Owner</strong> — full company control; invites users; manages AI Employees</li>
              <li><strong>AI Administrator</strong> — agents, skills, knowledge, policies (not ownership)</li>
              <li><strong>Manager / Supervisor</strong> — approvals and day-to-day ops</li>
              <li><strong>Reservation / Contract / Accounting / Administration / Member</strong> — by job</li>
            </ul>
          </div>''',
    )
    html = html.replace(
        '<button data-view="users" class="nav-btn">Users & Roles</button>',
        '<button data-view="users" class="nav-btn">Users &amp; positions</button>',
    )
    html = html.replace(
        '<button data-view="users" class="nav-btn">Users &amp; Roles</button>',
        '<button data-view="users" class="nav-btn">Users &amp; positions</button>',
    )
    html_path.write_text(html, encoding="utf-8")
    print("Updated index.html hierarchy")
elif "role-legend" in html:
    print("index.html hierarchy already present")
else:
    print("WARN: could not find Users section text to patch — check index.html manually")

# Ensure userRoleInput exists
html = html_path.read_text(encoding="utf-8")
if 'id="userRoleInput"' not in html:
    print("WARN: userRoleInput missing — Job 62 may not be applied")

# --- 3) Service grant on role change ---
if svc_path.exists():
    svc = svc_path.read_text(encoding="utf-8")
    if "def set_job_role" in svc and "grant_all_agents_to_user" not in svc:
        svc = svc.replace(
            '''    db.commit()
    return {"user_id": target.id, "role": role_name}
''',
            '''    if role_name in {
        "reservation", "member", "manager", "contract_manager",
        "administration", "accounting", "ai_admin",
    }:
        try:
            from app.services.access import grant_all_agents_to_user
            grant_all_agents_to_user(db, company_id=company.id, user_id=target.id)
        except Exception:
            pass
    db.commit()
    return {"user_id": target.id, "role": role_name}
''',
            1,
        )
        svc_path.write_text(svc, encoding="utf-8")
        print("Updated company_onboarding.set_job_role")
    else:
        print("company_onboarding OK")

# --- 4) Docs ---
docs_dir.mkdir(parents=True, exist_ok=True)
(docs_dir / "04_users_roles_employees.md").write_text(
    """# Feature: Users, invitations & job positions

## Purpose
Owner adds employees and assigns a **job position**. Only the company **Owner** can invite or change positions.

## Frontend
- Nav: **Users & positions**
- Invite: email + job position → **Send invitation**
- Employee list: change position → **Save position**
- **Make AI administrator** shortcut
- Debug token when DEBUG=true → login gate **Accept invitation**

## Hierarchy
Owner → AI Administrator → Manager/Supervisor → operational roles (reservation, contract, accounting, administration, member)

## Backend
- `GET /companies/{id}/job-roles`
- `POST /companies/{id}/invitations` `{ email, role_name }`
- `PUT /companies/{id}/users/{id}/role` `{ role_name }`
- `POST /auth/accept-invitation`
""",
    encoding="utf-8",
)
print("docs ok")

# --- 5) Test ---
tests_path.write_text(
    '''"""Job 63 — users & job positions."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_app_js_syntax_btn_refresh_users():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert \'if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;\' in js
    assert \'if ($("btnRefreshUsers") $("btnRefreshUsers")\' not in js


def test_users_view_has_positions_ui():
    html = client.get("/workspace").text
    assert "userRoleInput" in html or "job position" in html.lower() or "Job position" in html
''',
    encoding="utf-8",
)
print("Wrote", tests_path.relative_to(ROOT))
print("\nDone. Run: pytest tests/test_users_positions_job63.py -q")
print("Then: Ctrl+F5 on /workspace")
