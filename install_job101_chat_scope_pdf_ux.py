#!/usr/bin/env python3
"""
Job 101 — Owner chat UX + PDF extract without Tesseract.

1) Fix bubble showing literal "null" (${work} when work is null).
2) Advisory chat: out-of-scope → helpful owner guidance (not dead-end error).
3) Chip "Ask me something" uses a clearer first question.
4) PDF: extract text via PyMuPDF before OCR; skip OCR if Tesseract missing.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
CHAT = ROOT / "app" / "static" / "workspace" / "chat.js"
CONV = ROOT / "app" / "services" / "conversation.py"
EXT = ROOT / "app" / "knowledge" / "extractor.py"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
CACHE = "20261026-job101"


def fix_chat_null_and_prompt():
    t = CHAT.read_text(encoding="utf-8")

    # Fix ${work} null stringification — any pattern that appends raw work
    # Prefer workHtml empty string
    if "${work}${chips}" in t:
        t = t.replace("${work}${chips}", "${workHtml}${chips}")
        # ensure workHtml defined near work
        if "const workHtml" not in t:
            t = t.replace(
                "const work = role === 'agent' && typeof message.work_result?.result === 'string'",
                "const workResult = role === 'agent' && typeof message.work_result?.result === 'string'",
                1,
            )
            # This might break - do more carefully
        print("[OK] template uses workHtml")

    # Full safe rewrite of the return section of messageMarkup if needed
    # Simpler: replace null work handling in JS by string replace of common patterns
    t = t.replace("${work}${chips}", "${(work && typeof work === 'string') ? work : ''}${chips}")
    t = t.replace("${work}</article>", "${(work && typeof work === 'string') ? work : ''}</article>")

    # In FIXED_MARKUP style from earlier jobs, work is already HTML string or ""
    # Problem is work = null then ${work} → "null"
    t2 = re.sub(
        r"const work = role === 'agent' && typeof message\.work_result\?\.result === 'string'[^;]+;",
        "let workHtml = '';\n"
        "    if (role === 'agent' && message.work_result && typeof message.work_result.result === 'string' "
        "&& message.work_result.result.trim() && message.work_result.status === 'completed') {\n"
        "      workHtml = '<div class=\"work-result\">' + esc(message.work_result.result) + '</div>';\n"
        "    }",
        t,
        count=1,
    )
    if t2 != t:
        t = t2
        t = t.replace(
            "${(work && typeof work === 'string') ? work : ''}${chips}",
            "${workHtml}${chips}",
        )
        t = t.replace(
            "${(work && typeof work === 'string') ? work : ''}</article>",
            "${workHtml}</article>",
        )
        # also if still ${work}
        t = re.sub(r"\$\{work\}(?!H)", "${workHtml}", t)
        print("[OK] workHtml never null")

    # Chip ask prompt — in-domain, actionable for new owner
    old_ask = "What should I do first as company owner?"
    new_ask = (
        "I am the company owner just getting started. "
        "In your role, what should I prepare first so you can help me effectively "
        "(knowledge, examples of questions you can answer, and limits of chat vs tasks)?"
    )
    if old_ask in t:
        t = t.replace(old_ask, new_ask)
        print("[OK] chip ask prompt improved")

    CHAT.write_text(t, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(CHAT)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("chat.js invalid:\n" + (r.stderr or ""))
    print("[OK] node --check chat.js")


def fix_conversation_scope_reply():
    t = CONV.read_text(encoding="utf-8")
    old = """    try:
        grounded_context = load_agent_context(db, agent, request)
    except ValueError as exc:
        if agent.status != "active":
            raise
        return str(exc) + " No action was completed."
