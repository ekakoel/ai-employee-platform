#!/usr/bin/env python3
"""
Job 95 — 6-digit email OTP activation UI + fix blank onboarding + transparent autofill.

Run from repo root:
  python install_job95_otp_activation_onboard_fix.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
ONBOARD = ROOT / "app" / "services" / "company_onboarding.py"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"
JS = ROOT / "app" / "static" / "workspace" / "app.js"


def patch_backend_otp() -> None:
    if not ONBOARD.exists():
        print("[SKIP] company_onboarding.py")
        return
    t = ONBOARD.read_text(encoding="utf-8")

    # 6-digit OTP instead of urlsafe token
    t = t.replace(
        "token = secrets.token_urlsafe(32)",
        'token = f"{secrets.randbelow(1_000_000):06d}"  # Job 95: 6-digit OTP',
    )

    # Email body: prefer code over long link
    if "Your activation code is" not in t:
        t = re.sub(
            r"def deliver\(email, subject, route, token\):[\s\S]*?(?=\ndef )",
            '''def deliver(email, subject, route, token):
    if not mail_ready():
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = subject
    # Job 95 — numeric OTP in email body
    body = (
        "Your AI Employee Platform activation code is:\\n\\n"
        f"    {token}\\n\\n"
        "Enter this 6-digit code in the activation screen.\\n"
        "The code is valid for 24 hours.\\n\\n"
        "If you did not register, ignore this email.\\n"
    )
    message.set_content(body)
    try:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise auth_sessions.AuthError("Email delivery temporarily unavailable", 503) from None


''',
            t,
            count=1,
        )

    # register response message
    t = t.replace(
        '"message": "Company created. Verify the owner email before signing in."',
        '"message": "Company created. Enter the 6-digit code we emailed you."',
    )
    t = t.replace(
        '"message": "Email verified. You can sign in."',
        '"message": "Account activated. You can sign in."',
    )

    ONBOARD.write_text(t, encoding="utf-8")
    compile(ONBOARD.read_text(encoding="utf-8"), str(ONBOARD), "exec")
    print("[OK] backend 6-digit OTP + email body")


def patch_html_activation() -> None:
    if not HTML.exists():
        return
    t = HTML.read_text(encoding="utf-8")

    # Activation panel (replace registerSuccessPanel or inject)
    panel = '''
      <div id="registerSuccessPanel" class="tab-panel user-only">
        <div class="auth-notice">
          <div class="brand-orb small" aria-hidden="true"></div>
          <h2>Activate your account</h2>
          <p class="muted">We sent a <strong>6-digit code</strong> to <strong id="registerSuccessEmail"></strong>.</p>
          <div class="otp-row" id="otpRow">
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]" autocomplete="one-time-code" aria-label="Digit 1" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]" autocomplete="one-time-code" aria-label="Digit 2" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]" autocomplete="one-time-code" aria-label="Digit 3" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]" autocomplete="one-time-code" aria-label="Digit 4" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]" autocomplete="one-time-code" aria-label="Digit 5" />
            <input class="otp-digit" maxlength="1" inputmode="numeric" pattern="[0-9]" autocomplete="one-time-code" aria-label="Digit 6" />
          </div>
          <button type="button" id="btnActivateOtp" class="primary block btn-futura">Activate</button>
          <button type="button" id="btnResendFromNotice" class="link-btn">Resend code</button>
          <button type="button" id="btnGoLoginAfterRegister" class="link-btn">Back to sign in</button>
          <p id="registerSuccessLog" class="login-message" role="status"></p>
        </div>
      </div>
'''
    if 'id="registerSuccessPanel"' in t:
        t = re.sub(
            r'<div id="registerSuccessPanel" class="tab-panel user-only">[\s\S]*?</div>\s*(?=<div id="tab-invite"|<div id="tab-)',
            panel + "\n      ",
            t,
            count=1,
        )
    elif 'id="tab-invite"' in t:
        t = t.replace(
            '<div id="tab-invite" class="tab-panel user-only">',
            panel + '\n      <div id="tab-invite" class="tab-panel user-only">',
            1,
        )

    # Ensure onboarding wizard exists and is structured
    if 'id="onboardingWizard"' not in t:
        wiz = '''
  <div id="onboardingWizard" class="hidden" aria-live="polite">
    <div class="onboard-card">
      <div class="onboard-steps">
        <span data-step="1" class="active">1 · Company</span>
        <span data-step="2">2 · Hire AI</span>
        <span data-step="3">3 · Configure</span>
      </div>
      <div id="onboardPanel1">
        <h2>Set up your company</h2>
        <p class="muted">Add organization details so your AI employees have context.</p>
        <button type="button" id="btnOnboardGoCompany" class="primary block btn-futura">Open company profile</button>
      </div>
      <div id="onboardPanel2" class="hidden">
        <h2>Hire your first AI Employee</h2>
        <p class="muted">Pick a specialist to get started.</p>
        <div class="agent-pick-grid" id="onboardAgentGrid">
          <button type="button" class="agent-pick" data-slug="reservation"><div class="icon">🏨</div><strong>Reservation</strong><small>Booking</small></button>
          <button type="button" class="agent-pick" data-slug="contract-manager"><div class="icon">📄</div><strong>Contracts</strong><small>Review</small></button>
          <button type="button" class="agent-pick" data-slug="quotation"><div class="icon">💰</div><strong>Quotation</strong><small>Pricing</small></button>
          <button type="button" class="agent-pick" data-slug="support"><div class="icon">💬</div><strong>Support</strong><small>Knowledge</small></button>
        </div>
        <button type="button" id="btnOnboardHire" class="primary block btn-futura">Hire selected</button>
        <p id="onboardHireLog" class="login-message"></p>
      </div>
      <div id="onboardPanel3" class="hidden">
        <h2>Configure your AI Employee</h2>
        <label class="auth-field">Display name<input id="onboardAgentName" maxlength="120" placeholder="e.g. Maya · Reservations" /></label>
        <button type="button" id="btnOnboardFinish" class="primary block btn-futura">Finish setup</button>
        <button type="button" id="btnOnboardSkipConfig" class="link-btn">Skip for now</button>
        <p id="onboardConfigLog" class="login-message"></p>
      </div>
    </div>
  </div>
'''
        t = t.replace("</body>", wiz + "\n</body>")

    HTML.write_text(t, encoding="utf-8")
    print("[OK] HTML OTP activation panel + onboarding shell")


CSS_EXTRA = r'''
/* Job 95 — OTP + autofill + onboarding visibility */
.otp-row {
  display: flex;
  justify-content: center;
  gap: 0.45rem;
  margin: 1.25rem 0 1rem;
}
.otp-digit {
  width: 2.6rem !important;
  height: 3rem;
  text-align: center;
  font-size: 1.35rem !important;
  font-weight: 600;
  letter-spacing: 0;
  border: 1px solid rgba(148, 163, 184, 0.35) !important;
  border-radius: 10px !important;
  background: rgba(15, 23, 42, 0.45) !important;
  color: #f8fafc !important;
  caret-color: #22d3ee;
}
.otp-digit:focus {
  border-color: #22d3ee !important;
  box-shadow: 0 0 0 2px rgba(34, 211, 238, 0.25) !important;
  outline: none;
}

/* Chrome/Safari autofill — keep dark transparent look */
.login-gate input:-webkit-autofill,
.login-gate input:-webkit-autofill:hover,
.login-gate input:-webkit-autofill:focus,
.login-gate input:-webkit-autofill:active,
#onboardingWizard input:-webkit-autofill {
  -webkit-text-fill-color: #f1f5f9 !important;
  caret-color: #f1f5f9;
  box-shadow: 0 0 0 1000px rgba(15, 23, 42, 0.92) inset !important;
  -webkit-box-shadow: 0 0 0 1000px rgba(15, 23, 42, 0.92) inset !important;
  transition: background-color 99999s ease-out 0s;
  border-bottom-color: rgba(34, 211, 238, 0.5) !important;
}

/* Onboarding must never be a blank white sheet */
#onboardingWizard {
  position: fixed !important;
  inset: 0 !important;
  z-index: 200 !important;
  display: grid !important;
  place-items: center !important;
  min-height: 100vh !important;
  background: #070b14 !important;
  color: #e2e8f0 !important;
}
#onboardingWizard.hidden {
  display: none !important;
}
#onboardingWizard .onboard-card {
  color: #e2e8f0;
  width: min(460px, 94vw);
}
#onboardingWizard h2 {
  color: #f8fafc;
  margin: 0.25rem 0 0.5rem;
}
#onboardingWizard .muted { color: #94a3b8; }
#workspaceApp.hidden-by-onboard {
  visibility: hidden;
}
'''


def patch_css() -> None:
    if not CSS.exists():
        print("[SKIP] styles.css")
        return
    t = CSS.read_text(encoding="utf-8")
    if "Job 95 — OTP" in t:
        start = t.find("/* Job 95 — OTP")
        t = t[:start] + CSS_EXTRA
    else:
        t = t.rstrip() + "\n\n" + CSS_EXTRA
    CSS.write_text(t, encoding="utf-8")
    print("[OK] CSS OTP + autofill + onboarding bg")


def patch_js() -> None:
    if not JS.exists():
        return
    t = JS.read_text(encoding="utf-8")

    otp_js = r'''
  // Job 95 — OTP activation UI
  function collectOtp() {
    return Array.from(document.querySelectorAll("#otpRow .otp-digit"))
      .map((el) => (el.value || "").trim())
      .join("");
  }
  function bindOtpInputs() {
    const digits = Array.from(document.querySelectorAll("#otpRow .otp-digit"));
    digits.forEach((el, idx) => {
      el.addEventListener("input", () => {
        el.value = el.value.replace(/\D/g, "").slice(0, 1);
        if (el.value && idx < digits.length - 1) digits[idx + 1].focus();
      });
      el.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && !el.value && idx > 0) digits[idx - 1].focus();
      });
      el.addEventListener("paste", (e) => {
        const text = (e.clipboardData || window.clipboardData).getData("text") || "";
        const nums = text.replace(/\D/g, "").slice(0, 6);
        if (!nums) return;
        e.preventDefault();
        nums.split("").forEach((ch, i) => { if (digits[i]) digits[i].value = ch; });
        digits[Math.min(nums.length, digits.length) - 1]?.focus();
      });
    });
  }
  bindOtpInputs();

  if ($("btnActivateOtp")) {
    $("btnActivateOtp").onclick = async () => {
      const log = $("registerSuccessLog");
      const code = collectOtp();
      if (code.length !== 6) {
        if (log) log.textContent = "Enter the 6-digit code from your email";
        return;
      }
      try {
        if (log) log.textContent = "Activating…";
        const result = await api("/auth/verify-email", {
          method: "POST",
          skipAuth: true,
          body: JSON.stringify({ token: code }),
        });
        if (log) log.textContent = result.message || "Activated. Sign in.";
        openLoginTab("login");
        if ($("loginLog")) $("loginLog").textContent = result.message || "Account activated. Sign in.";
      } catch (err) {
        if (log) {
          log.classList.add("error");
          log.textContent = err.message || "Invalid or expired code";
        }
      }
    };
  }
  if ($("btnGoLoginAfterRegister")) {
    $("btnGoLoginAfterRegister").onclick = () => {
      if ($("registerSuccessPanel")) $("registerSuccessPanel").classList.remove("active");
      openLoginTab("login");
    };
  }
  if ($("btnResendFromNotice")) {
    $("btnResendFromNotice").onclick = async () => {
      const log = $("registerSuccessLog");
      const email = ($("registerSuccessEmail") && $("registerSuccessEmail").textContent) ||
        ($("registrationEmail") && $("registrationEmail").value) || "";
      try {
        const result = await api("/auth/request-verification", {
          method: "POST",
          skipAuth: true,
          body: JSON.stringify({ email: email.trim() }),
        });
        if (log) log.textContent = result.message || "Code resent if eligible.";
        // Dev: prefill OTP when API returns verification_token
        if (result.verification_token && /^\d{6}$/.test(result.verification_token)) {
          const digits = document.querySelectorAll("#otpRow .otp-digit");
          result.verification_token.split("").forEach((ch, i) => {
            if (digits[i]) digits[i].value = ch;
          });
        }
      } catch (err) {
        if (log) log.textContent = err.message || "Could not resend";
      }
    };
  }

  // After register success — open OTP panel
  // (hook into existing register handler via monkey-patch pattern)
  (function wrapRegisterSuccess() {
    const btn = $("btnRegisterCompany");
    if (!btn || btn.dataset.otpWrapped) return;
    btn.dataset.otpWrapped = "1";
    const prev = btn.onclick;
    // register handler is assigned as onclick later; observe after short delay
    setTimeout(() => {
      const original = btn.onclick;
      if (!original) return;
      btn.onclick = async function (ev) {
        await original.call(this, ev);
        try {
          const email = ($("registrationEmail") && $("registrationEmail").value || "").trim();
          if ($("registerSuccessEmail")) $("registerSuccessEmail").textContent = email;
          document.querySelectorAll(".login-tabs .tab, .tab-panel").forEach((el) => el.classList.remove("active"));
          if ($("registerSuccessPanel")) $("registerSuccessPanel").classList.add("active");
          // Dev convenience: if token field was filled
          const tok = $("verificationToken") && $("verificationToken").value;
          if (tok && /^\d{6}$/.test(tok)) {
            const digits = document.querySelectorAll("#otpRow .otp-digit");
            tok.split("").forEach((ch, i) => { if (digits[i]) digits[i].value = ch; });
          }
          document.querySelector("#otpRow .otp-digit")?.focus();
        } catch (_) {}
      };
    }, 0);
  })();

  // Fix blank onboarding: force dark wizard + show after login when pending
  window.showOnboardingWizard = function (step) {
    const w = $("onboardingWizard");
    if (!w) return;
    w.classList.remove("hidden");
    w.style.display = "grid";
    document.querySelectorAll("#onboardingWizard .onboard-steps span").forEach((el) => {
      el.classList.toggle("active", String(el.getAttribute("data-step")) === String(step || 1));
    });
    ["1", "2", "3"].forEach((i) => {
      const p = $("onboardPanel" + i);
      if (p) p.classList.toggle("hidden", String(i) !== String(step || 1));
    });
    const app = $("workspaceApp") || document.querySelector("[data-workspace-app]");
    if (app) app.classList.add("hidden-by-onboard");
  };
  window.hideOnboardingWizard = function () {
    const w = $("onboardingWizard");
    if (w) {
      w.classList.add("hidden");
      w.style.display = "none";
    }
    const app = $("workspaceApp") || document.querySelector("[data-workspace-app]");
    if (app) app.classList.remove("hidden-by-onboard");
  };
'''

    if "btnActivateOtp" not in t or "Job 95 — OTP" not in t:
        if '$("btnLogin").onclick' in t:
            t = t.replace(
                '$("btnLogin").onclick = async () => {',
                otp_js + '\n  $("btnLogin").onclick = async () => {',
                1,
            )
        else:
            t = t + "\n" + otp_js

    # After register API success, also jump to OTP (direct patch)
    if 'registerSuccessPanel").classList.add("active")' not in t.replace(" ", ""):
        t = t.replace(
            'if ($("loginEmail")) $("loginEmail").value = email;',
            'if ($("loginEmail")) $("loginEmail").value = email;\n'
            '      if ($("registerSuccessEmail")) $("registerSuccessEmail").textContent = email;\n'
            '      document.querySelectorAll(".login-tabs .tab, .tab-panel").forEach((el) => el.classList.remove("active"));\n'
            '      if ($("registerSuccessPanel")) $("registerSuccessPanel").classList.add("active");\n'
            '      if (result.verification_token && /^\\d{6}$/.test(result.verification_token)) {\n'
            '        const digits = document.querySelectorAll("#otpRow .otp-digit");\n'
            '        result.verification_token.split("").forEach((ch, i) => { if (digits[i]) digits[i].value = ch; });\n'
            '      }\n',
            1,
        )

    JS.write_text(t, encoding="utf-8")
    print("[OK] app.js OTP + onboarding show helpers")


def main() -> int:
    print("Job 95 — 6-digit OTP activation + onboarding/autofill fix")
    print(f"ROOT: {ROOT}")
    if not (ROOT / "app").is_dir():
        raise SystemExit("run from repo root")
    patch_backend_otp()
    patch_html_activation()
    patch_css()
    patch_js()
    print(
        """
Next:
  # Restart uvicorn; Ctrl+F5 /workspace
  # Register → OTP panel → enter 6 digits from email (dev: may auto-fill from API)
  # Login → onboarding should show dark aurora wizard (not white blank)

  git add app/services/company_onboarding.py app/static/workspace/
  git commit -m "Job 95: 6-digit OTP activation, onboarding blank fix, autofill transparent"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
