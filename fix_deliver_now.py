from pathlib import Path
path = Path("app/services/company_onboarding.py")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
start = end = None
for i, line in enumerate(lines):
    if line.startswith("def deliver("):
        start = i
    elif start is not None and end is None and line.startswith("def "):
        end = i
        break
if start is None:
    raise SystemExit("def deliver not found")
if end is None:
    end = len(lines)
print("Replacing lines", start + 1, "-", end)
new_fn = (
    "def deliver(email, subject, route, token):\n"
    "    if not mail_ready():\n"
    "        return\n"
    "    message = EmailMessage()\n"
    '    message["From"] = settings.smtp_from\n'
    '    message["To"] = email\n'
    '    message["Subject"] = subject\n'
    '    link = "%s%s%s" % (settings.public_base_url.rstrip("/"), route, token)\n'
    "    body = (\n"
    '        "Activate your AI Employee Platform account.\\n\\n"\n'
    '        "Open this link (valid 24 hours):\\n"\n'
    "        + link\n"
    '        + "\\n\\nIf you did not register, ignore this email.\\n"\n'
    "    )\n"
    "    message.set_content(body)\n"
    "    try:\n"
    "        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:\n"
    "            if settings.smtp_username:\n"
    "                smtp.login(settings.smtp_username, settings.smtp_password)\n"
    "            smtp.send_message(message)\n"
    "    except (OSError, smtplib.SMTPException):\n"
    '        raise auth_sessions.AuthError("Email delivery temporarily unavailable", 503) from None\n'
    "\n"
)
out = "".join(lines[:start]) + new_fn + "".join(lines[end:])
out = out.replace("/workspace?verify=", "/activate?token=")
path.write_text(out, encoding="utf-8")
compile(path.read_text(encoding="utf-8"), str(path), "exec")
print("REPAIRED OK")
