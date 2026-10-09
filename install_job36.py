#!/usr/bin/env python3
"""Job 36 installer — Users & Roles admin (idempotent).
Run from repo root:
  python install_job36.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path.cwd()


def must_exist(*parts: str) -> Path:
    p = ROOT.joinpath(*parts)
    if not p.exists():
        sys.exit(f"Missing {p} — run from repo root (Job 35 should already be applied)")
    return p


def patch_schema() -> None:
    p = must_exist("app", "schemas", "domain.py")
    t = p.read_text(encoding="utf-8")
    if "class UserRoleUpdate" in t and "role name for UI" in t:
        print("schema: already done")
        return
    if "class UserRead" not in t:
        sys.exit("UserRead not found in domain.py")
    block = t.split("class UserRead", 1)[1].split("class ", 1)[0]
    if "role: str | None = None" not in block:
        t = t.replace(
            "    role_id: str\n    department_id: str | None = None\n    status: str\n"
            "    is_platform_admin: bool = False\n    created_at: datetime\n",
            "    role_id: str\n    role: str | None = None  # role name for UI (Job 36)\n"
            "    department_id: str | None = None\n    status: str\n"
            "    is_platform_admin: bool = False\n    created_at: datetime\n",
            1,
        )
    if "class UserRoleUpdate" not in t:
        t = t.replace(
            "class AgentCatalogRead(BaseModel):",
            "class UserRoleUpdate(BaseModel):\n"
            "    role: str = Field(min_length=2, max_length=100)\n\n\n"
            "class AgentCatalogRead(BaseModel):",
            1,
        )
    p.write_text(t, encoding="utf-8")
    print("schema: updated")


def patch_routes() -> None:
    p = must_exist("app", "api", "routes.py")
    t = p.read_text(encoding="utf-8")
    if "def list_company_users" in t and "def user_to_read" in t:
        print("routes: already done")
        return

    if "UserRoleUpdate" not in t:
        if "UserCreate," in t:
            t = t.replace("UserCreate,", "UserCreate, UserRoleUpdate,", 1)
        else:
            t = "from app.schemas.domain import UserRoleUpdate  # Job 36\n" + t

    if "def user_to_read" not in t:
        marker = "def require_permission("
        helper = (
            "def user_to_read(user: User) -> UserRead:\n"
            '    """Serialize User with resolved role name for UI."""\n'
            "    data = UserRead.model_validate(user)\n"
            "    role_name = user.role.name if user.role is not None else None\n"
            '    return data.model_copy(update={"role": role_name})\n\n\n'
        )
        if marker not in t:
            sys.exit("require_permission not found")
        t = t.replace(marker, helper + marker, 1)

    list_block = '''
@router.get(
    "/companies/{company_id}/users",
    response_model=list[UserRead],
)
def list_company_users(
    company_id: str,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """List company users (Job 36 — team admin)."""
    user = require_company_user(db, company_id, x_user_id)
    require_permission(user, "team.manage")
    rows = list(
        db.scalars(
            select(User)
            .where(User.company_id == company_id)
            .order_by(User.created_at.asc())
        ).all()
    )
    for u in rows:
        _ = u.role
    return [user_to_read(u) for u in rows]


@router.patch(
    "/companies/{company_id}/users/{user_id}",
    response_model=UserRead,
)
def update_company_user_role(
    company_id: str,
    user_id: str,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Change a company user's role (owner / team.manage only)."""
    from app.services.seed import VALID_COMPANY_ROLES

    actor = require_company_user(db, company_id, x_user_id)
    require_permission(actor, "team.manage")
    target = db.scalar(
        select(User).where(User.id == user_id, User.company_id == company_id)
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    role_name = payload.role if payload.role in VALID_COMPANY_ROLES else None
    if not role_name:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")
    role = get_or_create_role(db, role_name)
    target.role_id = role.id
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user_id=actor.id,
        action="user.role_update",
        resource_type="user",
        resource_id=target.id,
        status="success",
        details={"role": role_name},
    )
    db.commit()
    db.refresh(target)
    _ = target.role
    return user_to_read(target)


