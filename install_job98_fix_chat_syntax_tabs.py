#!/usr/bin/env python3
"""
CRITICAL FIX: chat.js SyntaxError breaks entire workspace (app.js never runs).

Broken lines from Job 98:
    const textHtml = esc(body).replace(/
    /g, '<br>');

Also harden login tab switching so panels always activate.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
CHAT = ROOT / "app" / "static" / "workspace" / "chat.js"
APP = ROOT / "app" / "static" / "workspace" / "app.js"


FIXED_MARKUP = r'''
  function isConciergeMessage(content) {
    const t = String(content || "");
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

  function messageMarkup(message, esc, { agentName = "" } = {}) {
    const normalizedRole = { assistant: "agent", user: "human" }[message.role] || message.role;
    const role = ["human", "agent", "system"].includes(normalizedRole) ? normalizedRole : "agent";
    const raw = message.created_at || "";
    const date = new Date(raw && !/(Z|[+-]\d{2}:\d{2})$/i.test(raw) ? raw + "Z" : raw);
    const time = !Number.isNaN(date.getTime())
      ? '<time datetime="' +
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
        "</time>"
      : "";
    const sender =
      message.sender_name ||
      (role === "agent" ? agentName || "Unknown sender" : role === "system" ? "System" : "Unknown sender");
    const workObj =
      role === "agent" &&
      typeof message.work_result?.result === "string" &&
      message.work_result.result.trim() &&
      message.work_result.status === "completed"
        ? message.work_result
        : null;
    const work = workObj
      ? '<div class="work-result">' + esc(workObj.result) + "</div>"
      : "";
    const body = role === "agent" ? cleanReply(message.content) : message.content || "";
    const textHtml = esc(body).split("\n").join("<br>");
    const chips = role === "agent" && isConciergeMessage(message.content) ? conciergeActionsMarkup() : "";
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


def fix_chat():
    t = CHAT.read_text(encoding="utf-8")
    # Remove broken isConcierge through messageMarkup (inclusive)
    t2, n = re.subn(
        r"\n  function isConciergeMessage\(content\) \{[\s\S]*?\n  function messageMarkup\(message, esc, \{ agentName = [^}]+\} = \{\}\) \{[\s\S]*?\n  \}\n\n  function create\(",
        "\n" + FIXED_MARKUP + "\n  function create(",
        t,
        count=1,
    )
    if n != 1:
        # try without isConcierge prefix (only broken messageMarkup)
        t2, n = re.subn(
            r"\n  function messageMarkup\(message, esc, \{ agentName = [^}]+\} = \{\}\) \{[\s\S]*?\n  \}\n\n  function create\(",
            "\n" + FIXED_MARKUP + "\n  function create(",
            t,
            count=1,
        )
    if n != 1:
        # Nuclear: fix just the broken replace line
        if "esc(body).replace(/" in t:
            t2 = t.replace(
                "const textHtml = esc(body).replace(/\n/g, '<br>');",
                'const textHtml = esc(body).split("\\n").join("<br>");',
            )
            # also fix if split across lines
            t2 = re.sub(
                r"const textHtml = esc\(body\)\.replace\(/\s*/g, '<br>'\);",
                'const textHtml = esc(body).split("\\n").join("<br>");',
                t2,
                count=1,
            )
            n = 1
        else:
            raise SystemExit("could not locate broken messageMarkup in chat.js")
    CHAT.write_text(t2, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(CHAT)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("chat.js still invalid:\n" + (r.stderr or r.stdout))
    print("[OK] chat.js syntax fixed (node --check)")


def fix_tabs():
    """Single reliable tab switcher; remove conflicting Job 94 half-handler."""
    if not APP.exists():
        return
    t = APP.read_text(encoding="utf-8")

    good_tabs = '''
  // Login tabs — single handler (tabs + panels)
  function activateLoginTab(name) {
    if (!name) return;
    document.querySelectorAll(".login-tabs .tab, .auth-rail .tab").forEach((t) => {
      t.classList.toggle("active", t.getAttribute("data-tab") === name);
    });
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    const panel = document.getElementById("tab-" + name);
    if (panel) {
      panel.classList.add("active");
      panel.style.display = "";
    }
  }
  document.querySelectorAll(".login-tabs .tab, .auth-rail .tab").forEach((tab) => {
    tab.addEventListener("click", (e) => {
      e.preventDefault();
      activateLoginTab(tab.getAttribute("data-tab"));
    });
  });

  function openLoginTab(name) {
    activateLoginTab(name);
  }
'''

    # Replace first login tabs block
    t2, n1 = re.subn(
        r"  // Login tabs\n  document\.querySelectorAll\(\"\.login-tabs \.tab\"\)\.forEach\(\(tab\) => \{\n"
        r"    tab\.addEventListener\(\"click\", \(\) => \{\n"
        r"      document\.querySelectorAll\(\"\.login-tabs \.tab\"\)\.forEach\(\(t\) => t\.classList\.remove\(\"active\"\)\);\n"
        r"      document\.querySelectorAll\(\"\.tab-panel\"\)\.forEach\(\(p\) => p\.classList\.remove\(\"active\"\)\);\n"
        r"      tab\.classList\.add\(\"active\"\);\n"
        r"      const panel = \$\(\"tab-\" \+ tab\.dataset\.tab\);\n"
        r"      if \(panel\) panel\.classList\.add\(\"active\"\);\n"
        r"    \}\);\n"
        r"  \}\);\n\n"
        r"  function openLoginTab\(name\) \{\n"
        r"    document\.querySelector\(`\.login-tabs \.tab\[data-tab=\"\$\{name\}\"\]`\)\?\.click\(\);\n"
        r"  \}\n",
        good_tabs + "\n",
        t,
        count=1,
    )
    if n1 != 1:
        print("[WARN] primary tab block pattern not matched — trying broader")
        t2 = t

    # Remove Job 94 duplicate handler that only toggles panels (breaks tab active state)
    t3, n2 = re.subn(
        r"\n  // Job 94 — smoother tab panel transitions\n"
        r"  document\.querySelectorAll\(\"\.login-tabs \.tab, \.auth-rail \.tab\"\)\.forEach\(\(tab\) => \{\n"
        r"    tab\.addEventListener\(\"click\", \(\) => \{[\s\S]*?\n    \}\);\n"
        r"  \}\);\n",
        "\n",
        t2,
        count=1,
    )
    if n2 == 1:
        print("[OK] removed conflicting Job 94 tab handler")
    else:
        print("[WARN] Job 94 tab handler not removed")
        t3 = t2

    APP.write_text(t3, encoding="utf-8")
    print("[OK] app.js tab switching hardened")


def main():
    print("FIX — chat.js syntax + login tabs")
    if not CHAT.exists():
        raise SystemExit("run from repo root")
    fix_chat()
    fix_tabs()
    print(
        """
  # Hard refresh (Ctrl+Shift+R) — cached broken chat.js must reload
  # Tabs Sign in / Register / Activate / Invite must switch panels
  # Login button must work

  git add app/static/workspace/chat.js app/static/workspace/app.js
  git commit -m "fix: chat.js SyntaxError blocked login tabs; restore tab switching"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
