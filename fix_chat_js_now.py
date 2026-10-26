#!/usr/bin/env python3
"""One-shot: fix broken chat.js line 44 + bump cache + harden login tabs."""
from pathlib import Path
import subprocess

ROOT = Path.cwd()
CHAT = ROOT / "app" / "static" / "workspace" / "chat.js"
APP = ROOT / "app" / "static" / "workspace" / "app.js"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"


def fix_chat():
    text = CHAT.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Find broken: const textHtml = esc(body).replace(/
    # next line: /g, '<br>');
    out = []
    i = 0
    fixed = False
    while i < len(lines):
        line = lines[i]
        if "const textHtml = esc(body).replace(/" in line and line.strip().endswith("replace(/"):
            # skip this and next line if next is /g
            if i + 1 < len(lines) and "/g" in lines[i + 1]:
                out.append('    const textHtml = esc(body).split("\\n").join("<br>");\n')
                i += 2
                fixed = True
                continue
            # same line broken somehow
            out.append('    const textHtml = esc(body).split("\\n").join("<br>");\n')
            i += 1
            fixed = True
            continue
        # also fix if already partially wrong on one line with newline in middle of file content
        if "esc(body).replace(/" in line and "split" not in line:
            out.append('    const textHtml = esc(body).split("\\n").join("<br>");\n')
            # skip orphan /g line
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("/g"):
                i += 2
            else:
                i += 1
            fixed = True
            continue
        out.append(line)
        i += 1

    if not fixed:
        # Nuclear: rewrite messageMarkup body via markers
        joined = "".join(out)
        start = joined.find("  function messageMarkup(")
        end = joined.find("  function create(", start)
        if start < 0 or end < 0:
            raise SystemExit("messageMarkup not found and line-fix failed")
        new_fn = r'''  function isConciergeMessage(content) {
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
      ? '<time datetime="' + esc(date.toISOString()) + '">' +
        esc(new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(date)) +
        "</time>"
      : "";
    const sender = message.sender_name || (role === "agent" ? agentName || "Unknown sender" : role === "system" ? "System" : "Unknown sender");
    const workObj = role === "agent" && typeof message.work_result?.result === "string" && message.work_result.result.trim() && message.work_result.status === "completed" ? message.work_result : null;
    const work = workObj ? '<div class="work-result">' + esc(workObj.result) + "</div>" : "";
    const body = role === "agent" ? cleanReply(message.content) : message.content || "";
    const textHtml = esc(body).split("\n").join("<br>");
    const chips = role === "agent" && isConciergeMessage(message.content) ? conciergeActionsMarkup() : "";
    return '<article class="bubble ' + role + '"><div class="who"><span>' + esc(sender) + "</span>" + time + '</div><div class="bubble-text">' + textHtml + "</div>" + work + chips + "</article>";
  }

'''
        # Drop duplicate isConcierge if present before messageMarkup
        before = joined[:start]
        # remove prior isConciergeMessage block if any
        marker = before.rfind("  function isConciergeMessage")
        if marker >= 0:
            before = before[:marker]
        joined = before + new_fn + joined[end:]
        CHAT.write_text(joined, encoding="utf-8")
        print("[OK] chat.js messageMarkup rewritten")
    else:
        CHAT.write_text("".join(out), encoding="utf-8")
        print("[OK] chat.js broken replace() lines fixed")

    r = subprocess.run(["node", "--check", str(CHAT)], capture_output=True, text=True)
    if r.returncode != 0:
        # try nuclear rewrite if line fix still fails
        raise SystemExit("node --check failed:\n" + (r.stderr or ""))
    print("[OK] node --check chat.js")


def fix_tabs():
    if not APP.exists():
        return
    t = APP.read_text(encoding="utf-8")
    # Remove Job 94 duplicate tab handler by line scan
    lines = t.splitlines(keepends=True)
    out = []
    i = 0
    removed = False
    while i < len(lines):
        if "// Job 94 — smoother tab panel transitions" in lines[i]:
            # skip until closing of forEach block (simple brace count from this line)
            depth = 0
            started = False
            while i < len(lines):
                for ch in lines[i]:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                i += 1
                if started and depth <= 0:
                    break
            # skip trailing blank
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            removed = True
            continue
        out.append(lines[i])
        i += 1
    t = "".join(out)
    if removed:
        print("[OK] removed Job 94 duplicate tab handler")

    # Ensure openLoginTab activates panel reliably
    if "function activateLoginTab" not in t:
        needle = "  // Login tabs\n"
        if needle in t:
            inject = '''  // Login tabs
  function activateLoginTab(name) {
    if (!name) return;
    document.querySelectorAll(".login-tabs .tab, .auth-rail .tab").forEach((el) => {
      el.classList.toggle("active", el.getAttribute("data-tab") === name);
    });
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    const panel = document.getElementById("tab-" + name);
    if (panel) panel.classList.add("active");
  }
'''
            t = t.replace(needle, inject, 1)
            # Replace openLoginTab body
            t = t.replace(
                """  function openLoginTab(name) {
    document.querySelector(`.login-tabs .tab[data-tab="${name}"]`)?.click();
  }""",
                """  function openLoginTab(name) {
    activateLoginTab(name);
  }""",
                1,
            )
            # Make existing forEach call activateLoginTab
            t = t.replace(
                """  document.querySelectorAll(".login-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".login-tabs .tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      const panel = $("tab-" + tab.dataset.tab);
      if (panel) panel.classList.add("active");
    });
  });""",
                """  document.querySelectorAll(".login-tabs .tab, .auth-rail .tab").forEach((tab) => {
    tab.addEventListener("click", (e) => {
      e.preventDefault();
      activateLoginTab(tab.getAttribute("data-tab"));
    });
  });""",
                1,
            )
            print("[OK] activateLoginTab wired")
    APP.write_text(t, encoding="utf-8")


def bump_cache():
    if not HTML.exists():
        return
    t = HTML.read_text(encoding="utf-8")
    t2 = t.replace("?v=20261023-onboarding-4", "?v=20261026-chat-fix")
    t2 = t2.replace("?v=20261023-nav-1", "?v=20261026-chat-fix")
    if t2 != t:
        HTML.write_text(t2, encoding="utf-8")
        print("[OK] cache-bust query on scripts")
    else:
        # force any chat.js / app.js query
        t2 = t.replace("chat.js?", "chat.js?v=20261026-chat-fix&")
        t2 = t2.replace("app.js?", "app.js?v=20261026-chat-fix&")
        if t2 == t:
            t2 = t.replace(
                'src="/workspace/assets/chat.js',
                'src="/workspace/assets/chat.js?v=20261026-chat-fix',
            ).replace(
                'src="/workspace/assets/app.js',
                'src="/workspace/assets/app.js?v=20261026-chat-fix',
            )
        HTML.write_text(t2, encoding="utf-8")
        print("[OK] cache-bust applied")


def main():
    print("FIX chat.js NOW")
    if not CHAT.exists():
        raise SystemExit("run from repo root")
    fix_chat()
    fix_tabs()
    bump_cache()
    print("DONE. Hard refresh browser (Ctrl+Shift+R).")
    print("git add app/static/workspace/chat.js app/static/workspace/app.js app/static/workspace/index.html")
    print('git commit -m "fix: repair chat.js syntax so login tabs and app.js load"')
    print("git push origin development")


if __name__ == "__main__":
    main()