'''

    if "def list_company_users" not in t:
        token = '"/agent-catalog"'
        if token not in t:
            t = t + "\n" + list_block
        else:
            ridx = t.rfind("@router.get", 0, t.find(token))
            if ridx < 0:
                sys.exit("could not locate agent-catalog route")
            t = t[:ridx] + list_block + t[ridx:]

    if "return user_to_read(user)" not in t:
        t = t.replace(
            "    db.commit()\n    db.refresh(user)\n\n    return user\n",
            "    db.commit()\n    db.refresh(user)\n    _ = user.role\n\n"
            "    return user_to_read(user)\n",
            1,
        )

    p.write_text(t, encoding="utf-8")
    print("routes: updated")


def patch_html() -> None:
    p = must_exist("app", "static", "workspace", "index.html")
    t = p.read_text(encoding="utf-8")
    if 'data-view="users"' not in t:
        t = t.replace(
            '<button data-view="departments" class="nav-btn">Departments</button>',
            '<button data-view="users" class="nav-btn">Users & Roles</button>\n'
            '        <button data-view="departments" class="nav-btn">Departments</button>',
            1,
        )
    if 'id="view-users"' not in t:
        section = """
      <section id="view-users" class="view">
        <div class="card">
          <h2>Users &amp; roles</h2>
          <p class="muted">Invite company members and assign roles (owner, ai_admin, manager, reservation, member).</p>
          <div class="grid-2">
            <label>Name
              <input id="userNameInput" placeholder="Full name" />
            </label>
            <label>Email
              <input id="userEmailInput" placeholder="user@company.com" />
            </label>
            <label>Role
              <select id="userRoleInput">
                <option value="reservation">reservation</option>
                <option value="member">member</option>
                <option value="manager">manager</option>
                <option value="ai_admin">ai_admin</option>
                <option value="owner">owner</option>
              </select>
            </label>
            <label>Password
              <input id="userPasswordInput" type="password" placeholder="min 8 characters" value="demo12345" />
            </label>
          </div>
          <div class="row">
            <button id="btnCreateUser" class="primary">Create user</button>
            <button id="btnRefreshUsers" class="secondary">Refresh</button>
          </div>
          <pre id="userAdminLog" class="log hidden-log"></pre>
          <div id="usersList" class="list"></div>
        </div>
      </section>
"""
        if 'id="view-departments"' in t:
            t = t.replace(
                '<section id="view-departments" class="view">',
                section + '\n      <section id="view-departments" class="view">',
                1,
            )
        else:
            t = t.replace("</main>", section + "\n    </main>", 1)
    p.write_text(t, encoding="utf-8")
    print("html: updated")


def patch_js() -> None:
    p = must_exist("app", "static", "workspace", "app.js")
    t = p.read_text(encoding="utf-8")

    if 'users: ["team.manage"]' not in t:
        t = t.replace(
            'departments: ["agent.manage", "team.manage"]',
            'users: ["team.manage"],\n    departments: ["agent.manage", "team.manage"]',
            1,
        )

    if 'users: ["Users & Roles"' not in t:
        t = t.replace(
            'departments: ["Departments"',
            'users: ["Users & Roles", "Company members and role assignment"],\n    departments: ["Departments"',
            1,
        )

    if 'name === "users"' not in t:
        t = t.replace(
            'if (name === "departments") loadDepartments();',
            'if (name === "users") loadUsers();\n    if (name === "departments") loadDepartments();',
            1,
        )

    if "async function loadUsers" not in t:
        block = r"""
  async function loadUsers() {
    if (!state.companyId) return;
    try {
      const list = await api(`/companies/${state.companyId}/users`);
      $("usersList").innerHTML =
        (list || [])
          .map(
            (u) => `<div class="item">
          <strong>${escapeHtml(u.name)}</strong>
          <div class="meta">${escapeHtml(u.email)} · role: <code>${escapeHtml(u.role || u.role_id)}</code> · ${escapeHtml(u.status || "")}</div>
          <div class="row" style="margin-top:.35rem">
            <select data-user-role="${escapeHtml(u.id)}">
              ${["owner","ai_admin","manager","reservation","member"].map((r) =>
                `<option value="${r}" ${u.role === r ? "selected" : ""}>${r}</option>`
              ).join("")}
            </select>
            <button class="secondary btn-set-role" data-id="${escapeHtml(u.id)}">Update role</button>
          </div>
        </div>`
          )
          .join("") || `<div class="empty">No users.</div>`;
      document.querySelectorAll(".btn-set-role").forEach((b) => {
        b.onclick = async () => {
          const sel = document.querySelector(`select[data-user-role="${b.dataset.id}"]`);
          try {
            await api(`/companies/${state.companyId}/users/${b.dataset.id}`, {
              method: "PATCH",
              body: JSON.stringify({ role: sel.value }),
            });
            loadUsers();
          } catch (err) {
            alert(err.message);
          }
        };
      });
    } catch (err) {
      $("usersList").innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
    }
  }
  if ($("btnRefreshUsers")) $("btnRefreshUsers").onclick = loadUsers;
  if ($("btnCreateUser"))
    $("btnCreateUser").onclick = async () => {
      const log = $("userAdminLog");
      try {
        const body = await api(`/companies/${state.companyId}/users`, {
          method: "POST",
          body: JSON.stringify({
            name: ($("userNameInput").value || "").trim() || "New User",
            email: ($("userEmailInput").value || "").trim(),
            role: $("userRoleInput").value || "member",
            password: ($("userPasswordInput").value || "demo12345"),
          }),
        });
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = "Created " + body.email + " as " + (body.role || "");
        }
        $("userEmailInput").value = "";
        loadUsers();
      } catch (err) {
        if (log) {
          log.classList.remove("hidden-log");
          log.textContent = err.message;
        }
      }
    };

"""
        if "async function loadDepartments" in t:
            t = t.replace(
                "async function loadDepartments",
                block + "async function loadDepartments",
                1,
            )
        else:
            t = t + "\n" + block

    if "aiadmin@demo.local" not in t:
        seed = r"""
      // Seed persona users for role testing (Job 36)
      for (const [role, email] of [
        ["ai_admin", "aiadmin@demo.local"],
        ["reservation", "reservation@demo.local"],
        ["manager", "manager@demo.local"],
      ]) {
        try {
          await api(`/companies/${co.id}/users`, {
            method: "POST",
            body: JSON.stringify({
              name: role.replace("_", " "),
              email,
              role,
              password: "demo12345",
            }),
          });
          log.textContent += "\nUser " + email + " (" + role + ")";
        } catch (e) {
          log.textContent += "\nUser " + email + ": " + e.message;
        }
      }
"""
        inserted = False
        for marker in (
            'log.textContent += "\\n\\nWorkspace ready',
            'log.textContent += "\n\nWorkspace ready',
        ):
            if marker in t:
                t = t.replace(marker, seed + "\n      " + marker, 1)
                inserted = True
                break
        if not inserted:
            print("js: WARN quick-start seed marker not found (UI still works)")

    p.write_text(t, encoding="utf-8")
    print("js: updated")


def write_tests() -> None:
    p = ROOT / "tests" / "test_users_roles_job36.py"
    p.write_text(
        '''"""Job 36 — list/update company users, role name on UserRead."""

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _owner_company():
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"Co36 {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co["id"]}/users",
        json={
            "name": "Owner",
            "email": f"owner-{suffix}@job36.test",
            "role": "owner",
            "password": "demo12345",
        },
    ).json()
    return co["id"], owner["id"]