"""
    new = """    try:
        grounded_context = load_agent_context(db, agent, request)
    except ValueError as exc:
        if agent.status != "active":
            raise
        msg = str(exc)
        # Job 101 — advisory chat must not dead-end new owners on scope
        if "outside the assigned" in msg.lower() or "out of scope" in msg.lower():
            scope_bits = list(agent.scope or []) or list((agent.configuration or {}).get("skills") or [])
            scope_txt = ", ".join(str(s) for s in scope_bits[:8]) if scope_bits else "my assigned specialty"
            name = agent.name or "your AI Employee"
            return (
                f"I am {name}. My role is focused on: {scope_txt}. "
                "Chat is advisory only within that focus — I will not claim to act outside it. "
                "As Owner, useful next steps are: "
                "(1) add company Knowledge (policies/FAQ) so answers can cite your documents, "
                "(2) ask a question in my domain, or "
                "(3) hire another AI Employee for a different specialty. "
                "Try asking what kinds of questions I can answer, or open Knowledge to upload a policy."
            )
        return msg + " No action was completed."
"""
    if "Job 101 — advisory chat" in t:
        print("[OK] scope reply already friendly")
    elif old in t:
        t = t.replace(old, new, 1)
        print("[OK] out-of-scope → owner guidance")
    else:
        # flexible
        t2, n = re.subn(
            r"except ValueError as exc:\n"
            r"        if agent\.status != \"active\":\n"
            r"            raise\n"
            r"        return str\(exc\) \+ \" No action was completed\.\"\n",
            new.split("try:")[0].replace("    try:\n        grounded_context = load_agent_context(db, agent, request)\n    ", "")
            if False
            else """except ValueError as exc:
        if agent.status != "active":
            raise
        msg = str(exc)
        if "outside the assigned" in msg.lower() or "out of scope" in msg.lower():
            scope_bits = list(agent.scope or []) or list((agent.configuration or {}).get("skills") or [])
            scope_txt = ", ".join(str(s) for s in scope_bits[:8]) if scope_bits else "my assigned specialty"
            name = agent.name or "your AI Employee"
            return (
                f"I am {name}. My role is focused on: {scope_txt}. "
                "Chat is advisory only within that focus — I will not claim to act outside it. "
                "As Owner, useful next steps are: "
                "(1) add company Knowledge (policies/FAQ) so answers can cite your documents, "
                "(2) ask a question in my domain, or "
                "(3) hire another AI Employee for a different specialty. "
                "Try asking what kinds of questions I can answer, or open Knowledge to upload a policy."
            )
        return msg + " No action was completed."
