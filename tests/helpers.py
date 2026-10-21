"""Shared fixtures for auth-hardened API tests.

Company self-service create is locked; use demo bootstrap (DEBUG/dev) or
platform-admin provision. Prefer these helpers instead of POST /api/v1/companies.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

DEMO_PASSWORD = "demo12345"


def bootstrap_demo(client: TestClient, *, hire_agents: bool = True) -> dict[str, Any]:
    # FastAPI: hire_agents is a *query* param on POST /demo/bootstrap (not JSON body)
    res = client.post(
        "/api/v1/demo/bootstrap",
        params={"hire_agents": str(hire_agents).lower()},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("company_id"), body
    assert body.get("owner_email"), body
    return body


def login_headers(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    tok = res.json()
    headers = {
        "Authorization": f"Bearer {tok['access_token']}",
        "X-User-ID": tok["user_id"],
    }
    return headers


def provision_company(client: TestClient, *, role: str = "owner", hire_agents: bool = True) -> tuple[str, str, dict[str, str], dict]:
    """Return (company_id, user_id, headers, demo_body) for a persona.

    role: owner | ai_admin | reservation | manager | contract_manager | administration | member
    """
    demo = bootstrap_demo(client, hire_agents=hire_agents)
    users = demo.get("users") or []
    person = next((u for u in users if u.get("role") == role), None)
    if person is None and role == "owner":
        email = demo["owner_email"]
        uid = demo.get("owner_user_id") or demo.get("user_id")
    elif person is None:
        # fallback owner
        email = demo["owner_email"]
        person = next((u for u in users if u.get("role") == "owner"), None)
        uid = person["id"] if person else demo.get("owner_user_id")
    else:
        email = person["email"]
        uid = person["id"]
    headers = login_headers(client, email)
    if not uid:
        uid = headers["X-User-ID"]
    # ensure X-User-ID matches login
    headers["X-User-ID"] = headers.get("X-User-ID") or uid
    return demo["company_id"], headers["X-User-ID"], headers, demo


def owner_setup(client: TestClient) -> tuple[str, str, dict[str, str]]:
    """Legacy-compatible: (company_id, owner_id, headers)."""
    cid, uid, headers, _ = provision_company(client, role="owner")
    return cid, uid, headers

# Job 86: any local setup() that calls provision_company must RETURN headers
# e.g. return company_id, owner_id, agent_id, headers


def persona_headers(client: TestClient, demo: dict, role: str) -> tuple[str, dict[str, str]]:
    """Login as a bootstrap persona role; return (user_id, headers)."""
    users = demo.get("users") or []
    person = next((u for u in users if u.get("role") == role), None)
    if person is None:
        raise AssertionError(f"persona role {role!r} missing from bootstrap users")
    headers = login_headers(client, person["email"])
    return headers["X-User-ID"], headers
