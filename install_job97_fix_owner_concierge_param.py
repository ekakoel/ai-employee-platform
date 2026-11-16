#!/usr/bin/env python3
"""
Fix 500 on POST /conversations with owner_concierge=true.

Bug: routes pass owner_concierge=... but create_conversation() signature
never accepted the kwarg (NameError/TypeError → 500). Finish onboarding
then fell through to plain Home with no concierge UI.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
CONV = ROOT / "app" / "services" / "conversation.py"


def main() -> int:
    print("FIX: create_conversation(owner_concierge=...)")
    if not CONV.exists():
        print("ERROR: run from repo root")
        return 1

    t = CONV.read_text(encoding="utf-8")

    # Ensure helper exists
    if "def build_owner_concierge_welcome" not in t:
        helper = '''
def build_owner_concierge_welcome(agent_name: str, company_name: str) -> str:
    """Template welcome for first-hired AI Employee guiding the company owner."""
    agent = (agent_name or "your AI Employee").strip()
    company = (company_name or "your company").strip()
    return (
        f"Hello — I am {agent}, the first AI Employee at {company}.\\n\\n"
        "Your company profile is set up and I am ready to help. "
        "As Owner you can:\\n"
        "• Update Company profile (name, contact, industry)\\n"
        "• Hire and configure more AI Employees\\n"
        "• Assign skills and tools to each AI Employee\\n"
        "• Add Knowledge (policies, FAQs, playbooks) so answers stay grounded\\n"
        "• Invite teammates under Users & positions\\n"
        "• Chat with AI Employees, create Tasks, and review Approvals\\n\\n"
        "Suggested next steps — reply with a number or describe what you need:\\n"
        "1) Upload a knowledge document (policies / FAQ)\\n"
        "2) Invite a teammate\\n"
        "3) Give me a first real question or task\\n"
        "4) Open AI Employees to refine my configuration\\n\\n"
        "Chat is advisory. To run tools, use Create Task from this conversation."
    )


'''
        t = t.replace("\ndef create_conversation(", "\n" + helper + "def create_conversation(", 1)
        print("[OK] inserted build_owner_concierge_welcome")

    old = """def create_conversation(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    user_id: str,
    title: str = "",
) -> Conversation:"""
    new = """def create_conversation(
    db: Session,
    *,
    company_id: str,
    agent_instance_id: str,
    user_id: str,
    title: str = "",
    owner_concierge: bool = False,
) -> Conversation:"""

    if "owner_concierge: bool = False" in t and "def create_conversation" in t:
        # already has param?
        sig_start = t.find("def create_conversation")
        sig_end = t.find(") -> Conversation:", sig_start)
        sig = t[sig_start:sig_end]
        if "owner_concierge" in sig:
            print("[OK] signature already has owner_concierge")
        else:
            if old not in t:
                raise SystemExit("signature pattern not found")
            t = t.replace(old, new, 1)
            print("[OK] added owner_concierge param")
    else:
        if old not in t:
            # try flex single-line-ish
            import re
            t2, n = re.subn(
                r"def create_conversation\(\s*db: Session,\s*\*,\s*"
                r"company_id: str,\s*agent_instance_id: str,\s*user_id: str,\s*"
                r"title: str = \"\",\s*\) -> Conversation:",
                "def create_conversation(\n"
                "    db: Session,\n"
                "    *,\n"
                "    company_id: str,\n"
                "    agent_instance_id: str,\n"
                "    user_id: str,\n"
                "    title: str = \"\",\n"
                "    owner_concierge: bool = False,\n"
                ") -> Conversation:",
                t,
                count=1,
            )
            if n != 1:
                raise SystemExit("could not patch create_conversation signature")
            t = t2
            print("[OK] added owner_concierge param (regex)")
        else:
            t = t.replace(old, new, 1)
            print("[OK] added owner_concierge param")

    # Ensure Company import
    if "Company" not in t.split("def create_conversation")[0]:
        if "from app.models import Company" not in t:
            t = "from app.models import Company  # Job 97\n" + t
            print("[OK] Company import")

    # Ensure body uses owner_concierge (already present on GH)
    if "if owner_concierge:" not in t:
        raise SystemExit("body missing if owner_concierge — unexpected")

    CONV.write_text(t, encoding="utf-8")
    compile(CONV.read_text(encoding="utf-8"), str(CONV), "exec")
    print("[OK] conversation.py compiles")

    # Sanity: signature accepts the kwarg
    ns = {}
    # light check via ast
    import ast
    tree = ast.parse(CONV.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "create_conversation":
            args = [a.arg for a in node.args.kwonlyargs] + [a.arg for a in node.args.args]
            assert "owner_concierge" in args, args
            print("[OK] ast confirms owner_concierge kwonly/arg:", args)

    print(
        """
Restart uvicorn (required — Python code change):
  .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001

Retest:
  Login as owner who finished hire → Finish setup
  OR from Chat create conversation (should not 500)
  Network: POST /conversations → 201 not 500
  Chat shows agent welcome + 4 chips

  git add app/services/conversation.py
  git commit -m "fix: create_conversation accepts owner_concierge (stop 500 on Finish)"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