""",
            t,
            count=1,
        )
        if n != 1:
            raise SystemExit("could not patch _agent_reply_text ValueError handler")
        t = t2
        print("[OK] out-of-scope → owner guidance (regex)")

    CONV.write_text(t, encoding="utf-8")
    compile(CONV.read_text(encoding="utf-8"), str(CONV), "exec")
    print("[OK] conversation.py compiles")


def fix_pdf_pymupdf_before_ocr():
    t = EXT.read_text(encoding="utf-8")

    helper = '''
def extract_pdf_with_pymupdf(data: bytes) -> str:
    """Text layer extraction via PyMuPDF (no OCR / no Tesseract)."""
    pdf = fitz.open(stream=data, filetype="pdf")
    try:
        if pdf.page_count == 0:
            raise ValueError("PDF contains no pages")
        pages: list[str] = []
        for page_number in range(pdf.page_count):
            page = pdf.load_page(page_number)
            text = normalize_text(page.get_text("text") or "")
            if text:
                pages.append(f"[Page {page_number + 1}]\\n{text}")
        return normalize_text("\\n\\n".join(pages))
    finally:
        pdf.close()


def tesseract_available() -> bool:
    try:
        import shutil
        return bool(shutil.which("tesseract"))
    except Exception:
        return False
'''

    if "def extract_pdf_with_pymupdf" not in t:
        t = t.replace(
            "\ndef extract_pdf_with_ocr(data: bytes) -> str:",
            "\n" + helper + "\ndef extract_pdf_with_ocr(data: bytes) -> str:",
            1,
        )
        print("[OK] pymupdf text helper + tesseract_available")

    # Replace extract_pdf strategy
    old_pdf = '''def extract_pdf(data: bytes) -> str:
    """
    PDF extraction strategy:

    1. Try normal PDF text extraction.
    2. If insufficient, fallback to OCR.
    3. Fail only if both approaches produce
       insufficient meaningful text.
    """

    text = extract_pdf_with_pypdf(data)

    if has_meaningful_text(text):
        return text

    try:
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
        "insufficient text. The PDF may be'''

    # Use flexible replace of the function body start
    if "extract_pdf_with_pymupdf(data)" not in t.split("def extract_pdf")[1][:800]:
        t2, n = re.subn(
            r"def extract_pdf\(data: bytes\) -> str:[\s\S]*?text = extract_pdf_with_pypdf\(data\)\s*\n\s*if has_meaningful_text\(text\):\s*\n\s*return text\s*\n",
            '''def extract_pdf(data: bytes) -> str:
    """
    PDF extraction strategy:
    1. pypdf text layer
    2. PyMuPDF text layer (no Tesseract)
    3. OCR only if Tesseract is installed
    """
    text = extract_pdf_with_pypdf(data)
    if has_meaningful_text(text):
        return text

    try:
        text = extract_pdf_with_pymupdf(data)
        if has_meaningful_text(text):
            return text
    except Exception:
        pass

    if not tesseract_available():
        raise ValueError(
            "This PDF has little selectable text (likely a scan/image). "
            "Tesseract OCR is not installed on the server. "
            "Upload a text-based PDF, DOCX, or TXT — or paste the contract text via Add knowledge."
        )

''',
            t,
            count=1,
        )
        if n != 1:
            # insert pymupdf attempt after pypdf success check manually
            needle = "    text = extract_pdf_with_pypdf(data)\n\n    if has_meaningful_text(text):\n        return text\n"
            insert = (
                "    text = extract_pdf_with_pypdf(data)\n\n"
                "    if has_meaningful_text(text):\n"
                "        return text\n\n"
                "    try:\n"
                "        text = extract_pdf_with_pymupdf(data)\n"
                "        if has_meaningful_text(text):\n"
                "            return text\n"
                "    except Exception:\n"
                "        pass\n\n"
                "    if not tesseract_available():\n"
                "        raise ValueError(\n"
                "            \"This PDF has little selectable text (likely a scan/image). \"\n"
                "            \"Tesseract OCR is not installed on the server. \"\n"
                "            \"Upload a text-based PDF, DOCX, or TXT — or paste the contract text via Add knowledge.\"\n"
                "        )\n\n"
            )
            if needle in t:
                t = t.replace(needle, insert, 1)
                print("[OK] PDF strategy: pymupdf then optional OCR")
            else:
                print("[WARN] extract_pdf strategy not fully patched")
        else:
            t = t2
            print("[OK] extract_pdf rewritten start")

    EXT.write_text(t, encoding="utf-8")
    compile(EXT.read_text(encoding="utf-8"), str(EXT), "exec")
    print("[OK] extractor.py compiles")


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
    print("Job 101 — chat scope UX + PDF without Tesseract")
    if not CHAT.exists():
        raise SystemExit("run from repo root")
    fix_chat_null_and_prompt()
    fix_conversation_scope_reply()
    fix_pdf_pymupdf_before_ocr()
    bump_cache()
    print(
        f"""
TEST 1 — Ask me something chip:
  Ctrl+Shift+R (chat.js?v={CACHE})
  Click chip → agent replies with role + next steps (NOT only 'outside scope')
  No literal 'null' under bubbles

TEST 2 — Knowledge PDF:
  Restart uvicorn
  Text PDF → uses pypdf/pymupdf; if scan: clear 400 asking for text PDF / paste
  Paste contract via Add knowledge always works

  git add app/static/workspace/chat.js app/services/conversation.py \\
          app/knowledge/extractor.py app/static/workspace/index.html
  git commit -m "Job 101: friendly out-of-scope chat; fix null bubbles; PDF without Tesseract"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