def test_list_users_requires_team_manage():
    company_id, owner_id = _owner_company()
    res = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": owner_id},
        json={
            "name": "Res",
            "email": f"res-{uuid.uuid4().hex[:6]}@job36.test",
            "role": "reservation",
            "password": "demo12345",
        },
    )
    assert res.status_code in (200, 201), res.text
    res_id = res.json()["id"]
    assert res.json().get("role") == "reservation"

    denied = client.get(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": res_id},
    )
    assert denied.status_code == 403

    ok = client.get(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": owner_id},
    )
    assert ok.status_code == 200, ok.text
    assert len(ok.json()) >= 2
    assert any(u.get("role") == "owner" for u in ok.json())


def test_patch_user_role():
    company_id, owner_id = _owner_company()
    member = client.post(
        f"/api/v1/companies/{company_id}/users",
        headers={"X-User-ID": owner_id},
        json={
            "name": "Member",
            "email": f"mem-{uuid.uuid4().hex[:6]}@job36.test",
            "role": "member",
            "password": "demo12345",
        },
    ).json()
    patched = client.patch(
        f"/api/v1/companies/{company_id}/users/{member["id"]}",
        headers={"X-User-ID": owner_id},
        json={"role": "ai_admin"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["role"] == "ai_admin"


def test_users_nav_in_workspace():
    html = client.get("/workspace").content
    assert b'data-view="users"' in html
    assert b"view-users" in html
''',
        encoding="utf-8",
    )
    print(f"tests: wrote {p}")


def main() -> None:
    print(f"Installing Job 36 in {ROOT}")
    patch_schema()
    patch_routes()
    patch_html()
    patch_js()
    write_tests()
    print("Done.")
    print("  pytest tests/test_users_roles_job36.py -q")
    print("  uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
