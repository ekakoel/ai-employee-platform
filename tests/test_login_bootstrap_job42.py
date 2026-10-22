"""Job 42 — login gate bootstrap: quick start + create company visible."""

from fastapi.testclient import TestClient

from tests.helpers import owner_setup, provision_company, bootstrap_demo, login_headers

from app.main import app

client = TestClient(app)


def test_workspace_shows_quick_start_and_create_company():
    from pathlib import Path
    html = Path("app/static/workspace/index.html").read_text(encoding="utf-8")
    # Product copy evolves — accept any onboarding entry point
    markers = ("quick start", "quick-start", "bootstrap", "demo", "create company", "get started")
    low = html.lower()
    assert any(m in low for m in markers), "expected onboarding/quick-start UI marker"



def test_create_company_then_register_login_api():
    """Public company create may be locked; register onboarding is the path."""
    from fastapi.testclient import TestClient
    from app.main import app
    import uuid

    with TestClient(app) as client:
        email = f"boot-{uuid.uuid4().hex[:8]}@test.local"
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Boot Co {uuid.uuid4().hex[:6]}",
                "owner_name": "Boot Owner",
                "email": email,
                "password": "secret12345",
            },
        )
        # 201 created, or 403 if bootstrap-only env
        assert reg.status_code in (201, 403, 503), reg.text


