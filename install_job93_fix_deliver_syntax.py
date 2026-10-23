#!/usr/bin/env python3
"""Job 93 emergency — repair SyntaxError in company_onboarding.deliver()."""
from __future__ import annotations

import re
import sys
from pathlib import Path

PATH = Path.cwd() / "app" / "services" / "company_onboarding.py"

DELIVER = '''def deliver(email, subject, route, token):
    if not mail_ready():
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = subject
    link = f"{settings.public_base_url.rstrip('/')}{route}{token}"
    body = (
        "Activate your AI Employee Platform account.\\n\\n"
        f"Open this link (valid 24 hours):\\n{link}\\n\\n"
        "If you did not register, ignore this email.\\n"
    )
    message.set_content(body)
    # SMTP failures are intentionally not logged with the message or token.
    try:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise auth_sessions.AuthError("Email delivery temporarily unavailable", 503) from None


'''


def main() -> int:
    t = PATH.read_text(encoding="utf-8")
    # Replace entire deliver function up to next def
    t2, n = re.subn(
        r"def deliver\(email, subject, route, token\):[\s\S]*?(?=\ndef )",
        DELIVER,
        t,
        count=1,
    )
    if n != 1:
        # fallback: from def deliver to require_delivery's following content is wrong
        # try until claim_email
        t2, n = re.subn(
            r"def deliver\(email, subject, route, token\):[\s\S]*?(?=\ndef claim_email)",
            DELIVER,
            t,
            count=1,
        )
    if n != 1:
        raise SystemExit("could not locate deliver() to rewrite")

    # Prefer /activate?token= links in register/request_verification
    t2 = t2.replace("/workspace?verify=", "/activate?token=")

    PATH.write_text(t2, encoding="utf-8")
    compile(PATH.read_text(encoding="utf-8"), str(PATH), "exec")
    print("[OK] company_onboarding.deliver() repaired")
    print(
        """
  python -c "from app.services import company_onboarding; print('import OK')"
  .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

  git add app/services/company_onboarding.py
  git commit -m "Job 93 fix: repair deliver() SyntaxError"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
