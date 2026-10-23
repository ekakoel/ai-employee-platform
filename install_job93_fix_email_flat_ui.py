#!/usr/bin/env python3
"""
Job 93 FIX — real activation email link (/activate), post-register notice page,
flatter modern auth UI (no heavy cards), .env.example SMTP docs.

Run from repo root:
  python install_job93_fix_email_flat_ui.py
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
ENV_EXAMPLE = ROOT / ".env.example"


def patch_deliver_link() -> None:
    if not ONBOARD.exists():
        print("[SKIP] company_onboarding.py")
        return
    t = ONBOARD.read_text(encoding="utf-8")
    # Prefer /activate?token= for dedicated activation page
    t2 = t.replace(
        'deliver(email, "Verify your company account", "/workspace?verify=", token)',
        'deliver(email, "Activate your AI Employee Platform account", "/activate?token=", token)',
    )
    t2 = t2.replace(
        'deliver(email, "Verify your company account", "/workspace?verify=", token)',
        'deliver(email, "Activate your AI Employee Platform account", "/activate?token=", token)',
    )
    # request_verification path
    t2 = t2.replace(
        'deliver(email, "Verify your company account", "/workspace?verify=", token)',
        'deliver(email, "Activate your AI Employee Platform account", "/activate?token=", token)',
    )
    if "/activate?token=" not in t2:
        t2 = t2.replace('"/workspace?verify="', '"/activate?token="')
    # Richer email body if still minimal
    if "def deliver(email, subject, route, token):" in t2 and "Activate your account:" not in t2:
        t2 = re.sub(
            r"def deliver\(email, subject, route, token\):\n"
            r"    if not mail_ready\(\):\n"
            r"        return\n"
            r"    message = EmailMessage\(\)\n"
            r"    message\[\"From\"\] = settings\.smtp_from\n"
            r"    message\[\"To\"\] = email\n",
            '''def deliver(email, subject, route, token):
    if not mail_ready():
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    link = f"{settings.public_base_url.rstrip('/')}{route}{token}"
    message["Subject"] = subject
    message.set_content(
        "Activate your AI Employee Platform account.\\n\\n"
        f"Open this link (valid 24 hours):\\n{link}\\n\\n"
        "If you did not register, ignore this email.\\n"
    )
    # legacy subject/body assignment below may duplicate Subject — guard
''',
            t2,
            count=1,
        )
        # Remove duplicate Subject/set_content if original had them right after
        # Read original pattern - typically:
        # message["Subject"] = subject
        # message.set_content(f"{settings.public_base_url}{route}{token}")
        t2 = re.sub(
            r"message\[\"Subject\"\] = subject\n"
            r"\s*message\.set_content\([^\)]+\)\n"
            r"\s*# legacy subject/body assignment below may duplicate Subject — guard\n"
            r"\s*message\[\"Subject\"\] = subject\n"
            r"\s*message\.set_content\([^\)]+\)\n",
            "message[\"Subject\"] = subject\n"
            "    link = f\"{settings.public_base_url.rstrip('/')}" + "{route}{token}\"\n"
            "    message.set_content(\n"
            "        \"Activate your AI Employee Platform account.\\n\\n\"\n"
            "        f\"Open this link (valid 24 hours):\\n{link}\\n\\n\"\n"
            "        \"If you did not register, ignore this email.\\n\"\n"
            "    )\n",
            t2,
            count=1,
        )
    # Simpler reliable replace of set_content only
    t2 = re.sub(
        r"message\.set_content\(\s*f?[\"'].*?[\"']\s*\)",
        'message.set_content(\n'
        '        "Activate your AI Employee Platform account.\\n\\n"\n'
        '        f"Open this link (valid 24 hours):\\n'
        '{settings.public_base_url.rstrip(\'/\')}{route}{token}\\n\\n"\n'
        '        "If you did not register, ignore this email.\\n"\n'
        '    )',
        t2,
        count=2,
    )
    ONBOARD.write_text(t2, encoding="utf-8")
    try:
        compile(t2, str(ONBOARD), "exec")
        print("[OK] company_onboarding deliver → /activate?token=")
    except SyntaxError as e:
        print(f"[WARN] onboarding syntax: {e} — restoring safer patch")
        # Safe minimal patch only
        t = ONBOARD.read_text(encoding="utf-8")
        t = t.replace("/workspace?verify=", "/activate?token=")
        ONBOARD.write_text(t, encoding="utf-8")
        print("[OK] link path only")


def patch_env_example() -> None:
    block = """
