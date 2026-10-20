"""Install Job 73 from repo root: python install_job73_results_governance.py"""
from pathlib import Path
import sys

ROOT = Path.cwd()
if not (ROOT / "app/static/workspace/index.html").exists():
    sys.exit("Run from repo root (folder with app/)")

html_path = ROOT / "app/static/workspace/index.html"
html = html_path.read_text(encoding="utf-8")
changed = False

def sub(old, new, label):
    global html, changed
    if old in html:
        html = html.replace(old, new)
        print(label, "OK")
        changed = True
    elif "Plan &amp; usage" in html and label == "usage":
        print(label, "already")
    elif "Governance overview" in html and label == "governance":
        print(label, "already")
    else:
        print(label, "WARN not matched")

sub(
"""      <section id=\"view-usage\" class=\"view\">
        <div class=\"card\">
          <div class=\"row between\">
            <h2>Plan & usage</h2>
            <button id=\"btnRefreshUsage\" class=\"secondary\">Refresh</button>
          </div>
          <div id=\"usageStats\" class=\"stats\"></div>
          <pre id=\"usageDetail\" class=\"log\"></pre>
        </div>
      </section>
""",
"""      <section id=\"view-usage\" class=\"view\">
        <p class=\"home-notice\" role=\"status\">
          <strong>Plan &amp; usage</strong> shows quota and consumption for this company.
          Visible to Owner and roles with <code>usage.read</code> (e.g. Administration, Accounting).
        </p>
        <div class=\"card\">
          <div class=\"row between\">
            <h2>Plan & usage</h2>
            <button id=\"btnRefreshUsage\" class=\"secondary\">Refresh</button>
          </div>
          <div id=\"usageStats\" class=\"stats\"></div>
          <pre id=\"usageDetail\" class=\"log\"></pre>
        </div>
      </section>
""",
"usage",
)

sub(
"""      <section id=\"view-governance\" class=\"view\">
        <div class=\"card\">
          <div class=\"row between\">
            <h2>Governance</h2>
            <button id=\"btnRefreshGov\" class=\"secondary\">Refresh</button>
          </div>
          <div id=\"govStats\" class=\"stats\"></div>
          <div class=\"grid-2\">
            <div>
              <h3>Agents</h3>
              <div id=\"govAgents\" class=\"list\"></div>
            </div>
            <div>
              <h3>Recent audit</h3>
              <div id=\"govAudit\" class=\"list\"></div>
            </div>
          </div>
        </div>
      </section>
""",
"""      <section id=\"view-governance\" class=\"view\">
        <p class=\"home-notice\" role=\"status\">
          <strong>Governance</strong> is the Owner/manager overview: AI workforce health, recent audit events, and control signals.
          For day-to-day approvals use <strong>Inbox</strong> / <strong>Approvals</strong>. Full event history is under <strong>Audit log</strong>.
        </p>
        <div class=\"card\">
          <div class=\"row between\">
            <h2>Governance overview</h2>
            <button id=\"btnRefreshGov\" class=\"secondary\">Refresh</button>
          </div>
          <div id=\"govStats\" class=\"stats\"></div>
          <div class=\"grid-2\">
            <div>
              <h3>Agents</h3>
              <div id=\"govAgents\" class=\"list\"></div>
            </div>
            <div>
              <h3>Recent audit</h3>
              <div id=\"govAudit\" class=\"list\"></div>
            </div>
          </div>
        </div>
      </section>
""",
"governance",
)

if 'aria-label="Work results"' not in html:
    if '<aside id="outputCenter" class="output-center">' in html:
        html = html.replace(
            '<aside id="outputCenter" class="output-center">',
            '<aside id="outputCenter" class="output-center" aria-label="Work results">',
            1,
        )
        changed = True
        print("outputCenter OK")

if changed:
    html_path.write_text(html, encoding="utf-8")

rj = ROOT / "app/static/workspace/results.js"
if rj.exists():
    t = rj.read_text(encoding="utf-8")
    if "Run a Task execute" not in t:
        t = t.replace(
            "No matching results.",
            "No matching results. Run a Task (execute) to produce quotations, availability, or reservations.",
        )
        t = t.replace(
            'message("No results loaded.");',
            'message("No results loaded. Complete a task with tools, then open Results from Home or the output panel.");',
        )
        rj.write_text(t, encoding="utf-8")
        print("results.js OK")

docs = ROOT / "docs/features"
docs.mkdir(parents=True, exist_ok=True)
(docs / "16_results_governance.md").write_text(
    """# Feature: Results, Governance & Usage

## Results (Output center)
Structured outputs from **Task execute**: quotations, availability, reservations.

Chat advisory mode does not write tool results here.

## Governance
Owner overview (`governance.read`): agents, recent audit. Day-to-day gates: Approvals / Inbox.

## Plan & usage
Quota consumption (`usage.read`).

## Flow
```
Task execute → (approval) → Results → Governance/Audit
```
""",
    encoding="utf-8",
)
(docs / "17_MVP_QA_CHECKLIST.md").write_text(
    """# MVP QA checklist

## Auth & company
- [ ] Register → verify → login → company profile unlocks nav
- [ ] Owner invites AI Admin + Reservation; accept works

## Workforce & data
- [ ] Hire AI Employee; grant can_use
- [ ] Knowledge extract; inventory seed
- [ ] Marketplace install; policies allow/require_approval

## Work loop
- [ ] Home role actions; Chat advisory; Tasks execute
- [ ] Approvals gated; Results show tool output
- [ ] Notifications / Inbox

See also: 00_PRODUCT_WALKTHROUGH.md
""",
    encoding="utf-8",
)
readme = docs / "README.md"
if readme.exists():
    r = readme.read_text(encoding="utf-8")
    if "16_results" not in r:
        readme.write_text(
            r.rstrip()
            + "\n| 16 | Results, Governance & Usage | [16](16_results_governance.md) |\n"
            + "| 17 | MVP QA checklist | [17](17_MVP_QA_CHECKLIST.md) |\n",
            encoding="utf-8",
        )
        print("README OK")

(ROOT / "tests").mkdir(exist_ok=True)
(ROOT / "tests/test_results_governance_job73.py").write_text(
    '''"""Job 73 tests."""
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
''',
    encoding="utf-8",
)
print("Done. pytest tests/test_results_governance_job73.py -q")
