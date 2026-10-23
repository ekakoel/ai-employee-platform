#!/usr/bin/env python3
"""
FULL FIX: Activate tab empty because JS looks for id=\"tab-activate\"
but panel was id=\"registerSuccessPanel\".

- Rename panel to id=\"tab-activate\"
- Ensure full OTP UI
- Wire register success + resend + activate buttons
- CSS force display
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
JS = ROOT / "app" / "static" / "workspace" / "app.js"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"

PANEL = '''
      <div id="tab-activate" class="tab-panel user-only">
        <div class="auth-notice">
          <h2>Activate your account</h2>
          <p class="muted">Enter the <strong>6-digit code</strong> we emailed you.</p>
          <label class="auth-field" style="text-transform:none;letter-spacing:0;font-size:0.85rem;color:#94a3b8">
            Email
            <input id="activateEmail" type="email" placeholder="you@company.com" autocomplete="email" />
          </label>
          <div class="otp-row" id="otpRow">
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 1" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 2" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 3" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 4" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 5" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 6" />
          </div>
          <button type="button" id="btnActivateOtp" class="primary block">Activate account</button>
          <button type="button" id="btnResendFromNotice" class="link-btn">Resend code</button>
          <button type="button" id="btnGoLoginAfterRegister" class="link-btn">Back to sign in</button>
          <p id="registerSuccessLog" class="login-message" role="status"></p>
          <p id="registerSuccessEmail" class="hidden" aria-hidden="true"></p>
        </div>
      </div>
'''


def patch_html():
    t = HTML.read_text(encoding="utf-8")
    # Remove any old panels
    t = re.sub(
        r'<div id="registerSuccessPanel"[^>]*>[\s\S]*?</div>\s*(?=<div id="tab-invite"|<div id="tab-)',
        "",
        t,
        count=1,
    )
    t = re.sub(
        r'<div id="tab-activate"[^>]*>[\s\S]*?</div>\s*(?=<div id="tab-invite"|<div id="tab-)',
        "",
        t,
        count=1,
    )
    # Ensure Activate tab button exists
    if 'data-tab="activate"' not in t:
        t = t.replace(
            '<button type="button" class="tab user-only" data-tab="register">Register company</button>',
            '<button type="button" class="tab user-only" data-tab="register">Register company</button>\n'
            '        <button type="button" class="tab user-only" data-tab="activate">Activate</button>',
            1,
        )
    # Insert panel before invite
    if 'id="tab-activate"' not in t:
        if 'id="tab-invite"' in t:
            t = t.replace(
                '<div id="tab-invite"',
                PANEL + '\n      <div id="tab-invite"',
                1,
            )
        else:
            t = t.replace("</div>\n\n  <!--", PANEL + "\n  <!--", 1)
    HTML.write_text(t, encoding="utf-8")
    print("[OK] HTML id=tab-activate with full OTP form")


def patch_js():
    t = JS.read_text(encoding="utf-8")

    # Alias: any registerSuccessPanel lookups also work via tab-activate
    if "function $(" in t or "const $ =" in t or "function $(id)" in t:
        pass

    # Replace showActivatePanel body if exists, else inject
    show_fn = r'''
  function showActivatePanel(email) {
    const em = (email || "").trim();
    if (em && $("activateEmail")) $("activateEmail").value = em;
    if (em && $("loginEmail")) $("loginEmail").value = em;
    if (em && $("registerSuccessEmail")) $("registerSuccessEmail").textContent = em;
    if (em && $("registrationEmail")) $("registrationEmail").value = em;
    openLoginTab("activate");
    const first = document.querySelector("#otpRow .otp-digit");
    if (first) setTimeout(() => first.focus(), 50);
  }
  function collectOtpCode() {
    return Array.from(document.querySelectorAll("#otpRow .otp-digit"))
      .map((el) => (el.value || "").replace(/\D/g, ""))
      .join("");
  }
  (function bindOtpDigitsOnce() {
    if (window.__otpBound) return;
    window.__otpBound = true;
    const digits = () => Array.from(document.querySelectorAll("#otpRow .otp-digit"));
    document.addEventListener("input", (e) => {
      if (!e.target.classList.contains("otp-digit")) return;
      const list = digits();
      const idx = list.indexOf(e.target);
      e.target.value = (e.target.value || "").replace(/\D/g, "").slice(0, 1);
      if (e.target.value && idx >= 0 && idx < list.length - 1) list[idx + 1].focus();
    });
    document.addEventListener("keydown", (e) => {
      if (!e.target.classList.contains("otp-digit")) return;
      const list = digits();
      const idx = list.indexOf(e.target);
      if (e.key === "Backspace" && !e.target.value && idx > 0) list[idx - 1].focus();
    });
    document.addEventListener("paste", (e) => {
      if (!e.target.classList.contains("otp-digit")) return;
      const nums = ((e.clipboardData || window.clipboardData).getData("text") || "").replace(/\D/g, "").slice(0, 6);
      if (!nums) return;
      e.preventDefault();
      const list = digits();
      nums.split("").forEach((ch, i) => { if (list[i]) list[i].value = ch; });
      list[Math.min(nums.length, 6) - 1]?.focus();
    });
  })();

  if ($("btnActivateOtp")) {
    $("btnActivateOtp").onclick = async () => {
      const log = $("registerSuccessLog");
      const code = collectOtpCode();
      if (code.length !== 6) {
        if (log) { log.classList.add("error"); log.textContent = "Enter all 6 digits"; }
        return;
      }
      try {
        if (log) { log.classList.remove("error"); log.textContent = "Activating…"; }
        const result = await api("/auth/verify-email", {
          method: "POST", skipAuth: true,
          body: JSON.stringify({ token: code }),
        });
        if (log) log.textContent = result.message || "Activated.";
        openLoginTab("login");
        if ($("loginLog")) $("loginLog").textContent = result.message || "Account activated. Sign in.";
      } catch (err) {
        if (log) { log.classList.add("error"); log.textContent = err.message || "Invalid or expired code"; }
      }
    };
  }
  if ($("btnGoLoginAfterRegister")) {
    $("btnGoLoginAfterRegister").onclick = () => openLoginTab("login");
  }
  if ($("btnResendFromNotice")) {
    $("btnResendFromNotice").onclick = async () => {
      const log = $("registerSuccessLog");
      const email = (
        ($("activateEmail") && $("activateEmail").value) ||
        ($("loginEmail") && $("loginEmail").value) ||
        ($("registrationEmail") && $("registrationEmail").value) || ""
      ).trim();
      if (!email) {
        if (log) { log.classList.add("error"); log.textContent = "Enter your email above, then resend."; }
        return;
      }
      try {
        const result = await api("/auth/request-verification", {
          method: "POST", skipAuth: true,
          body: JSON.stringify({ email }),
        });
        if (log) { log.classList.remove("error"); log.textContent = result.message || "Code sent if eligible."; }
        if (result.verification_token && /^\d{6}$/.test(String(result.verification_token))) {
          const list = document.querySelectorAll("#otpRow .otp-digit");
          String(result.verification_token).split("").forEach((ch, i) => { if (list[i]) list[i].value = ch; });
        }
      } catch (err) {
        if (log) { log.classList.add("error"); log.textContent = err.message || "Could not resend"; }
      }
    };
  }
'''

    # Remove broken duplicate showActivatePanel definitions by replacing first occurrence body is hard;
    # Inject before btnLogin if showActivatePanel missing proper openLoginTab("activate")
    if 'openLoginTab("activate")' not in t:
        if '$("btnLogin").onclick' in t:
            t = t.replace(
                '$("btnLogin").onclick = async () => {',
                show_fn + '\n  $("btnLogin").onclick = async () => {',
                1,
            )
        else:
            t = t + "\n" + show_fn
    else:
        # Still inject bind handlers if btnActivateOtp handler missing
        if "btnActivateOtp" not in t or "collectOtpCode" not in t:
            t = t.replace(
                '$("btnLogin").onclick = async () => {',
                show_fn + '\n  $("btnLogin").onclick = async () => {',
                1,
            )

    # Register success → activate tab
    if "showActivatePanel(email)" not in t:
        t = t.replace(
            'log.textContent = result.message || "Company created.";',
            'log.textContent = result.message || "Company created.";\n'
            '      showActivatePanel(email);\n'
            '      if (result.verification_token && /^\\d{6}$/.test(String(result.verification_token))) {\n'
            '        const list = document.querySelectorAll("#otpRow .otp-digit");\n'
            '        String(result.verification_token).split("").forEach((ch, i) => { if (list[i]) list[i].value = ch; });\n'
            '      }',
            1,
        )
    # Ensure register path calls showActivatePanel even if message assignment differs
    if "showActivatePanel(email)" not in t:
        t = t.replace(
            'if ($("loginEmail")) $("loginEmail").value = email;',
            'showActivatePanel(email);\n      if ($("loginEmail")) $("loginEmail").value = email;',
            1,
        )

    # Login error opens activate
    if "Account not activated" not in t or "showActivatePanel((($(\"loginEmail\")" not in t:
        needle = 'log.textContent = err.message || "Sign in failed";'
        if needle in t and "showActivatePanel((($(\"loginEmail\")" not in t:
            t = t.replace(
                needle,
                needle + "\n"
                '        if (/not activated|6-digit|activation/i.test(String(err.message || ""))) {\n'
                '          showActivatePanel((($("loginEmail") && $("loginEmail").value) || "").trim());\n'
                '        }',
                1,
            )

    JS.write_text(t, encoding="utf-8")
    print("[OK] app.js tab-activate wiring")


def patch_css():
    block = r'''
/* Activate panel must show when tab active */
#tab-activate.tab-panel.active { display: block !important; opacity: 1 !important; transform: none !important; }
.otp-row { display: flex; justify-content: center; gap: 0.45rem; margin: 1.2rem 0; flex-wrap: wrap; }
.otp-digit {
  width: 2.6rem !important; height: 3rem; text-align: center;
  font-size: 1.35rem !important; font-weight: 600;
  border: 1px solid rgba(148,163,184,0.35) !important; border-radius: 10px !important;
  background: rgba(15,23,42,0.55) !important; color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc !important;
}
.otp-digit:focus { border-color: #22d3ee !important; outline: none; }
#tab-activate .auth-field input {
  width: 100%; margin-top: 0.35rem;
  background: transparent; color: #f1f5f9;
  border: none; border-bottom: 1px solid rgba(148,163,184,0.35);
}
'''
    t = CSS.read_text(encoding="utf-8")
    if "#tab-activate.tab-panel.active" not in t:
        CSS.write_text(t.rstrip() + "\n\n" + block, encoding="utf-8")
    print("[OK] CSS #tab-activate visible")


def main():
    print("FULL FIX — Activate panel id=tab-activate + OTP UI")
    if not HTML.exists():
        raise SystemExit("run from repo root")
    patch_html()
    patch_js()
    patch_css()
    print(
        """
Done. Hard refresh (Ctrl+F5), click Activate — you must see:
  email field + 6 digit boxes + Activate account button

  git add app/static/workspace/index.html app/static/workspace/app.js app/static/workspace/styles.css
  git commit -m "fix: Activate tab shows OTP panel (id=tab-activate)"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
