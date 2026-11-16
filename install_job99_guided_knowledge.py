#!/usr/bin/env python3
"""
Job 99 — Guided first knowledge upload for new owners.

After concierge chip "Upload knowledge" (or empty knowledge list):
- Banner explains why knowledge matters
- Highlights note form + document extract
- Clears when user successfully adds knowledge

Run from repo root:
  python install_job99_guided_knowledge.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"
APP = ROOT / "app" / "static" / "workspace" / "app.js"

BANNER_HTML = '''
        <div id="knowledgeGuideBanner" class="knowledge-guide hidden" role="region" aria-label="Getting started with knowledge">
          <div class="knowledge-guide-inner">
            <strong>First knowledge for your AI Employees</strong>
            <p class="muted">
              AI Employees answer from company knowledge. Add a policy, FAQ, or contract excerpt so chat stays accurate.
            </p>
            <ol class="knowledge-guide-steps">
              <li><strong>Quick note</strong> — paste a short policy below and click <em>Add knowledge</em>.</li>
              <li><strong>Or upload a file</strong> — PDF/DOCX/TXT via <em>Extract to knowledge</em>.</li>
              <li>Return to <strong>Chat</strong> and ask a question about what you added.</li>
            </ol>
            <button type="button" id="btnKnowledgeGuideDismiss" class="link-btn">Dismiss tip</button>
          </div>
        </div>
'''

CSS_BLOCK = '''
/* Job 99 — guided first knowledge */
.knowledge-guide {
  margin: 0 0 1rem;
  padding: 1rem 1.15rem;
  border-radius: 14px;
  border: 1px solid rgba(56, 189, 248, 0.35);
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.12), rgba(129, 140, 248, 0.1));
  color: #e2e8f0;
}
.knowledge-guide.hidden { display: none !important; }
.knowledge-guide-inner strong { display: block; font-size: 1rem; margin-bottom: 0.35rem; color: #f8fafc; }
.knowledge-guide-steps {
  margin: 0.6rem 0 0.5rem 1.1rem;
  padding: 0;
  color: #cbd5e1;
  font-size: 0.88rem;
  line-height: 1.45;
}
.knowledge-guide-steps li { margin-bottom: 0.25rem; }
.knowledge-guide .link-btn {
  background: none;
  border: none;
  color: #7dd3fc;
  cursor: pointer;
  padding: 0;
  font-size: 0.82rem;
  text-decoration: underline;
}
#knowledgeNoteCard.guide-highlight,
#knowledgeWriteCard.guide-highlight {
  outline: 2px solid rgba(56, 189, 248, 0.55);
  outline-offset: 2px;
  border-radius: 12px;
}
'''


def patch_html():
    t = HTML.read_text(encoding="utf-8")
    if "knowledgeGuideBanner" in t:
        print("[OK] banner already in HTML")
        return
    # Insert after opening of view-knowledge content — find view-knowledge section
    m = re.search(r'(<section id="view-knowledge" class="view">\s*)', t)
    if not m:
        # try without class order
        m = re.search(r'(<section[^>]*id="view-knowledge"[^>]*>\s*)', t)
    if not m:
        raise SystemExit("view-knowledge section not found")
    # Prefer insert after first toolbar/header inside the view
    # Look for btnRefreshKnowledge block end
    anchor = t.find('id="btnRefreshKnowledge"')
    if anchor > 0:
        # find closing of that header row — after next </div> following toolbar
        insert_at = t.find("</div>", t.find("</div>", anchor) + 1)
        if insert_at < 0:
            insert_at = m.end()
        else:
            insert_at = insert_at + len("</div>")
        t = t[:insert_at] + "\n" + BANNER_HTML + t[insert_at:]
    else:
        t = t[: m.end()] + BANNER_HTML + t[m.end() :]
    HTML.write_text(t, encoding="utf-8")
    print("[OK] knowledge guide banner HTML")


def patch_css():
    t = CSS.read_text(encoding="utf-8")
    if "Job 99 — guided first knowledge" in t:
        print("[OK] CSS already")
        return
    CSS.write_text(t.rstrip() + "\n\n" + CSS_BLOCK, encoding="utf-8")
    print("[OK] CSS guide banner")


def patch_app_js():
    t = APP.read_text(encoding="utf-8")

    helpers = r'''
  // Job 99 — guided first knowledge
  function knowledgeGuideKey() {
    return "knowledge_guide_done:" + (state.companyId || "x");
  }
  function shouldShowKnowledgeGuide() {
    try {
      if (localStorage.getItem(knowledgeGuideKey()) === "1") return false;
    } catch (_) {}
    try {
      if (sessionStorage.getItem("knowledge_guide_force") === "1") return true;
    } catch (_) {}
    return true; // show until dismissed or first successful add
  }
  function setKnowledgeGuideVisible(show) {
    const banner = $("knowledgeGuideBanner");
    if (!banner) return;
    banner.classList.toggle("hidden", !show);
    ["knowledgeNoteCard", "knowledgeWriteCard"].forEach((id) => {
      const el = $(id);
      if (el) el.classList.toggle("guide-highlight", !!show);
    });
  }
  function openKnowledgeGuided() {
    try { sessionStorage.setItem("knowledge_guide_force", "1"); } catch (_) {}
    showView("knowledge");
    setKnowledgeGuideVisible(shouldShowKnowledgeGuide());
    const title = $("knowTitle") || $("knowledgeIngestTitle");
    if (title) {
      try { title.focus(); } catch (_) {}
    }
  }
  function markKnowledgeGuideDone() {
    try { localStorage.setItem(knowledgeGuideKey(), "1"); } catch (_) {}
    try { sessionStorage.removeItem("knowledge_guide_force"); } catch (_) {}
    setKnowledgeGuideVisible(false);
  }
  if ($("btnKnowledgeGuideDismiss")) {
    $("btnKnowledgeGuideDismiss").onclick = () => markKnowledgeGuideDone();
  }
'''

    if "function openKnowledgeGuided" not in t:
        # insert before showView definition or after setConnected
        if "  function showView(name) {" in t:
            t = t.replace("  function showView(name) {", helpers + "\n  function showView(name) {", 1)
        else:
            raise SystemExit("showView not found")

    # Enhance showView knowledge branch
    old_k = 'if (name === "knowledge") { applyKnowledgeWriteGating(); loadKnowledge(); }'
    new_k = (
        'if (name === "knowledge") { applyKnowledgeWriteGating(); loadKnowledge(); '
        "setKnowledgeGuideVisible(shouldShowKnowledgeGuide()); }"
    )
    if old_k in t and "setKnowledgeGuideVisible(shouldShowKnowledgeGuide())" not in t:
        t = t.replace(old_k, new_k, 1)
        print("[OK] showView knowledge shows guide")
    elif "setKnowledgeGuideVisible(shouldShowKnowledgeGuide())" in t:
        print("[OK] showView knowledge already guided")
    else:
        # flexible
        t2, n = re.subn(
            r'if \(name === ["\']knowledge["\']\) \{[^}]*loadKnowledge\(\);?\s*\}',
            'if (name === "knowledge") { applyKnowledgeWriteGating(); loadKnowledge(); setKnowledgeGuideVisible(shouldShowKnowledgeGuide()); }',
            t,
            count=1,
        )
        if n == 1:
            t = t2
            print("[OK] showView knowledge (regex)")
        else:
            print("[WARN] knowledge showView branch not patched")

    # Wire concierge action to openKnowledgeGuided
    if "openKnowledgeGuided()" not in t:
        t = t.replace(
            "if (action === 'knowledge') showView('knowledge');",
            "if (action === 'knowledge') openKnowledgeGuided();",
            1,
        )
        print("[OK] concierge → openKnowledgeGuided")

    # After successful add knowledge — mark guide done
    # Find btnAddKnowledge handlers
    if "markKnowledgeGuideDone" not in t.split("btnAddKnowledge")[-1][:800] if "btnAddKnowledge" in t else True:
        # patch common success patterns after add knowledge
        patterns = [
            (
                'if (log) log.textContent = "Knowledge added',
                'markKnowledgeGuideDone();\n        if (log) log.textContent = "Knowledge added',
            ),
        ]
        # broader: after successful POST knowledge
        t2, n = re.subn(
            r'(btnAddKnowledge[\s\S]{0,1200}?await api\([^\)]*knowledge[^\)]*\)[\s\S]{0,400}?)(loadKnowledge\(\))',
            r'\1markKnowledgeGuideDone();\n        \2',
            t,
            count=1,
            flags=re.I,
        )
        if n == 1:
            t = t2
            print("[OK] add knowledge marks guide done")
        else:
            # try ingest button
            t3, n3 = re.subn(
                r'(btnKnowledgeIngest[\s\S]{0,1500}?)(loadKnowledge\(\))',
                r'\1markKnowledgeGuideDone();\n        \2',
                t,
                count=1,
            )
            if n3 == 1:
                t = t3
                print("[OK] ingest marks guide done")
            else:
                print("[WARN] could not auto-hook markKnowledgeGuideDone on add — dismiss still works")

    APP.write_text(t, encoding="utf-8")
    print("[OK] app.js Job 99 helpers")


def bump_cache():
    t = HTML.read_text(encoding="utf-8")
    t2 = re.sub(
        r'(src="/workspace/assets/(?:app|chat|home|inbox|results|sidebar)\.js)\?v=[^"]*"',
        r'\1?v=20261026-job99"',
        t,
    )
    if t2 != t:
        HTML.write_text(t2, encoding="utf-8")
        print("[OK] cache-bust v=20261026-job99")


def main():
    print("Job 99 — Guided first knowledge")
    print("ROOT:", ROOT)
    if not HTML.exists():
        raise SystemExit("run from repo root")
    patch_html()
    patch_css()
    patch_app_js()
    bump_cache()
    print(
        """
Verify:
  1. Ctrl+Shift+R
  2. Chat → concierge chip "Upload knowledge" → Knowledge view + blue guide banner
  3. Add a note → banner dismisses
  4. Or Dismiss tip

  git add app/static/workspace/index.html app/static/workspace/styles.css app/static/workspace/app.js
  git commit -m "Job 99: guided first knowledge upload for new owners"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