# --- Email (activation / invites) Job 93 ---
# Required for real delivery outside development-without-SMTP:
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=apikey_or_user
SMTP_PASSWORD=secret
SMTP_FROM="AI Employee Platform <noreply@yourdomain.com>"
# Public URL used inside activation links (must be https in production)
PUBLIC_BASE_URL=https://app.yourdomain.com
# Local dev example:
# PUBLIC_BASE_URL=http://127.0.0.1:8000
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=465
# SMTP_USERNAME=you@gmail.com
# SMTP_PASSWORD=app-password
"""
    if ENV_EXAMPLE.exists():
        t = ENV_EXAMPLE.read_text(encoding="utf-8")
        if "SMTP_HOST" in t:
            print("[OK] .env.example already has SMTP")
            return
        ENV_EXAMPLE.write_text(t.rstrip() + "\n" + block, encoding="utf-8")
    else:
        ENV_EXAMPLE.write_text(block.lstrip(), encoding="utf-8")
    print("[OK] .env.example SMTP section")


def patch_html_notice() -> None:
    if not HTML.exists():
        return
    t = HTML.read_text(encoding="utf-8")
    # Ensure post-register notice panel exists
    if 'id="registerSuccessPanel"' not in t:
        notice = '''
      <div id="registerSuccessPanel" class="tab-panel user-only">
        <div class="auth-notice">
          <div class="auth-notice-icon">✉</div>
          <h2>Check your email</h2>
          <p class="muted">We sent an activation link to <strong id="registerSuccessEmail"></strong>.</p>
          <p class="muted">Open the link to activate your owner account, then sign in.</p>
          <button type="button" id="btnGoLoginAfterRegister" class="primary block">Go to sign in</button>
          <button type="button" id="btnResendFromNotice" class="link-btn">Resend activation email</button>
          <p id="registerSuccessLog" class="login-message" role="status"></p>
        </div>
      </div>
'''
        # insert after tab-register block closing - find tab-invite
        if 'id="tab-invite"' in t:
            t = t.replace(
                '<div id="tab-invite" class="tab-panel user-only">',
                notice + '\n      <div id="tab-invite" class="tab-panel user-only">',
                1,
            )
        else:
            t = t.replace("</div>\n\n  <!--", notice + "\n  <!--", 1)
    HTML.write_text(t, encoding="utf-8")
    print("[OK] index.html register success panel")


def patch_js_notice() -> None:
    if not JS.exists():
        return
    t = JS.read_text(encoding="utf-8")
    # After successful register, show notice panel instead of verification token UI
    inject = '''
      // Job 93 fix — dedicated "check your email" notice + login CTA
      try {
        if ($("registerSuccessEmail")) $("registerSuccessEmail").textContent = email;
        if ($("registerSuccessPanel")) {
          document.querySelectorAll(".login-tabs .tab, .tab-panel").forEach((el) => el.classList.remove("active"));
          $("registerSuccessPanel").classList.add("active");
        }
        if ($("verificationPanel")) $("verificationPanel").classList.add("hidden");
      } catch (_) {}
'''
    if "registerSuccessPanel" not in t or "btnGoLoginAfterRegister" not in t:
        # After log.textContent = result.message in register handler
        if "activationBanner" in t:
            t = t.replace(
                'if ($("activationBanner")) {',
                inject + '\n      if ($("activationBanner")) {',
                1,
            )
        elif 'log.textContent = result.message' in t:
            t = t.replace(
                'log.textContent = result.message',
                'log.textContent = result.message' + inject,
                1,
            )
        handlers = '''
  if ($("btnGoLoginAfterRegister")) {
    $("btnGoLoginAfterRegister").onclick = () => {
      if ($("registerSuccessPanel")) $("registerSuccessPanel").classList.remove("active");
      openLoginTab("login");
    };
  }
  if ($("btnResendFromNotice")) {
    $("btnResendFromNotice").onclick = () => {
      if ($("btnResendVerification")) $("btnResendVerification").click();
      const log = $("registerSuccessLog");
      if (log) log.textContent = "If the account needs activation, another email was requested.";
    };
  }
'''
        if "btnGoLoginAfterRegister" not in t:
            t = t.replace(
                '  $("btnLogin").onclick = async () => {',
                handlers + '\n  $("btnLogin").onclick = async () => {',
                1,
            )
    JS.write_text(t, encoding="utf-8")
    print("[OK] app.js post-register notice")


FLAT_CSS = r'''
/* Job 93 fix — flatter modern auth (minimal chrome, no heavy cards) */
.login-gate {
  background: #0b1220;
}
.login-card {
  width: min(400px, 100%);
  padding: 0.5rem 0.25rem 1rem;
  border: none;
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: none;
  border-radius: 0;
}
.login-brand {
  margin-bottom: 1.25rem;
}
.login-brand h1 {
  font-weight: 650;
  letter-spacing: -0.03em;
}
.login-tabs {
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  padding-bottom: 0.65rem;
  margin-bottom: 1.25rem;
}
.login-tabs .tab {
  border: none;
  background: transparent;
  border-radius: 0;
  padding: 0.35rem 0.5rem;
  position: relative;
}
.login-tabs .tab.active {
  background: transparent;
  border: none;
  color: #f8fafc;
}
.login-tabs .tab.active::after {
  content: "";
  position: absolute;
  left: 0.4rem;
  right: 0.4rem;
  bottom: -0.65rem;
  height: 2px;
  background: linear-gradient(90deg, #0ea5e9, #818cf8);
  border-radius: 2px;
}
.login-card input[type="text"],
.login-card input[type="email"],
.login-card input[type="password"],
.login-card input:not([type]) {
  border: none;
  border-bottom: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 0;
  background: transparent;
  padding: 0.55rem 0.15rem;
}
.login-card input:focus {
  outline: none;
  border-bottom-color: #38bdf8;
}
.login-card .primary.block {
  margin-top: 1.25rem;
  border-radius: 999px;
  padding: 0.7rem 1.1rem;
}
.auth-notice {
  text-align: center;
  padding: 1rem 0.25rem 0.5rem;
}
.auth-notice-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}
.auth-notice h2 {
  margin: 0 0 0.5rem;
  font-size: 1.35rem;
  letter-spacing: -0.02em;
}
/* Wizard: also flatter */
.onboard-card {
  border: none;
  background: transparent;
  backdrop-filter: none;
  box-shadow: none;
  width: min(440px, 94vw);
}
'''


def patch_css_flat() -> None:
    if not CSS.exists():
        print("[SKIP] styles.css")
        return
    t = CSS.read_text(encoding="utf-8")
    if "Job 93 fix — flatter" in t:
        print("[OK] flat CSS already")
        return
    CSS.write_text(t.rstrip() + "\n\n" + FLAT_CSS, encoding="utf-8")
    print("[OK] styles.css flatter auth")


def main() -> int:
    print("Job 93 FIX — email activation + notice page + flat UI")
    print(f"ROOT: {ROOT}")
    patch_deliver_link()
    patch_env_example()
    patch_html_notice()
    patch_js_notice()
    patch_css_flat()
    print(
        """
Configure SMTP in .env (repo root):

  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=465
  SMTP_USERNAME=you@gmail.com
  SMTP_PASSWORD=your-app-password
  SMTP_FROM=AI Employee <you@gmail.com>
  PUBLIC_BASE_URL=http://127.0.0.1:8000

Restart the API server after editing .env.

Verify:
  # Register → "Check your email" panel + Go to sign in
  # Inbox has activation link → /activate?token=...
  # Hard refresh /workspace

  git add app/services/company_onboarding.py app/static/workspace/ \\
          app/static/auth/activate.html .env.example
  git commit -m "Job 93 fix: activation email link, post-register notice, flat auth UI"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
