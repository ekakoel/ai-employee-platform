"""Job 62 — invite with job position + list roles."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _owner_session():
    demo = client.post("/api/v1/demo/bootstrap")
    assert demo.status_code == 200, demo.text
    body = demo.json()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": body["owner_email"], "password": "demo12345"},
    )
    assert login.status_code == 200, login.text
    tok = login.json()
    return body["company_id"], {
        "Authorization": f"Bearer {tok['access_token']}",
        "X-User-ID": tok["user_id"],
    }


def test_list_job_roles():
    company_id, headers = _owner_session()
    res = client.get(f"/api/v1/companies/{company_id}/job-roles", headers=headers)
    assert res.status_code == 200, res.text
    names = {r["name"] for r in res.json()["roles"]}
    assert "owner" not in names
    assert "reservation" in names
    assert "ai_admin" in names


def test_invite_with_role_name():
    company_id, headers = _owner_session()
    res = client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers=headers,
        json={"email": "newhire@example.test", "role_name": "reservation"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body.get("role_name") == "reservation"
    inv = client.get(f"/api/v1/companies/{company_id}/invitations", headers=headers)
    assert inv.status_code == 200
    rows = inv.json()
    assert any(r.get("email") == "newhire@example.test" and r.get("role_name") == "reservation" for r in rows)


def test_users_ui_has_job_position_select():
    html = client.get("/workspace").text
    assert "userRoleInput" in html
    assert "Job position" in html or "job position" in html.lower()
