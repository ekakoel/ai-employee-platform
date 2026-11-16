#!/usr/bin/env python3
"""
COMPLETE fix for login tabs dead / WorkspaceChat is not defined.

Root cause chain:
1) chat.js had a broken regex (Job 98) → SyntaxError
2) app.js never runs → tabs/login dead, WorkspaceChat undefined
3) Browser still loads ?v=20261023-onboarding-4 (cached broken JS)

This script ALWAYS rewrites the chat markup section and bumps every
workspace script query string so the browser cannot keep the broken file.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
CHAT = ROOT / "app" / "static" / "workspace" / "chat.js"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
APP = ROOT / "app" / "static" / "workspace" / "app.js"

CACHE = "20261026-login-fix-2"

GOOD_BLOCK = r'''
  function isConciergeMessage(content) {
    var t = String(content || "");
    return /As Owner you can/i.test(t) || /Suggested next steps/i.test(t) || /first AI Employee/i.test(t);
  }
  function conciergeActionsMarkup() {
    return (
      '<div class="concierge-actions" role="group" aria-label="Suggested next steps">' +
      '<button type="button" class="concierge-chip" data-concierge="knowledge">1 · Upload knowledge</button>' +
      '<button type="button" class="concierge-chip" data-concierge="users">2 · Invite teammate</button>' +
      '<button type="button" class="concierge-chip" data-concierge="ask">3 · Ask me something</button>' +
      '<button type="button" class="concierge-chip" data-concierge="agents">4 · Configure AI Employee</button>' +
      "</div>"
    );
  }
  function messageMarkup(message, esc, opts) {
    opts = opts || {};
    var agentName = opts.agentName || "";
    var normalizedRole = ({ assistant: "agent", user: "human" })[message.role] || message.role;
    var role = ["human", "agent", "system"].indexOf(normalizedRole) >= 0 ? normalizedRole : "agent";
    var raw = message.created_at || "";
    var date = new Date(raw && !/(Z|[+-]\d{2}:\d{2})$/i.test(raw) ? raw + "Z" : raw);
    var time = "";
    if (!Number.isNaN(date.getTime())) {
      time =
        '<time datetime="' +
        esc(date.toISOString()) +
        '">' +
        esc(
          new Intl.DateTimeFormat("en", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            timeZoneName: "short",
          }).format(date)
        ) +
        "</time>";
    }
    var sender =
      message.sender_name ||
      (role === "agent" ? agentName || "Unknown sender" : role === "system" ? "System" : "Unknown sender");
    var work = "";
    if (
      role === "agent" &&
      message.work_result &&
      typeof message.work_result.result === "string" &&
      message.work_result.result.trim() &&
      message.work_result.status === "completed"
    ) {
      work = '<div class="work-result">' + esc(message.work_result.result) + "</div>";
    }
    var body = role === "agent" ? cleanReply(message.content) : message.content || "";
    var textHtml = esc(body).split("\n").join("<br>");
    var chips = role === "agent" && isConciergeMessage(message.content) ? conciergeActionsMarkup() : "";
    return (
      '<article class="bubble ' +
      role +
      '"><div class="who"><span>' +
      esc(sender) +
      "</span>" +
      time +
      '</div><div class="bubble-text">' +
      textHtml +
      "</div>" +
      work +
      chips +
      "</article>"
    );
  }
'''


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    """Replace exclusive region [start_marker, end_marker) with replacement + end_marker preserved."""
    # Prefer isConciergeMessage if present, else messageMarkup
    start = text.find(start_marker)
    if start < 0:
        start_marker = "  function messageMarkup("
        start = text.find(start_marker)
    if start < 0:
        raise SystemExit("Could not find messageMarkup/isConciergeMessage in chat.js")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit("Could not find create() after messageMarkup in chat.js")
    return text[:start] + replacement.lstrip("\n") + "\n\n" + text[end:]


def fix_chat() -> None:
    text = CHAT.read_text(encoding="utf-8")
    text = replace_between(
        text,
        "  function isConciergeMessage(",
        "  function create(",
        GOOD_BLOCK,
    )
    CHAT.write_text(text, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(CHAT)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("chat.js still invalid after rewrite:\n" + (r.stderr or r.stdout or ""))
    print("[OK] chat.js rewritten + node --check passed")


def bump_html() -> None:
    if not HTML.exists():
        print("[WARN] index.html missing")
        return
    t = HTML.read_text(encoding="utf-8")
    # Normalize all workspace script tags to new cache key
    for name in ("home.js", "inbox.js", "chat.js", "results.js", "sidebar.js", "app.js"):
        # replace any existing ?v=... after this file
        import re
        t = re.sub(
            rf'(src="/workspace/assets/{name})(?:\?[^"]*)?"',
            rf'\1?v={CACHE}"',
            t,
        )
    HTML.write_text(t, encoding="utf-8")
    print(f"[OK] index.html script cache → v={CACHE}")


def fix_app_tabs() -> None:
    if not APP.exists():
        return
    t = APP.read_text(encoding="utf-8")
    # Drop Job 94 duplicate handler if still present
    marker = "// Job 94 — smoother tab panel transitions"
    if marker in t:
        start = t.find(marker)
        # find end of the forEach call
        sub = t[start:]
        # skip until we see "  });\n" after forEach
        idx = sub.find("  document.querySelectorAll")
        if idx < 0:
            idx = 0
        # from marker, find matching end: next occurrence of "\n  });\n\n" after forEach
        end_rel = sub.find("\n  });\n", sub.find("forEach"))
        if end_rel > 0:
            end_rel += len("\n  });\n")
            t = t[:start] + t[start + end_rel :]
            print("[OK] removed duplicate Job 94 tab handler")
        else:
            print("[WARN] could not slice Job 94 block")
    APP.write_text(t, encoding="utf-8")


def verify() -> None:
    r = subprocess.run(["node", "--check", str(CHAT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    body = CHAT.read_text(encoding="utf-8")
    assert "esc(body).replace(/" not in body, "broken replace still present"
    assert "function messageMarkup" in body
    assert "function create(" in body
    html = HTML.read_text(encoding="utf-8")
    assert f"chat.js?v={CACHE}" in html, "cache not bumped"
    print("[OK] verification passed")
    print(f"     Browser must load: /workspace/assets/chat.js?v={CACHE}")


def main() -> int:
    print("COMPLETE LOGIN/TAB FIX")
    print("ROOT:", ROOT)
    if not CHAT.exists():
        print("ERROR: app/static/workspace/chat.js not found — run from repo root")
        return 1
    fix_chat()
    fix_app_tabs()
    bump_html()
    verify()
    print(
        """
NEXT (do all of these):
  1) Restart not required for static files, but hard-refresh IS required
  2) Open DevTools → Network → disable cache → Ctrl+Shift+R
  3) Confirm chat.js URL ends with ?v=20261026-login-fix-2
  4) Console must be clean of SyntaxError / WorkspaceChat is not defined

  git add app/static/workspace/chat.js app/static/workspace/index.html app/static/workspace/app.js
  git commit -m "fix: rewrite chat.js markup + cache-bust so login tabs load"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
