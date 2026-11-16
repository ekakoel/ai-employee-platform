#!/usr/bin/env python3
"""
Job 100 fix:
1) Concierge chips do nothing — bindConciergeChips() was OUTSIDE render()
   so it never ran after messages painted.
2) knowledge/ingest-extract 500 — OCR/tesseract failures and other extract
   errors were uncaught (only ValueError → 400).

Run from repo root, then hard-refresh + restart uvicorn.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
CHAT = ROOT / "app" / "static" / "workspace" / "chat.js"
APP = ROOT / "app" / "static" / "workspace" / "app.js"
EXTRACTOR = ROOT / "app" / "knowledge" / "extractor.py"
ROUTES = ROOT / "app" / "api" / "routes.py"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
CACHE = "20261026-job100"


def fix_chat_chips():
    t = CHAT.read_text(encoding="utf-8")
    # Broken pattern: close render then call bind outside
    broken = "    }      bindConciergeChips(document);"
    fixed = "      bindConciergeChips(thread);\n    }"
    if broken in t:
        t = t.replace(broken, fixed, 1)
        print("[OK] moved bindConciergeChips inside render()")
    elif "bindConciergeChips(thread)" in t or re.search(
        r"controls\(\);\s*\n\s*bindConciergeChips", t
    ):
        print("[OK] bind already inside render")
    else:
        # insert before closing of render if bind exists only outside
        t2, n = re.subn(
            r"(function render\(scroll = true\) \{[\s\S]*?controls\(\);\s*)\n    \}",
            r"\1\n      bindConciergeChips(thread);\n    }",
            t,
            count=1,
        )
        if n == 1:
            t = t2
            # remove stray outside call
            t = t.replace("      bindConciergeChips(document);\n", "")
            t = t.replace("    bindConciergeChips(document);\n", "")
            print("[OK] injected bindConciergeChips before end of render")
        else:
            print("[WARN] could not auto-place bindConciergeChips")

    # Event delegation backup on chatThread (survives re-renders)
    if "chatThreadConciergeDelegate" not in t:
        delegate = '''
    // Job 100 — event delegation so chips always respond after re-render
    (function chatThreadConciergeDelegate() {
      const thread = document.getElementById("chatThread");
      if (!thread || thread.dataset.conciergeDelegate === "1") return;
      thread.dataset.conciergeDelegate = "1";
      thread.addEventListener("click", (ev) => {
        const btn = ev.target && ev.target.closest ? ev.target.closest(".concierge-chip") : null;
        if (!btn) return;
        ev.preventDefault();
        const action = btn.getAttribute("data-concierge");
        markTourEngaged();
        if (action === "ask") {
          if ($("chatInput")) {
            $("chatInput").value = "What should I do first as company owner?";
            $("chatInput").focus();
            controls();
          }
          return;
        }
        if (typeof onConciergeAction === "function") onConciergeAction(action);
      });
    })();
'''
        # after bindConciergeChips function definition
        t = t.replace(
            "    function bindConciergeChips(root) {",
            delegate + "\n    function bindConciergeChips(root) {",
            1,
        )
        print("[OK] chatThread click delegation for chips")

    CHAT.write_text(t, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(CHAT)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("chat.js invalid:\n" + (r.stderr or ""))
    print("[OK] node --check chat.js")


def fix_app_concierge():
    if not APP.exists():
        return
    t = APP.read_text(encoding="utf-8")
    old = """    onConciergeAction: (action) => {
      try {
        if (action === 'knowledge') showView('knowledge');
        else if (action === 'users') showView('users');
        else if (action === 'agents') showView('agents');
      } catch (e) { console.warn(e); }
    },"""
    new = """    onConciergeAction: (action) => {
      try {
        if (action === 'knowledge') {
          if (typeof openKnowledgeGuided === 'function') openKnowledgeGuided();
          else showView('knowledge');
        } else if (action === 'users') showView('users');
        else if (action === 'agents') showView('agents');
      } catch (e) { console.warn('onConciergeAction', e); }
    },"""
    if old in t:
        t = t.replace(old, new, 1)
        print("[OK] onConciergeAction → openKnowledgeGuided")
    elif "openKnowledgeGuided()" in t.split("onConciergeAction")[1][:400]:
        print("[OK] onConciergeAction already guided")
    else:
        t2, n = re.subn(
            r"onConciergeAction:\s*\(action\)\s*=>\s*\{[\s\S]*?\},",
            new.strip() + "\n",
            t,
            count=1,
        )
        if n == 1:
            t = t2
            print("[OK] onConciergeAction replaced (regex)")
        else:
            print("[WARN] onConciergeAction not patched")
    APP.write_text(t, encoding="utf-8")


def fix_extractor_ocr():
    t = EXTRACTOR.read_text(encoding="utf-8")
    if "OCR unavailable" in t:
        print("[OK] OCR error handling already present")
        return
    # Wrap extract_pdf OCR call
    old = """    ocr_text = extract_pdf_with_ocr(data)

    if has_meaningful_text(ocr_text):
        return ocr_text

    raise ValueError(
        "PDF text extraction and OCR both produced "
        "insufficient text. The PDF may be"""
    new = """    try:
        ocr_text = extract_pdf_with_ocr(data)
    except Exception as exc:
        raise ValueError(
            "PDF has little selectable text and OCR failed "
            f"({type(exc).__name__}: {exc}). "
            "Install Tesseract for scanned PDFs, or upload a text-based PDF / paste text as a knowledge note."
        ) from exc

    if has_meaningful_text(ocr_text):
        return ocr_text

    raise ValueError(
        "PDF text extraction and OCR both produced "
        "insufficient text. The PDF may be"""
    if old not in t:
        # broader
        if "ocr_text = extract_pdf_with_ocr(data)" in t and "OCR failed" not in t:
            t = t.replace(
                "    ocr_text = extract_pdf_with_ocr(data)\n",
                "    try:\n"
                "        ocr_text = extract_pdf_with_ocr(data)\n"
                "    except Exception as exc:\n"
                "        raise ValueError(\n"
                "            \"PDF has little selectable text and OCR failed \"\n"
                "            f\"({type(exc).__name__}: {exc}). \"\n"
                "            \"Install Tesseract for scanned PDFs, or upload a text-based PDF / paste text as a knowledge note.\"\n"
                "        ) from exc\n",
                1,
            )
            print("[OK] OCR exceptions → ValueError")
        else:
            print("[WARN] extract_pdf OCR block not found")
    else:
        t = t.replace(old, new, 1)
        print("[OK] OCR exceptions → ValueError")
    EXTRACTOR.write_text(t, encoding="utf-8")
    compile(EXTRACTOR.read_text(encoding="utf-8"), str(EXTRACTOR), "exec")
    print("[OK] extractor.py compiles")


def fix_routes_ingest():
    t = ROUTES.read_text(encoding="utf-8")
    old = """    try:
        item = ingest_document_to_knowledge(
            db,
            company_id=company_id,
            data=data,
            original_filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            agent_instance_id=agent_instance_id,
            created_by_user_id=user.id,
            title=title,
            category=category or "document",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc"""
    new = """    try:
        item = ingest_document_to_knowledge(
            db,
            company_id=company_id,
            data=data,
            original_filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            agent_instance_id=agent_instance_id,
            created_by_user_id=user.id,
            title=title,
            category=category or "document",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid opaque 500 for missing OCR / parse libraries
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not extract text ({type(exc).__name__}: {exc}). "
                "Try a text PDF, DOCX, TXT, or paste content via Add knowledge."
            ),
        ) from exc"""
    if "Could not extract text" in t:
        print("[OK] ingest route already soft-fails extract errors")
    elif old in t:
        t = t.replace(old, new, 1)
        ROUTES.write_text(t, encoding="utf-8")
        print("[OK] ingest-extract maps extract failures to 400")
    else:
        print("[WARN] ingest try/except block not exact — skip routes")
        return
    compile(ROUTES.read_text(encoding="utf-8"), str(ROUTES), "exec")
    print("[OK] routes compile check (syntax)")


def bump_cache():
    if not HTML.exists():
        return
    t = HTML.read_text(encoding="utf-8")
    t2 = re.sub(
        r'(src="/workspace/assets/(?:app|chat|home|inbox|results|sidebar)\.js)\?v=[^"]*"',
        rf'\1?v={CACHE}"',
        t,
    )
    HTML.write_text(t2, encoding="utf-8")
    print(f"[OK] cache v={CACHE}")


def main():
    print("Job 100 — chips click + knowledge extract errors")
    if not CHAT.exists():
        raise SystemExit("run from repo root")
    fix_chat_chips()
    fix_app_concierge()
    fix_extractor_ocr()
    fix_routes_ingest()
    bump_cache()
    print(
        f"""
TEST chips:
  Ctrl+Shift+R — Network must show chat.js?v={CACHE}
  Click chip under concierge message → navigates (knowledge/users/agents)

TEST knowledge extract:
  Restart uvicorn (Python change)
  Upload a TEXT-based PDF or .txt / .docx
  Scanned PDF without Tesseract → clear 400 message (not 500)
  Or use Add knowledge (paste text) — always works without OCR

  git add app/static/workspace/chat.js app/static/workspace/app.js \\
          app/static/workspace/index.html app/knowledge/extractor.py app/api/routes.py
  git commit -m "fix: concierge chip clicks; soft-fail knowledge extract/OCR"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
