"""Job 73 tests."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_views():
    html = client.get("/workspace").text
    assert 'id="view-governance"' in html
    assert 'id="view-usage"' in html

def test_docs():
    assert Path("docs/features/16_results_governance.md").is_file()
    assert Path("docs/features/17_MVP_QA_CHECKLIST.md").is_file()
