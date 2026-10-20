"""Job 76 — company profile role-based edit vs read-only UI."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_company_profile_has_edit_and_read_blocks():
    html = client.get("/workspace").text
    assert 'id="view-company"' in html
    assert 'id="companyProfileEdit"' in html
    assert 'id="companyProfileRead"' in html
    assert 'id="btnSaveCompanyProfile"' in html
    assert 'id="companyReadName"' in html


def test_app_js_applies_owner_mode():
    js = Path("app/static/workspace/app.js").read_text(encoding="utf-8")
    assert "applyCompanyProfileMode" in js
    assert "isCompanyProfileOwner" in js
    assert "companyProfileEdit" in js
    assert "companyProfileRead" in js
