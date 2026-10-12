from pathlib import Path
ROOT = Path.cwd()
html_path = ROOT / "app/static/auth/forgot-password.html"
t = html_path.read_text(encoding="utf-8")
t = t.replace('const API = "/api/v1";', 'const FORGOT_URL = "/api/v1/auth/forgot-password";\n    const RESET_URL = "/api/v1/auth/reset-password";')
t = t.replace('fetch(API + "/auth/forgot-password"', 'fetch(FORGOT_URL')
t = t.replace('fetch(API + "/auth/reset-password"', 'fetch(RESET_URL')
html_path.write_text(t, encoding="utf-8")
print("ok", "/api/v1/auth/forgot-password" in t)
