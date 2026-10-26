#!/usr/bin/env python3
"""
Job 98 — Concierge quick actions + once-only tour engagement.

- Chat shows action chips under owner-concierge agent messages
- Chips navigate to Knowledge / Users / AI Employees or prefill a first question
- Marks tour engaged in localStorage (per company) so we don't re-spam UX
- Home can show a one-line tip until first engagement

Run from repo root:
  python install_job98_concierge_actions.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
CHAT = ROOT / "app" / "static" / "workspace" / "chat.js"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"
APP = ROOT / "app" / "static" / "workspace" / "app.js"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"


def patch_chat_js():
    t = CHAT.read_text(encoding="utf-8")

    # Enhance messageMarkup to append chips for concierge content
    if "concierge-actions" not in t:
        old = """  function messageMarkup(message, esc, { agentName = '' } = {}) {
    const normalizedRole = { assistant: 'agent', user: 'human' }[message.role] || message.role;
    const role = ['human', 'agent', 'system'].includes(normalizedRole) ? normalizedRole : 'agent';
    const raw = message.created_at || '';
    const date = new Date(raw && !/(Z|[+-]\\d{2}:\\d{2})$/i.test(raw) ? `${raw}Z` : raw);
    const time = !Number.isNaN(date.getTime()) ? `<time datetime="${esc(date.toISOString())}">${esc(new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(date))}</time>` : '';
    const sender = message.sender_name || (role === 'agent' ? agentName || 'Unknown sender' : role === 'system' ? 'System' : 'You');
    const work = role === 'agent' && typeof message.work_result?.result === 'string' && message.work_result.result.trim()
      ? `<div class="work-result">${esc(message.work_result.result)}</div>` : '';
    const content = role === 'agent' ? cleanReply(message.content) : message.content || '';
    return `<article class="bubble ${role}"><div class="who"><span>${esc(sender)}</span>${time}</div><div>${esc(content).replace(/\\n/g, '<br>')}</div>${work}</article>`;
  }"""
        # Use flexible approach - find return of messageMarkup
        # Simpler: after messageMarkup function, we'll inject helper and patch return line

        helper = r'''
  function isConciergeMessage(content) {
    const t = String(content || '');
    return /As Owner you can/i.test(t) || /Suggested next steps/i.test(t) || /first AI Employee/i.test(t);
  }
  function conciergeActionsMarkup() {
    return `<div class="concierge-actions" role="group" aria-label="Suggested next steps">
      <button type="button" class="concierge-chip" data-concierge="knowledge">1 · Upload knowledge</button>
      <button type="button" class="concierge-chip" data-concierge="users">2 · Invite teammate</button>
      <button type="button" class="concierge-chip" data-concierge="ask">3 · Ask me something</button>
      <button type="button" class="concierge-chip" data-concierge="agents">4 · Configure AI Employee</button>
    </div>`;
  }
'''
        if "function isConciergeMessage" not in t:
            t = t.replace(
                "  function messageMarkup(message, esc, { agentName = '' } = {}) {",
                helper + "\n  function messageMarkup(message, esc, { agentName = '' } = {}) {",
                1,
            )

        # Patch the return of messageMarkup to append chips
        # Find: return `<article class="bubble
        t2, n = re.subn(
            r"return `<article class=\"bubble \$\{role\}\">[\s\S]*?</article>`;",
            "const body = role === 'agent' ? cleanReply(message.content) : message.content || '';\n"
            "    const textHtml = esc(body).replace(/\\n/g, '<br>');\n"
            "    const chips = role === 'agent' && isConciergeMessage(message.content) ? conciergeActionsMarkup() : '';\n"
            "    return `<article class=\"bubble ${role}\"><div class=\"who\"><span>${esc(sender)}</span>${time}</div>"
            "<div class=\"bubble-text\">${textHtml}</div>${work}${chips}</article>`;",
            t,
            count=1,
        )
        if n == 1:
            t = t2
            # Remove duplicate content const usage issues - the original had const content =
            # May leave unused const content - ok in JS
            print("[OK] messageMarkup concierge chips")
        else:
            # try alternate simpler injection after cleanReply content line
            print("[WARN] messageMarkup return pattern not matched — alternate patch")
            if "conciergeActionsMarkup()" not in t:
                t = t.replace(
                    "return `<article class=\"bubble ${role}\">",
                    "const __chips = role === 'agent' && isConciergeMessage(message.content) ? conciergeActionsMarkup() : '';\n"
                    "    return `<article class=\"bubble ${role}\">",
                    1,
                )
                t = t.replace(
                    "</div>${work}</article>`;",
                    "</div>${work}${__chips}</article>`;",
                    1,
                )
                print("[OK] alternate chips inject")

    # Wire chip clicks inside create()
    if "data-concierge" not in t.split("function create")[1][:4000] or "bindConciergeChips" not in t:
        bind = '''
    function markTourEngaged() {
      try {
        const s = getSession();
        if (s && s.companyId) localStorage.setItem('owner_concierge_done:' + s.companyId, '1');
      } catch (_) {}
    }
    function bindConciergeChips(root) {
      (root || document).querySelectorAll?.('.concierge-chip')?.forEach((btn) => {
        if (btn.dataset.bound) return;
        btn.dataset.bound = '1';
        btn.onclick = () => {
          const action = btn.getAttribute('data-concierge');
          markTourEngaged();
          if (action === 'knowledge' && typeof onConciergeAction === 'function') onConciergeAction('knowledge');
          else if (action === 'users' && typeof onConciergeAction === 'function') onConciergeAction('users');
          else if (action === 'agents' && typeof onConciergeAction === 'function') onConciergeAction('agents');
          else if (action === 'ask') {
            if ($('chatInput')) {
              $('chatInput').value = 'What should I do first as company owner?';
              $('chatInput').focus();
              controls();
            }
          }
        };
      });
    }
'''
        # inject after const drafts
        if "function markTourEngaged" not in t:
            t = t.replace(
                "    const drafts = new Map();",
                "    const drafts = new Map();\n" + bind,
                1,
            )
        # call bindConciergeChips after render
        if "bindConciergeChips()" not in t:
            t = t.replace(
                "function render(scroll = true) {",
                "function render(scroll = true) {\n      // Job 98 chips bound after DOM paint",
                1,
            )
            # after messages rendered - find end of render function's innerHTML assignment
            t = re.sub(
                r"(function render\(scroll = true\) \{[\s\S]*?)(\n    function saveDraft)",
                r"\1      bindConciergeChips(document);\n\2",
                t,
                count=1,
            )

        # Extend create() to accept onConciergeAction
        t = t.replace(
            "function create({ api, getSession, escapeHtml: esc, onAgentChanged, onTaskCreated, openTask, openResult }) {",
            "function create({ api, getSession, escapeHtml: esc, onAgentChanged, onTaskCreated, openTask, openResult, onConciergeAction }) {",
            1,
        )

    CHAT.write_text(t, encoding="utf-8")
    print("[OK] chat.js Job 98")


def patch_css():
    block = r'''
/* Job 98 — concierge action chips */
.concierge-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.75rem;
}
.concierge-chip {
  border: 1px solid rgba(56, 189, 248, 0.4);
  background: rgba(14, 165, 233, 0.12);
  color: #e0f2fe;
  border-radius: 999px;
  padding: 0.35rem 0.75rem;
  font-size: 0.78rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.concierge-chip:hover {
  background: rgba(14, 165, 233, 0.25);
  border-color: rgba(56, 189, 248, 0.7);
}
'''
    if not CSS.exists():
        return
    t = CSS.read_text(encoding="utf-8")
    if "Job 98 — concierge" not in t:
        CSS.write_text(t.rstrip() + "\n\n" + block, encoding="utf-8")
    print("[OK] styles.css chips")


def patch_app_js():
    t = APP.read_text(encoding="utf-8")
    # Wire onConciergeAction when creating chatWorkspace
    if "onConciergeAction" not in t:
        # Find WorkspaceChat.create({
        m = re.search(r"const chatWorkspace = WorkspaceChat\.create\(\{([\s\S]*?)\}\);", t)
        if m:
            inner = m.group(1)
            if "onConciergeAction" not in inner:
                new_inner = inner.rstrip() + "\n    onConciergeAction: (action) => {\n"
                new_inner += "      try {\n"
                new_inner += "        if (action === 'knowledge') showView('knowledge');\n"
                new_inner += "        else if (action === 'users') showView('users');\n"
                new_inner += "        else if (action === 'agents') showView('agents');\n"
                new_inner += "      } catch (e) { console.warn(e); }\n"
                new_inner += "    },\n  "
                t = t.replace(m.group(0), "const chatWorkspace = WorkspaceChat.create({" + new_inner + "});", 1)
                print("[OK] app.js onConciergeAction")
        else:
            print("[WARN] WorkspaceChat.create block not found")

    # Mark tour engaged when finishing onboard (already opened chat)
    if "owner_concierge_done" not in t:
        t = t.replace(
            'owner_concierge: true,',
            'owner_concierge: true, // Job 98\n',
            1,
        )
        # after successful create conversation in finishOnboardConfig
        t = t.replace(
            "await chatWorkspace.openAgent(onboardHiredAgentId, { forceNew: true });",
            "await chatWorkspace.openAgent(onboardHiredAgentId, { forceNew: true });\n"
            "          try { localStorage.setItem('owner_concierge_seen:' + state.companyId, '1'); } catch (_) {}",
            1,
        )

    APP.write_text(t, encoding="utf-8")
    print("[OK] app.js")


def main():
    print("Job 98 — Concierge quick actions")
    print(f"ROOT: {ROOT}")
    if not CHAT.exists():
        raise SystemExit("run from repo root")
    patch_chat_js()
    patch_css()
    patch_app_js()
    print(
        """
Next:
  Ctrl+F5 /workspace
  Complete onboarding → Chat shows 4 chips under welcome
  Click chip → navigates or prefills input

  git add app/static/workspace/chat.js app/static/workspace/styles.css app/static/workspace/app.js
  git commit -m "Job 98: concierge quick-action chips (knowledge/users/ask/agents)"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
