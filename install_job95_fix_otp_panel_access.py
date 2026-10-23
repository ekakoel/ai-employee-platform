#!/usr/bin/env python3
"""
Job 95 fix3 — OTP panel after register + Activate tab when page was closed.
Also clearer login error when email not activated.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
JS = ROOT / "app" / "static" / "workspace" / "app.js"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"
AUTH = ROOT / "app" / "services" / "auth_sessions.py"

OTP_PANEL = '''
      <div id="registerSuccessPanel" class="tab-panel user-only">
        <div class="auth-notice">
          <h2>Activate your account</h2>
          <p class="muted">Enter the <strong>6-digit code</strong> sent to<br><strong id="registerSuccessEmail"></strong></p>
          <div class="otp-row" id="otpRow">
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 1" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 2" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 3" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 4" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 5" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-label="Digit 6" />
          </div>
          <button type="button" id="btnActivateOtp" class="primary block">Activate account</button>
          <button type="button" id="btnResendFromNotice" class="link-btn" type="button">Resend code</button>
          <button type="button" id="btnGoLoginAfterRegister" class="link-btn" type="button">Back to sign in</button>
          <p id="registerSuccessLog" class="login-message" role="status"></p>
        </div>
      </div>
'''


def patch_html():
    t = HTML.read_text(encoding="utf-8")
    # Replace existing success panel entirely
    if 'id="registerSuccessPanel"' in t:
        t = re.sub(
            r'<div id="registerSuccessPanel" class="tab-panel user-only">[\s\S]*?</div>\s*(?=<div id="tab-invite"|<div id="tab-)',
            OTP_PANEL + "\n      ",
            t,
            count=1,
        )
    else:
        t = t.replace(
            '<div id="tab-invite"',
            OTP_PANEL + '\n      <div id="tab-invite"',
            1,
        )

    # Add Activate tab next to Register
    if 'data-tab="activate"' not in t:
        t = t.replace(
            '<button type="button" class="tab user-only" data-tab="register">Register company</button>',
            '<button type="button" class="tab user-only" data-tab="register">Register company</button>\n'
            '        <button type="button" class="tab user-only" data-tab="activate" id="tabActivateBtn">Activate</button>',
            1,
        )
    # Map activate tab -> registerSuccessPanel via id alias: tab-activate
    if 'id="tab-activate"' not in t:
        t = t.replace(
            'id="registerSuccessPanel"',
            'id="registerSuccessPanel" data-also="tab-activate"',
            1,
        )
        # add id tab-activate as same panel - use wrapper: change id to support both
        # Simpler: JS openLoginTab("activate") shows registerSuccessPanel

    HTML.write_text(t, encoding="utf-8")
    print("[OK] HTML OTP panel + Activate tab")


def patch_auth_login():
    if not AUTH.exists():
        return
    t = AUTH.read_text(encoding="utf-8")
    old = """        user = lock_user(db, candidates[0].id)
        active_user(db, user)
        if not verify_password(password, user.password_hash):"""
    new = """        user = lock_user(db, candidates[0].id)
        if user and not user.email_verified:
            raise AuthError(
                "Account not activated. Enter the 6-digit code sent to your email.",
                403,
            )
        active_user(db, user)
        if not verify_password(password, user.password_hash):"""
    if "Account not activated" not in t:
        if old not in t:
            print("[WARN] login patch point not found")
        else:
            t = t.replace(old, new, 1)
            AUTH.write_text(t, encoding="utf-8")
            print("[OK] auth_sessions.login unverified message")
    else:
        print("[OK] login message already present")


def patch_js():
    t = JS.read_text(encoding="utf-8")

    # Helpers always present
    helpers = r'''
  // Job 95 fix3 — OTP helpers + activate access
  function showActivatePanel(email) {
    if (email && $("registerSuccessEmail")) $("registerSuccessEmail").textContent = email;
    if (email && $("registrationEmail") && !$("registrationEmail").value) $("registrationEmail").value = email;
    if (email && $("loginEmail")) $("loginEmail").value = email;
    document.querySelectorAll(".login-tabs .tab, .auth-rail .tab, .tab-panel").forEach((el) => el.classList.remove("active"));
    const tabBtn = document.querySelector('.login-tabs .tab[data-tab="activate"], .auth-rail .tab[data-tab="activate"]');
    if (tabBtn) tabBtn.classList.add("active");
    if ($("registerSuccessPanel")) {
      $("registerSuccessPanel").classList.add("active");
      $("registerSuccessPanel").style.display = "block";
    }
    const first = document.querySelector("#otpRow .otp-digit");
    if (first) first.focus();
  }
  function collectOtpCode() {
    return Array.from(document.querySelectorAll("#otpRow .otp-digit")).map((el) => (el.value || "").replace(/\D/g, "")).join("");
  }
  (function bindOtpDigits() {
    const digits = Array.from(document.querySelectorAll("#otpRow .otp-digit"));
    digits.forEach((el, idx) => {
      el.addEventListener("input", () => {
        el.value = (el.value || "").replace(/\D/g, "").slice(0, 1);
        if (el.value && idx < digits.length - 1) digits[idx + 1].focus();
      });
      el.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && !el.value && idx > 0) digits[idx - 1].focus();
      });
      el.addEventListener("paste", (e) => {
        const nums = ((e.clipboardData || window.clipboardData).getData("text") || "").replace(/\D/g, "").slice(0, 6);
        if (!nums) return;
        e.preventDefault();
        nums.split("").forEach((ch, i) => { if (digits[i]) digits[i].value = ch; });
        digits[Math.min(nums.length, 6) - 1]?.focus();
      });
    });
  })();

  // Tab "activate" opens OTP panel
  document.querySelectorAll('.login-tabs .tab[data-tab="activate"], .auth-rail .tab[data-tab="activate"]').forEach((tab) => {
    tab.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const email = ($("loginEmail") && $("loginEmail").value) || ($("registrationEmail") && $("registrationEmail").value) || "";
      showActivatePanel(email);
    });
  });

  if ($("btnActivateOtp")) {
    $("btnActivateOtp").onclick = async () => {
      const log = $("registerSuccessLog");
      const code = collectOtpCode();
      if (code.length !== 6) {
        if (log) { log.classList.add("error"); log.textContent = "Enter all 6 digits from your email"; }
        return;
      }
      try {
        if (log) { log.classList.remove("error"); log.textContent = "Activating…"; }
        const result = await api("/auth/verify-email", {
          method: "POST", skipAuth: true,
          body: JSON.stringify({ token: code }),
        });
        if (log) log.textContent = result.message || "Activated. You can sign in.";
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
        ($("registerSuccessEmail") && $("registerSuccessEmail").textContent) ||
        ($("registrationEmail") && $("registrationEmail").value) ||
        ($("loginEmail") && $("loginEmail").value) || ""
      ).trim();
      if (!email) {
        if (log) log.textContent = "Enter your email on the Sign in tab first, then open Activate.";
        return;
      }
      try {
        const result = await api("/auth/request-verification", {
          method: "POST", skipAuth: true,
          body: JSON.stringify({ email }),
        });
        if (log) { log.classList.remove("error"); log.textContent = result.message || "If eligible, a new code was sent."; }
        if (result.verification_token && /^\d{6}$/.test(String(result.verification_token))) {
          const digits = document.querySelectorAll("#otpRow .otp-digit");
          String(result.verification_token).split("").forEach((ch, i) => { if (digits[i]) digits[i].value = ch; });
        }
      } catch (err) {
        if (log) { log.classList.add("error"); log.textContent = err.message || "Could not resend"; }
      }
    };
  }
'''

    if "showActivatePanel" not in t:
        if '$("btnLogin").onclick' in t:
            t = t.replace('$("btnLogin").onclick = async () => {', helpers + '\n  $("btnLogin").onclick = async () => {', 1)
        else:
            t = t + "\n" + helpers

    # Force register success to open activate panel
    # Replace the success block inside register handler
    t = re.sub(
        r"if \(\$\(\"registerSuccessEmail\"\)\) \$\(\"registerSuccessEmail\"\)\.textContent = email;[\s\S]*?if \(\$\(\"loginEmail\"\)\) \$\(\"loginEmail\"\)\.value = email;",
        'showActivatePanel(email);\n'
        '      if (result.verification_token && /^\\d{6}$/.test(String(result.verification_token))) {\n'
        '        const digits = document.querySelectorAll("#otpRow .otp-digit");\n'
        '        String(result.verification_token).split("").forEach((ch, i) => { if (digits[i]) digits[i].value = ch; });\n'
        '      }\n'
        '      if ($("loginEmail")) $("loginEmail").value = email;',
        t,
        count=1,
    )

    # Also after log.textContent = result.message on register - ensure showActivatePanel
    if "showActivatePanel(email)" not in t:
        t = t.replace(
            'log.textContent = result.message || "Company created.";',
            'log.textContent = result.message || "Company created.";\n      showActivatePanel(email);',
            1,
        )
        t = t.replace(
            "log.textContent = result.message;",
            'log.textContent = result.message;\n      if (button && button.id === "btnRegisterCompany") showActivatePanel(email);',
            1,
        )

    # Login failure → open activate if not activated
    if "Account not activated" not in t or "showActivatePanel(($(\"loginEmail\")" not in t:
        t = t.replace(
            'log.textContent = err.message || "Sign in failed";',
            'log.textContent = err.message || "Sign in failed";\n'
            '        const msg = String(err.message || "");\n'
            '        if (/not activated|6-digit|activation code/i.test(msg)) {\n'
            '          showActivatePanel((($("loginEmail") && $("loginEmail").value) || "").trim());\n'
            '        }',
            1,
        )

    JS.write_text(t, encoding="utf-8")
    print("[OK] app.js OTP + activate access")


def patch_css_otp():
    if not CSS.exists():
        return
    block = r'''
/* Job 95 fix3 OTP digits */
.otp-row { display:flex; justify-content:center; gap:0.45rem; margin:1.2rem 0; }
.otp-digit {
  width:2.6rem !important; height:3rem; text-align:center;
  font-size:1.35rem !important; font-weight:600;
  border:1px solid rgba(148,163,184,0.35) !important; border-radius:10px !important;
  background:rgba(15,23,42,0.55) !important; color:#f8fafc !important;
}
.otp-digit:focus { border-color:#22d3ee !important; outline:none; }
#registerSuccessPanel.active { display:block !important; }
'''
    t = CSS.read_text(encoding="utf-8")
    if "Job 95 fix3 OTP" not in t:
        CSS.write_text(t.rstrip() + "\n" + block, encoding="utf-8")
    print("[OK] CSS OTP")


def main():
    print("Job 95 fix3 — OTP panel + activate later from login")
    patch_html()
    patch_auth_login()
    patch_js()
    patch_css_otp()
    print(
        """
  # Restart server + Ctrl+F5
  # Register → OTP panel
  # Or Sign in (unverified) → message + Activate tab
  # Or click Activate tab anytime → enter email on Sign in first, Resend code

  git add app/static/workspace/index.html app/static/workspace/app.js \\
          app/static/workspace/styles.css app/services/auth_sessions.py
  git commit -m "Job 95 fix3: OTP panel after register; activate tab; login unverified hint"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
