"""Job 64 — AI admin / administration can invite; nav gated by permission."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _bootstrap():
    res = client.post("/api/v1/demo/bootstrap")
    assert res.status_code == 200, res.text
    return res.json()


def _login(email: str):
    tok = client.post("/api/v1/auth/login", json={"email": email, "password": "demo12345"})
    assert tok.status_code == 200, tok.text
    body = tok.json()
    return {
        "Authorization": f"Bearer {body['access_token']}",
        "X-User-ID": body["user_id"],
    }


def test_ai_admin_can_invite_reservation():
    demo = _bootstrap()
    admin = next(u for u in demo["users"] if u["role"] == "ai_admin")
    headers = _login(admin["email"])
    res = client.post(
        f"/api/v1/companies/{demo['company_id']}/invitations",
        headers=headers,
        json={"email": "newres@example.test", "role_name": "reservation"},
    )
    assert res.status_code == 201, res.text
    assert res.json().get("role_name") == "reservation"


def test_ai_admin_cannot_invite_ai_admin():
    demo = _bootstrap()
    admin = next(u for u in demo["users"] if u["role"] == "ai_admin")
    headers = _login(admin["email"])
    res = client.post(
        f"/api/v1/companies/{demo['company_id']}/invitations",
        headers=headers,
        json={"email": "otheradmin@example.test", "role_name": "ai_admin"},
    )
    assert res.status_code in (400, 403), res.text


def test_reservation_cannot_invite():
    demo = _bootstrap()
    res_user = next(u for u in demo["users"] if u["role"] == "reservation")
    headers = _login(res_user["email"])
    res = client.post(
        f"/api/v1/companies/{demo['company_id']}/invitations",
        headers=headers,
        json={"email": "x@example.test", "role_name": "member"},
    )
    assert res.status_code == 403, res.text


def test_users_nav_requires_team_manage():
    from pathlib import Path
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert 'users: ["team.manage"]' in js or "users: ['team.manage']" in js
