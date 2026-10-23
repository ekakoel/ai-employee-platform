#!/usr/bin/env python3
"""
Job 93 — Aurora auth shell + email activation (no inline verify) +
login identifier field + post-login onboarding gate (Company → Hire → Config).

Run from repo root:
  python install_job93_onboarding_aurora.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"
# styles may live under assets/
CSS_CANDIDATES = [
    ROOT / "app" / "static" / "workspace" / "styles.css",
    ROOT / "app" / "static" / "workspace" / "assets" / "styles.css",
]
JS = ROOT / "app" / "static" / "workspace" / "app.js"
AUTH_DIR = ROOT / "app" / "static" / "auth"
ACTIVATE = AUTH_DIR / "activate.html"


AURORA_CSS = r'''
/* ===== Job 93 — Aurora auth + centered onboarding card ===== */
.login-gate {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1.5rem;
  overflow: hidden;
  background: #0b1220;
}
.login-gate::before {
  content: "";
  position: absolute;
  inset: -40%;
  background:
    radial-gradient(ellipse 50% 40% at 20% 30%, rgba(56, 189, 248, 0.35), transparent 55%),
    radial-gradient(ellipse 45% 35% at 80% 20%, rgba(167, 139, 250, 0.32), transparent 50%),
    radial-gradient(ellipse 40% 40% at 60% 80%, rgba(45, 212, 191, 0.22), transparent 50%),
    radial-gradient(ellipse 35% 30% at 30% 70%, rgba(251, 191, 36, 0.12), transparent 50%);
  animation: aurora-drift 18s ease-in-out infinite alternate;
  pointer-events: none;
  z-index: 0;
}
@keyframes aurora-drift {
  0%   { transform: translate3d(-2%, -1%, 0) scale(1); }
  50%  { transform: translate3d(3%, 2%, 0) scale(1.05); }
  100% { transform: translate3d(-1%, 3%, 0) scale(1.02); }
}
.login-card {
  position: relative;
  z-index: 1;
  width: min(440px, 100%);
  padding: 1.75rem 1.6rem 1.5rem;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
  color: #e2e8f0;
}
.login-brand h1 { font-size: 1.25rem; letter-spacing: -0.02em; }
.login-brand p { color: #94a3b8; font-size: 0.85rem; }
.login-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin: 1rem 0 1.1rem;
}
.login-tabs .tab {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: transparent;
  color: #94a3b8;
  border-radius: 999px;
  padding: 0.35rem 0.75rem;
  font-size: 0.8rem;
}
.login-tabs .tab.active {
  color: #f8fafc;
  border-color: rgba(56, 189, 248, 0.55);
  background: rgba(14, 165, 233, 0.15);
}
.login-card label {
  display: block;
  font-size: 0.8rem;
  color: #cbd5e1;
  margin-bottom: 0.75rem;
}
.login-card input[type="text"],
.login-card input[type="email"],
.login-card input[type="password"],
.login-card input:not([type]) {
  width: 100%;
  margin-top: 0.3rem;
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: rgba(15, 23, 42, 0.85);
  color: #f1f5f9;
}
.login-card .primary.block {
  width: 100%;
  margin-top: 0.5rem;
  border: none;
  border-radius: 10px;
  padding: 0.65rem 1rem;
  font-weight: 600;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: #fff;
  cursor: pointer;
}
.login-card .primary.block:hover { filter: brightness(1.06); }
.login-message { font-size: 0.85rem; color: #94a3b8; min-height: 1.2em; }
.login-message.error { color: #fca5a5; }
.activation-banner {
  margin-top: 0.75rem;
  padding: 0.75rem 0.9rem;
  border-radius: 10px;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #a7f3d0;
  font-size: 0.85rem;
  line-height: 1.4;
}
/* Onboarding wizard (post-login, pre-home) */
#onboardingWizard.hidden { display: none !important; }
#onboardingWizard {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  background: #0b1220;
}
#onboardingWizard::before {
  content: "";
  position: absolute;
  inset: -30%;
  background:
    radial-gradient(ellipse 50% 40% at 25% 35%, rgba(56, 189, 248, 0.3), transparent 55%),
    radial-gradient(ellipse 40% 35% at 75% 25%, rgba(167, 139, 250, 0.28), transparent 50%),
    radial-gradient(ellipse 40% 40% at 55% 75%, rgba(45, 212, 191, 0.2), transparent 50%);
  animation: aurora-drift 18s ease-in-out infinite alternate;
  pointer-events: none;
}
.onboard-card {
  position: relative;
  z-index: 1;
  width: min(520px, 94vw);
  padding: 1.75rem;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(15, 23, 42, 0.78);
  backdrop-filter: blur(16px);
  color: #e2e8f0;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
}
.onboard-steps {
  display: flex;
  gap: 0.4rem;
  margin-bottom: 1rem;
  font-size: 0.72rem;
  color: #94a3b8;
}
.onboard-steps span {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.25);
}
.onboard-steps span.active {
  color: #f8fafc;
  border-color: rgba(56, 189, 248, 0.5);
  background: rgba(14, 165, 233, 0.15);
}
.agent-pick-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem;
  margin: 1rem 0;
}
.agent-pick {
  text-align: left;
  padding: 0.85rem;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: rgba(15, 23, 42, 0.6);
  color: #e2e8f0;
  cursor: pointer;
}
.agent-pick:hover, .agent-pick.selected {
  border-color: rgba(56, 189, 248, 0.55);
  background: rgba(14, 165, 233, 0.12);
}
.agent-pick .icon { font-size: 1.4rem; margin-bottom: 0.25rem; }
.agent-pick strong { display: block; font-size: 0.9rem; }
.agent-pick small { color: #94a3b8; font-size: 0.75rem; }
'''


def resolve_css() -> Path:
    for c in CSS_CANDIDATES:
        if c.exists():
            return c
    return CSS_CANDIDATES[0]


def patch_css() -> None:
    path = resolve_css()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(AURORA_CSS, encoding="utf-8")
        print(f"[OK] created {path}")
        return
    t = path.read_text(encoding="utf-8")
    if "Job 93 — Aurora" in t:
        print(f"[OK] {path.name} aurora already present")
        return
    # Append; also soften old login-gate if present by appending overrides
    path.write_text(t.rstrip() + "\n\n" + AURORA_CSS, encoding="utf-8")
    print(f"[OK] {path} aurora CSS")


def patch_html() -> None:
    if not HTML.exists():
        print("[SKIP] index.html")
        return
    t = HTML.read_text(encoding="utf-8")

    # Login identifier field
    t = t.replace(
        '''        <label for="loginEmail">Email
          <input id="loginEmail" type="email" placeholder="you@company.com" autocomplete="username" required />
        </label>''',
        '''        <label for="loginEmail">Email, username, or phone
          <input id="loginEmail" type="text" placeholder="you@company.com / username / phone" autocomplete="username" required />
        </label>''',
    )

    # Register copy + hide token verify UI (activation via email only)
    old_reg = '''      <div id="tab-register" class="tab-panel user-only">
        <p class="muted">Step 1 — Register your business. You become the <strong>Owner</strong>. After email verification, complete the company profile in the workspace.</p>
        <ol class="muted" style="margin:0 0 1rem 1.1rem;padding:0;font-size:.85rem;line-height:1.45">
          <li>Create company + owner account</li>
          <li>Verify email</li>
          <li>Sign in → Company profile (industry &amp; contact)</li>
          <li>Users &amp; Roles → invite staff and set job positions</li>
        </ol>
        <label>Company name<input id="registrationCompany" maxlength="200" required /></label>
        <label>Owner name<input id="registrationName" maxlength="200" required /></label>
        <label>Owner email<input id="registrationEmail" type="email" autocomplete="email" required /></label>
        <label>Password<input id="registrationPassword" type="password" minlength="8" autocomplete="new-password" required /></label>
        <button id="btnRegisterCompany" class="primary block">Create company</button>
        <p id="registrationLog" class="login-message" role="status"></p>
        <div id="verificationPanel" class="hidden">
          <label>Verification token<input id="verificationToken" autocomplete="off" /></label>
          <button id="btnVerifyEmail" class="secondary block">Verify email</button>
        </div>
        <button id="btnResendVerification" class="link-btn" type="button">Request verification again</button>
      </div>'''

    # Flexible match - replace verification panel section and intro
    t = re.sub(
        r'<div id="tab-register" class="tab-panel user-only">[\s\S]*?<button id="btnRegisterCompany"',
        '''<div id="tab-register" class="tab-panel user-only">
        <p class="muted">Create your company. You become the <strong>Owner</strong>. Activate via the link we email you — then sign in.</p>
        <label>Company name<input id="registrationCompany" maxlength="200" required /></label>
        <label>Your name<input id="registrationName" maxlength="200" required /></label>
        <label>Work email<input id="registrationEmail" type="email" autocomplete="email" required /></label>
        <label>Password<input id="registrationPassword" type="password" minlength="8" autocomplete="new-password" required /></label>
        <button id="btnRegisterCompany"''',
        t,
        count=1,
    )
    # Hide token panel - replace verification panel with activation banner area
    t = re.sub(
        r'<div id="verificationPanel" class="hidden">[\s\S]*?</div>\s*'
        r'<button id="btnResendVerification"[^>]*>[\s\S]*?</button>',
        '''<div id="verificationPanel" class="hidden">
          <div class="activation-banner" id="activationBanner">
            Check your email for an activation link. After activating, sign in here.
          </div>
          <button id="btnResendVerification" class="link-btn" type="button">Resend activation email</button>
          <input id="verificationToken" type="hidden" />
          <button id="btnVerifyEmail" type="button" class="hidden" tabindex="-1" aria-hidden="true">Verify</button>
        </div>''',
        t,
        count=1,
    )

    # Onboarding wizard shell before closing body
    if 'id="onboardingWizard"' not in t:
        wizard = '''
  <!-- Job 93 — post-login onboarding wizard -->
  <div id="onboardingWizard" class="hidden" aria-live="polite">
    <div class="onboard-card">
      <div class="onboard-steps">
        <span data-step="1" class="active">1 · Company</span>
        <span data-step="2">2 · Hire AI</span>
        <span data-step="3">3 · Configure</span>
      </div>
      <div id="onboardPanel1">
        <h2>Set up your company</h2>
        <p class="muted">A few details so your AI employees work in the right context.</p>
        <p class="muted">Continue in <strong>Company profile</strong> — save name, contact, and industry.</p>
        <button type="button" id="btnOnboardGoCompany" class="primary block">Open company profile</button>
      </div>
      <div id="onboardPanel2" class="hidden">
        <h2>Hire your first AI Employee</h2>
        <p class="muted">Pick a specialist. You can hire more later.</p>
        <div class="agent-pick-grid" id="onboardAgentGrid">
          <button type="button" class="agent-pick" data-slug="reservation"><div class="icon">🏨</div><strong>Reservation</strong><small>Booking &amp; availability</small></button>
          <button type="button" class="agent-pick" data-slug="contract-manager"><div class="icon">📄</div><strong>Contracts</strong><small>Review &amp; obligations</small></button>
          <button type="button" class="agent-pick" data-slug="quotation"><div class="icon">💰</div><strong>Quotation</strong><small>Pricing &amp; quotes</small></button>
          <button type="button" class="agent-pick" data-slug="support"><div class="icon">💬</div><strong>Support</strong><small>Answers from knowledge</small></button>
        </div>
        <button type="button" id="btnOnboardHire" class="primary block">Hire selected</button>
        <p id="onboardHireLog" class="login-message"></p>
      </div>
      <div id="onboardPanel3" class="hidden">
        <h2>Configure your AI Employee</h2>
        <p class="muted">Name them and open full settings anytime from AI Employees.</p>
        <label>Display name<input id="onboardAgentName" maxlength="120" placeholder="e.g. Maya · Reservations" /></label>
        <button type="button" id="btnOnboardFinish" class="primary block">Finish setup</button>
        <button type="button" id="btnOnboardSkipConfig" class="link-btn">Skip for now</button>
        <p id="onboardConfigLog" class="login-message"></p>
      </div>
    </div>
  </div>
'''
        t = t.replace("</body>", wizard + "\n</body>")

    HTML.write_text(t, encoding="utf-8")
    print(f"[OK] {HTML}")


def patch_js() -> None:
    if not JS.exists():
        print("[SKIP] app.js")
        return
    t = JS.read_text(encoding="utf-8")

    # Register: show activation panel, hide token UX
    old_reg_success = '''      log.textContent = result.message;
      $("verificationPanel").classList.remove("hidden");
      if (result.verification_token) $("verificationToken").value = result.verification_token;
      $("loginEmail").value = email;'''
    new_reg_success = '''      log.textContent = result.message || "Company created.";
      if ($("verificationPanel")) $("verificationPanel").classList.remove("hidden");
      if ($("activationBanner")) {
        $("activationBanner").textContent =
          "We sent an activation link to " + email + ". Open it, then sign in. (Dev: token may appear in API logs.)";
      }
      // Dev convenience only — never block UI on token paste
      if (result.verification_token && $("verificationToken")) {
        $("verificationToken").value = result.verification_token;
      }
      if ($("loginEmail")) $("loginEmail").value = email;'''
    if old_reg_success in t:
        t = t.replace(old_reg_success, new_reg_success)
    else:
        t = t.replace(
            'if (result.verification_token) $("verificationToken").value = result.verification_token;',
            'if (result.verification_token && $("verificationToken")) $("verificationToken").value = result.verification_token;\n'
            '      if ($("activationBanner")) $("activationBanner").textContent = "Check your email to activate, then sign in.";',
            1,
        )

    # Login: treat field as identifier; API still email for now
    t = t.replace(
        'if (!email || !password) throw new Error("Email and password are required");',
        'if (!email || !password) throw new Error("Email/username/phone and password are required");',
    )

    # After applyAuthSession success path - inject onboarding router
    # Find applyAuthSession definition or after await applyAuthSession(body);
    if "routePostLoginOnboarding" not in t:
        helper = r'''
  // Job 93 — post-login onboarding wizard
  let onboardHiredAgentId = null;
  function setOnboardStep(n) {
    document.querySelectorAll("#onboardingWizard .onboard-steps span").forEach((el) => {
      el.classList.toggle("active", String(el.getAttribute("data-step")) === String(n));
    });
    ["1", "2", "3"].forEach((i) => {
      const p = $("onboardPanel" + i);
      if (p) p.classList.toggle("hidden", String(i) !== String(n));
    });
  }
  function showOnboardingWizard(step) {
    const w = $("onboardingWizard");
    if (!w) return;
    w.classList.remove("hidden");
    setOnboardStep(step || 1);
  }
  function hideOnboardingWizard() {
    const w = $("onboardingWizard");
    if (w) w.classList.add("hidden");
  }
  async function routePostLoginOnboarding() {
    try {
      if (!state.companyId) return;
      const company = await api(`/companies/${state.companyId}`);
      state.onboardingStatus = company.onboarding_status || "pending";
      if (state.onboardingStatus !== "complete") {
        showOnboardingWizard(1);
        return;
      }
      let agents = [];
      try { agents = await api(`/companies/${state.companyId}/agents`); } catch (_) {}
      if (!agents || !agents.length) {
        showOnboardingWizard(2);
        return;
      }
      hideOnboardingWizard();
    } catch (_) {
      /* non-blocking */
    }
  }
  if ($("btnOnboardGoCompany")) {
    $("btnOnboardGoCompany").onclick = () => {
      hideOnboardingWizard();
      try { showView("company"); } catch (_) {}
    };
  }
  document.querySelectorAll("#onboardAgentGrid .agent-pick").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#onboardAgentGrid .agent-pick").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
    });
  });
  if ($("btnOnboardHire")) {
    $("btnOnboardHire").onclick = async () => {
      const log = $("onboardHireLog");
      const selected = document.querySelector("#onboardAgentGrid .agent-pick.selected");
      if (!selected) {
        if (log) log.textContent = "Select an AI Employee type";
        return;
      }
      const slug = selected.getAttribute("data-slug");
      try {
        if (log) log.textContent = "Hiring…";
        const catalog = await api("/agent-catalog");
        const item = (catalog || []).find((c) => c.slug === slug) || (catalog || [])[0];
        if (!item) throw new Error("Catalog empty");
        const nameInput = $("onboardAgentName");
        const hireName = (nameInput && nameInput.value.trim()) || selected.querySelector("strong")?.textContent || "AI Employee";
        const hired = await api(`/companies/${state.companyId}/agents/${item.id}/hire`, {
          method: "POST",
          body: JSON.stringify({ name: hireName }),
        });
        onboardHiredAgentId = hired.id || hired.agent_instance_id;
        if (log) log.textContent = "Hired. Configure next.";
        if (nameInput) nameInput.value = hireName;
        setOnboardStep(3);
      } catch (err) {
        if (log) log.textContent = err.message || "Hire failed";
      }
    };
  }
  async function finishOnboardConfig() {
    const log = $("onboardConfigLog");
    try {
      const name = ($("onboardAgentName") && $("onboardAgentName").value.trim()) || "";
      if (onboardHiredAgentId && name) {
        try {
          await api(`/companies/${state.companyId}/agents/${onboardHiredAgentId}`, {
            method: "PATCH",
            body: JSON.stringify({ name }),
          });
        } catch (_) { /* optional endpoint */ }
      }
      hideOnboardingWizard();
      try { showView("home"); } catch (_) { try { showView("agents"); } catch (__) {} }
    } catch (err) {
      if (log) log.textContent = err.message || "Could not finish";
    }
  }
  if ($("btnOnboardFinish")) $("btnOnboardFinish").onclick = () => finishOnboardConfig();
  if ($("btnOnboardSkipConfig")) $("btnOnboardSkipConfig").onclick = () => {
    hideOnboardingWizard();
    try { showView("home"); } catch (_) {}
  };

'''
        # Insert before btnLogin handler
        t = t.replace(
            '  $("btnLogin").onclick = async () => {',
            helper + '\n  $("btnLogin").onclick = async () => {',
            1,
        )
        t = t.replace(
            "      await applyAuthSession(body);",
            "      await applyAuthSession(body);\n      await routePostLoginOnboarding();",
            1,
        )

    # After company profile save success — advance wizard to hire if open
    if "btnSaveCompanyProfile" in t and "showOnboardingWizard(2)" not in t:
        # soft: after successful save that sets complete, try step 2
        t = t.replace(
            "state.onboardingStatus = company.onboarding_status;",
            "state.onboardingStatus = company.onboarding_status;\n"
            "      if (company.onboarding_status === \"complete\" && $(\"onboardingWizard\") &&\n"
            "          !$(\"onboardingWizard\").classList.contains(\"hidden\")) {\n"
            "        showOnboardingWizard(2);\n"
            "      }",
            1,
        )

    JS.write_text(t, encoding="utf-8")
    print(f"[OK] {JS}")


def write_activate_page() -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    html = r'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Activate account — AI Employee Platform</title>
  <style>
    body { margin:0; font-family: system-ui, sans-serif; background:#0b1220; color:#e2e8f0; min-height:100vh; display:grid; place-items:center; }
    body::before { content:""; position:fixed; inset:-40%;
      background: radial-gradient(ellipse 50% 40% at 20% 30%, rgba(56,189,248,.35), transparent 55%),
                  radial-gradient(ellipse 45% 35% at 80% 20%, rgba(167,139,250,.32), transparent 50%);
      animation: a 18s ease-in-out infinite alternate; z-index:0; }
    @keyframes a { from{transform:translate(-2%,0)} to{transform:translate(3%,2%)} }
    .card { position:relative; z-index:1; width:min(420px,92vw); padding:1.75rem; border-radius:16px;
      background:rgba(15,23,42,.78); border:1px solid rgba(255,255,255,.1); backdrop-filter:blur(16px); }
    a { color:#7dd3fc; }
    .ok { color:#6ee7b7; }
    .err { color:#fca5a5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Activate your account</h1>
    <p id="msg">Activating…</p>
    <p><a href="/workspace">Go to sign in</a></p>
  </div>
  <script>
    (async () => {
      const msg = document.getElementById("msg");
      const params = new URLSearchParams(location.search);
      const token = params.get("token") || params.get("verify") || "";
      if (!token) {
        msg.textContent = "Missing activation token. Open the link from your email.";
        msg.className = "err";
        return;
      }
      try {
        const res = await fetch("/api/v1/auth/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || data.message || res.statusText);
        msg.textContent = data.message || "Email verified. You can sign in.";
        msg.className = "ok";
      } catch (e) {
        msg.textContent = e.message || "Activation failed";
        msg.className = "err";
      }
    })();
  </script>
</body>
</html>
'''
    ACTIVATE.write_text(html, encoding="utf-8")
    print(f"[OK] {ACTIVATE}")

    # Wire route in main.py if missing
    main = ROOT / "app" / "main.py"
    if main.exists():
        mt = main.read_text(encoding="utf-8")
        if "/activate" not in mt:
            snippet = '''
@app.get("/activate", response_class=HTMLResponse)
@app.get("/activate/", response_class=HTMLResponse)
def activate_account_page():
    """Job 93 — email activation landing (token query param)."""
    path = AUTH_DIR / "activate.html"
    if path.is_file():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return HTMLResponse("<p>Activation page missing.</p>", status_code=404)

'''
            # after forgot-password route block
            if "forgot_password_page" in mt:
                mt = mt.replace(
                    "def forgot_password_page():",
                    "def forgot_password_page():",
                    1,
                )
                # append before last line or after forgot handler
                idx = mt.find("def forgot_password_page")
                # find next def or end of function - simpler append before workspace route
                if "@app.get(\"/workspace\")" in mt:
                    mt = mt.replace(
                        '@app.get("/workspace")',
                        snippet + '@app.get("/workspace")',
                        1,
                    )
                else:
                    mt = mt.rstrip() + "\n" + snippet
                main.write_text(mt, encoding="utf-8")
                print("[OK] main.py /activate route")
            else:
                print("[WARN] main.py — add /activate route manually if needed")


def main() -> int:
    print("Job 93 — Aurora onboarding + activation email + hire wizard")
    print(f"ROOT: {ROOT}")
    if not (ROOT / "app").is_dir():
        raise SystemExit("run from repo root")
    patch_css()
    patch_html()
    patch_js()
    write_activate_page()
    print(
        """
Next:
  # Hard refresh workspace (Ctrl+F5)
  # Register → message "check email" (no token form)
  # Open /activate?token=... (dev token from API) → login
  # Pending company → wizard step 1 → save company → hire → configure

  git add app/static/workspace/index.html app/static/workspace/app.js \\
          app/static/workspace/styles.css app/static/workspace/assets/styles.css \\
          app/static/auth/activate.html app/main.py
  git commit -m "Job 93: aurora auth, email activation UX, onboarding hire wizard"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
